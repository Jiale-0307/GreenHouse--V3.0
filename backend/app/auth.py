import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy import select

from . import models as m
from .core import fail


def hash_password(password):
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password, stored):
    try:
        _, salt, key = stored.split("$")
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(candidate.hex(), key)
    except (ValueError, TypeError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def db_session(request: Request):
    with request.app.state.db.session() as db:
        yield db


def find_session(db, token):
    row = db.get(m.Session, token_hash(token)) if token else None
    user = db.get(m.User, row.user_id) if row else None
    device = (
        db.scalar(select(m.SessionDevice).where(m.SessionDevice.token_hash == row.token_hash))
        if row
        else None
    )
    # 升级前缺少独立终端元数据的旧会话要求重新登录，避免保留旧持久Cookie语义。
    if (
        not row
        or not device
        or row.expires_at <= m.now()
        or device.created_at + timedelta(hours=12) <= m.now()
        or not user
        or not user.enabled
    ):
        return None, None
    return row, user


def authenticated(request: Request, db=Depends(db_session, scope="function")):
    settings = request.app.state.settings
    session, user = find_session(db, request.cookies.get(settings.cookie_name))
    if not user:
        fail(401, "SESSION_EXPIRED", "请登录或重新登录")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        token = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(token, session.csrf_token):
            fail(403, "CSRF_REJECTED", "CSRF令牌无效，请刷新会话")
    request.state.session = session
    return user


def operator(user=Depends(authenticated)):
    if user.role not in ("admin", "operator"):
        fail(403, "ROLE_DENIED", "当前账号没有写入权限")
    return user


def admin(user=Depends(authenticated)):
    if user.role != "admin":
        fail(403, "ADMIN_REQUIRED", "此操作需要管理员权限")
    return user


def create_session(db, user, settings, user_agent=""):
    token = secrets.token_urlsafe(32)
    row = m.Session(
        token_hash=token_hash(token),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(32),
        expires_at=m.now() + timedelta(hours=settings.session_hours),
    )
    db.add(row)
    db.flush()
    db.add(m.SessionDevice(token_hash=row.token_hash, user_agent=user_agent[:256]))
    return token, row


def ingest_auth(request: Request):
    configured = request.app.state.settings.ingest_token.get_secret_value()
    supplied = request.headers.get("Authorization", "")
    if not configured:
        fail(503, "INGEST_DISABLED", "数据接入令牌尚未配置")
    if not hmac.compare_digest(supplied, f"Bearer {configured}"):
        fail(401, "INGEST_UNAUTHORIZED", "数据接入认证失败")


def bootstrap_admin(db, username, password):
    # 锁定站点行，使首次管理员创建与账号更新在 MySQL 下串行。
    db.scalar(select(m.Site).where(m.Site.id == "default-site").with_for_update())
    if db.scalar(select(m.User.id).where(m.User.role == "admin", m.User.enabled.is_(True))):
        raise ValueError("已存在启用的管理员；本命令不会覆盖账号")
    if len(password) < 12 or len(password) > 256:
        raise ValueError("管理员密码长度必须为12至256字符")
    if db.scalar(select(m.User.id).where(m.User.username == username)):
        raise ValueError("账号已存在")
    user = m.User(
        username=username, display_name=username, password_hash=hash_password(password), role="admin"
    )
    db.add(user)
    return user
