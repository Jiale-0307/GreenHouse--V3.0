import asyncio
import logging
import json
from pathlib import Path
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Header,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware

from . import models as m, schemas as s
from .auth import (
    admin,
    authenticated,
    create_session,
    db_session,
    find_session,
    hash_password,
    ingest_auth,
    operator,
    verify_password,
)
from .commands import submit
from .config import Settings
from .core import (
    SNAPSHOT_REFERENCE,
    actuator_data,
    alarm_data,
    audit,
    camera_data,
    can_control,
    chat_data,
    command_data,
    emit,
    fail,
    get_site,
    iso,
    log_data,
    message_data,
    metric_data,
    parameter_data,
    seed,
    site_data,
    snapshot,
    timestamp,
    user_data,
)
from .db import Database
from .ingestion import configure_site, ingest_alarm, telemetry, feedback

logger = logging.getLogger("zfxzg")
api = APIRouter(prefix="/api/v1")
SITE = "/sites/{siteId}"
DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def settings(request: Request):
    return request.app.state.settings


@api.get("/auth/session")
def session_info(request: Request, user=Depends(authenticated)):
    return {"user": user_data(user), "csrfToken": request.state.session.csrf_token}


@api.post("/auth/login")
def login(
    body: s.Login,
    request: Request,
    response: Response,
    db=Depends(db_session, scope="function"),
    cfg=Depends(settings),
):
    # 按客户端地址限制失败尝试；反向代理仅信任部署文档配置的来源。
    key = request.client.host if request.client else "unknown"
    attempts = request.app.state.login_attempts[key]
    while attempts and attempts[0] < time.monotonic() - 60:
        attempts.popleft()
    if len(attempts) >= 10:
        fail(429, "LOGIN_RATE_LIMITED", "登录尝试过多，请稍后重试")
    attempts.append(time.monotonic())
    user = db.scalar(select(m.User).where(m.User.username == body.username))
    valid = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.enabled:
        fail(401, "INVALID_CREDENTIALS", "账号或密码错误")
    old, _ = find_session(db, request.cookies.get(cfg.cookie_name))
    if old:
        db.delete(old)
    token, session = create_session(db, user, cfg, request.headers.get("user-agent", ""))
    response.set_cookie(
        cfg.cookie_name,
        token,
        httponly=True,
        secure=cfg.cookie_secure,
        samesite=cfg.cookie_samesite,
        path="/",
    )
    return {"user": user_data(user), "csrfToken": session.csrf_token}


@api.post("/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    user=Depends(authenticated),
    db=Depends(db_session, scope="function"),
    cfg=Depends(settings),
):
    db.delete(request.state.session)
    response.delete_cookie(cfg.cookie_name, path="/", secure=cfg.cookie_secure, samesite=cfg.cookie_samesite)


@api.get("/auth/sessions")
def list_sessions(request: Request, user=Depends(authenticated), db=Depends(db_session, scope="function")):
    # 管理员查看所有活跃终端；普通用户仅能管理自己的会话。
    query = (
        select(m.SessionDevice, m.Session, m.User)
        .join(m.Session, m.SessionDevice.token_hash == m.Session.token_hash)
        .join(m.User, m.Session.user_id == m.User.id)
        .where(m.Session.expires_at > m.now())
    )
    if user.role != "admin":
        query = query.where(m.Session.user_id == user.id)
    return [
        dict(
            id=device.id,
            username=account.username,
            userAgent=device.user_agent,
            createdAt=iso(device.created_at),
            expiresAt=iso(session.expires_at),
            current=session.token_hash == request.state.session.token_hash,
        )
        for device, session, account in db.execute(
            query.order_by(m.SessionDevice.created_at.desc()).limit(200)
        )
    ]


@api.delete("/auth/sessions/{sessionId}", status_code=204)
def revoke_session(
    sessionId: str, request: Request, user=Depends(authenticated), db=Depends(db_session, scope="function")
):
    device = db.get(m.SessionDevice, sessionId)
    session = db.get(m.Session, device.token_hash) if device else None
    if not session or (user.role != "admin" and session.user_id != user.id):
        fail(404, "SESSION_NOT_FOUND", "会话不存在或无访问权限")
    db.delete(session)


@api.get(SITE + "/monitoring")
def get_monitoring(
    siteId: str, user=Depends(authenticated), db=Depends(db_session, scope="function"), cfg=Depends(settings)
):
    from .monitoring import monitoring_data

    get_site(db, siteId, cfg)
    return monitoring_data(db, siteId, cfg)


@api.post(SITE + "/mode", status_code=202)
def set_site_mode(
    siteId: str,
    body: s.ModeWrite,
    user=Depends(operator),
    db=Depends(db_session, scope="function"),
    cfg=Depends(settings),
):
    get_site(db, siteId, cfg)
    # 有读点位不等于有写协议；禁止绕过界面直接调用API触发PLC动作。
    fail(403, "MODE_WRITE_UNCONFIRMED", "停止行为、现场优先级和写入协议尚未确认，模式切换暂未启用")


@api.get("/sites")
def sites(user=Depends(authenticated), db=Depends(db_session, scope="function"), cfg=Depends(settings)):
    rows = db.scalars(select(m.Site).order_by(m.Site.id)).all()
    return [site_data(r, cfg) for r in rows if not r.is_debug or cfg.enable_debug_control]


@api.get(SITE + "/snapshot")
def get_snapshot(
    siteId: str, user=Depends(authenticated), db=Depends(db_session, scope="function"), cfg=Depends(settings)
):
    return snapshot(db, get_site(db, siteId, cfg), cfg)


@api.get(SITE + "/metrics")
def metrics(
    siteId: str, user=Depends(authenticated), db=Depends(db_session, scope="function"), cfg=Depends(settings)
):
    get_site(db, siteId, cfg)
    return [
        metric_data(r)
        for r in db.scalars(
            select(m.Metric).where(m.Metric.site_id == siteId).order_by(m.Metric.display_order)
        )
    ]


@api.get(SITE + "/capabilities")
def capabilities(
    siteId: str, user=Depends(authenticated), db=Depends(db_session, scope="function"), cfg=Depends(settings)
):
    site = get_site(db, siteId, cfg)
    control = can_control(site, cfg)
    writable = db.scalar(
        select(m.Parameter.id).where(m.Parameter.site_id == siteId, m.Parameter.writable.is_(True)).limit(1)
    )
    return dict(
        controlEnabled=control,
        parametersWritable=control and bool(writable),
        aiEnabled=cfg.ai_ready,
        alarmAcknowledge=True,
        historyRanges=[
            dict(id="1h", label="最近1小时", seconds=3600),
            dict(id="24h", label="最近24小时", seconds=86400),
            dict(id="7d", label="最近7天", seconds=604800),
        ],
        aggregations=[
            dict(id="raw", label="原始数据"),
            dict(id="1m", label="1分钟均值"),
            dict(id="5m", label="5分钟均值"),
            dict(id="1h", label="1小时均值"),
        ],
        staleAfterSeconds=cfg.stale_after_seconds,
        commandTimeoutSeconds=cfg.command_timeout_seconds,
    )


@api.get(SITE + "/actuators")
def actuators(
    siteId: str, user=Depends(authenticated), db=Depends(db_session, scope="function"), cfg=Depends(settings)
):
    site = get_site(db, siteId, cfg)
    return [
        actuator_data(r, site, cfg)
        for r in db.scalars(select(m.Actuator).where(m.Actuator.site_id == siteId).order_by(m.Actuator.id))
    ]


@api.get(SITE + "/parameters")
def parameters(
    siteId: str, user=Depends(authenticated), db=Depends(db_session, scope="function"), cfg=Depends(settings)
):
    site = get_site(db, siteId, cfg)
    return [
        parameter_data(r, site, cfg)
        for r in db.scalars(select(m.Parameter).where(m.Parameter.site_id == siteId).order_by(m.Parameter.id))
    ]


@api.get(SITE + "/cameras")
def cameras(
    siteId: str, user=Depends(authenticated), db=Depends(db_session, scope="function"), cfg=Depends(settings)
):
    get_site(db, siteId, cfg)
    return [
        camera_data(r)
        for r in db.scalars(select(m.Camera).where(m.Camera.site_id == siteId).order_by(m.Camera.id))
    ]


@api.get(SITE + "/trends")
def trends(
    siteId: str,
    metricIds: str,
    aggregation: str,
    from_: str = Query(alias="from"),
    to: str = Query(),
    user=Depends(authenticated),
    db=Depends(db_session, scope="function"),
    cfg=Depends(settings),
):
    get_site(db, siteId, cfg)
    start, end = timestamp(from_), timestamp(to)
    if start > end or end - start > timedelta(days=cfg.max_history_days):
        fail(422, "INVALID_RANGE", "历史查询范围倒置或超过允许天数")
    ids = list(dict.fromkeys(metricIds.split(",")))
    if not 1 <= len(ids) <= 100:
        fail(422, "INVALID_METRICS", "请选择1至100项测点")
    known = set(db.scalars(select(m.Metric.id).where(m.Metric.site_id == siteId, m.Metric.enabled.is_(True))))
    if not set(ids) <= known:
        fail(422, "UNKNOWN_METRIC", "包含未启用或不存在的测点")
    buckets = {"raw": 0, "1m": 60, "5m": 300, "1h": 3600}
    if aggregation not in buckets:
        fail(422, "INVALID_AGGREGATION", "不支持的聚合方式")
    rows = db.scalars(
        select(m.Sample)
        .where(
            m.Sample.site_id == siteId,
            m.Sample.metric_id.in_(ids),
            m.Sample.timestamp >= start,
            m.Sample.timestamp <= end,
        )
        .order_by(m.Sample.timestamp, m.Sample.id)
        .limit(200001)
    ).all()
    if len(rows) > 200000:
        fail(422, "QUERY_TOO_LARGE", "数据过多，请缩小查询范围")
    series = {mid: [] for mid in ids}
    interval = buckets[aggregation]
    if interval == 0:
        if len(rows) > cfg.max_trend_points:
            fail(422, "TOO_MANY_POINTS", "原始点过多，请缩小范围或选择聚合")
        for r in rows:
            series[r.metric_id].append(dict(timestamp=iso(r.timestamp), value=r.value))
    else:
        groups = defaultdict(list)
        for r in rows:
            groups[(r.metric_id, int(r.timestamp.timestamp()) // interval * interval)].append(r.value)
        from datetime import datetime, timezone

        point_count = 0
        for mid in ids:
            ticks = [tick for metric_id, tick in groups if metric_id == mid]
            if not ticks:
                continue
            first, last = min(ticks), max(ticks)
            point_count += (last - first) // interval + 1
            if point_count > cfg.max_trend_points:
                fail(422, "TOO_MANY_POINTS", "聚合点过多，请缩小范围或增大聚合周期")
            for tick in range(first, last + 1, interval):
                values = groups.get((mid, tick), [])
                # 空桶和任一明确缺测都保留断点，防止图表跨过中断连线。
                value = None if not values or any(v is None for v in values) else sum(values) / len(values)
                series[mid].append(
                    dict(timestamp=iso(datetime.fromtimestamp(tick, timezone.utc)), value=value)
                )
    return [dict(metricId=mid, points=points) for mid, points in series.items()]


def filtered_page(db, model, site_id, page, size, from_, to, filters, time_column):
    conditions = [model.site_id == site_id]
    start, end = timestamp(from_) if from_ else None, timestamp(to) if to else None
    if start and end and start > end:
        fail(422, "INVALID_RANGE", "开始时间不能晚于结束时间")
    if start:
        conditions.append(time_column >= start)
    if end:
        conditions.append(time_column <= end)
    for column, value, values in filters:
        if value:
            if values and value not in values:
                fail(422, "INVALID_FILTER", "筛选值不合法")
            conditions.append(column == value)
    total = db.scalar(select(func.count()).select_from(model).where(*conditions))
    rows = db.scalars(
        select(model)
        .where(*conditions)
        .order_by(time_column.desc(), model.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    serializer = alarm_data if model is m.Alarm else log_data
    return dict(items=[serializer(r) for r in rows], page=page, pageSize=size, total=total)


@api.get(SITE + "/alarms")
def alarms(
    siteId: str,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    status: str | None = None,
    level: str | None = None,
    user=Depends(authenticated),
    db=Depends(db_session, scope="function"),
    cfg=Depends(settings),
):
    get_site(db, siteId, cfg)
    return filtered_page(
        db,
        m.Alarm,
        siteId,
        page,
        pageSize,
        from_,
        to,
        [
            (m.Alarm.status, status, ("open", "acknowledged", "closed")),
            (m.Alarm.level, level, ("info", "warning", "critical")),
        ],
        m.Alarm.occurred_at,
    )


@api.get(SITE + "/logs")
def logs(
    siteId: str,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    status: str | None = None,
    actor: str | None = None,
    user=Depends(authenticated),
    db=Depends(db_session, scope="function"),
    cfg=Depends(settings),
):
    get_site(db, siteId, cfg)
    return filtered_page(
        db,
        m.OperationLog,
        siteId,
        page,
        pageSize,
        from_,
        to,
        [
            (m.OperationLog.status, status, ("accepted", "executing", "succeeded", "rejected", "unknown")),
            (m.OperationLog.actor, actor, None),
        ],
        m.OperationLog.requested_at,
    )


@api.post(SITE + "/alarms/{alarmId}/acknowledge")
def acknowledge(
    siteId: str,
    alarmId: str,
    user=Depends(operator),
    db=Depends(db_session, scope="function"),
    cfg=Depends(settings),
):
    db.scalar(select(m.Site).where(m.Site.id == siteId).with_for_update())
    get_site(db, siteId, cfg)
    row = db.get(m.Alarm, alarmId)
    if not row or row.site_id != siteId:
        fail(404, "ALARM_NOT_FOUND", "报警不存在")
    if row.status == "acknowledged":
        return alarm_data(row)
    if row.status != "open" or not row.can_acknowledge:
        fail(409, "ALARM_NOT_ACKNOWLEDGEABLE", "此报警不能确认")
    row.status = "acknowledged"
    lifecycle = db.get(m.AlarmLifecycle, row.id)
    if lifecycle:
        lifecycle.acknowledged_at = m.now()
    audit(db, siteId, user.username, "alarm.acknowledge", row.id)
    emit(db, siteId, "alarm.updated", alarm_data(row))
    return alarm_data(row)


@api.post(SITE + "/commands", status_code=202)
def control(
    siteId: str,
    body: s.Control,
    key: str = Header(alias="Idempotency-Key"),
    user=Depends(operator),
    db=Depends(db_session, scope="function"),
    cfg=Depends(settings),
):
    return submit(db, siteId, user, body, key, "actuator", body.actuatorId, cfg)


@api.patch(SITE + "/parameters/{parameterId}", status_code=202)
def parameter_write(
    siteId: str,
    parameterId: str,
    body: s.ParameterWrite,
    key: str = Header(alias="Idempotency-Key"),
    user=Depends(admin),
    db=Depends(db_session, scope="function"),
    cfg=Depends(settings),
):
    return submit(db, siteId, user, body, key, "parameter", parameterId, cfg)


@api.get(SITE + "/commands/{commandId}")
def command(
    siteId: str,
    commandId: str,
    user=Depends(authenticated),
    db=Depends(db_session, scope="function"),
    cfg=Depends(settings),
):
    get_site(db, siteId, cfg)
    row = db.get(m.Command, commandId)
    if not row or row.site_id != siteId:
        fail(404, "COMMAND_NOT_FOUND", "指令不存在")
    return command_data(row)


@api.get("/users")
def users(user=Depends(admin), db=Depends(db_session, scope="function")):
    return [user_data(r) for r in db.scalars(select(m.User).order_by(m.User.username))]


@api.post("/users", status_code=201)
def create_user(body: s.CreateUser, user=Depends(admin), db=Depends(db_session, scope="function")):
    db.scalar(select(m.Site).where(m.Site.id == "default-site").with_for_update())
    if db.scalar(select(m.User.id).where(m.User.username == body.username)):
        fail(409, "USERNAME_EXISTS", "账号已存在")
    row = m.User(
        username=body.username,
        display_name=body.username,
        role=body.role,
        password_hash=hash_password(body.password),
    )
    db.add(row)
    db.flush()
    audit(db, "default-site", user.username, "user.create", row.username)
    return user_data(row)


@api.patch("/users/{userId}")
def update_user(
    userId: str, body: s.UpdateUser, user=Depends(admin), db=Depends(db_session, scope="function")
):
    # 锁住共同的站点行，防止两个管理员并发互相停用后没有管理员。
    db.scalar(select(m.Site).where(m.Site.id == "default-site").with_for_update())
    row = db.get(m.User, userId)
    if not row:
        fail(404, "USER_NOT_FOUND", "账号不存在")
    if row.role == "admin" and row.enabled and (body.role != "admin" or not body.enabled):
        count = db.scalar(
            select(func.count()).select_from(m.User).where(m.User.role == "admin", m.User.enabled.is_(True))
        )
        if count <= 1:
            fail(409, "LAST_ADMIN", "不能停用或降级最后一名管理员")
    row.role, row.enabled = body.role, body.enabled
    db.execute(delete(m.Session).where(m.Session.user_id == row.id))
    audit(db, "default-site", user.username, "user.update", row.username)
    return user_data(row)


def owned_chat(db, site_id, session_id, user, cfg):
    get_site(db, site_id, cfg)
    row = db.get(m.ChatSession, session_id)
    if not row or row.site_id != site_id or row.user_id != user.id:
        fail(404, "CHAT_NOT_FOUND", "会话不存在")
    return row


@api.get(SITE + "/ai/sessions")
def chats(
    siteId: str, user=Depends(authenticated), db=Depends(db_session, scope="function"), cfg=Depends(settings)
):
    get_site(db, siteId, cfg)
    return [
        chat_data(r)
        for r in db.scalars(
            select(m.ChatSession)
            .where(m.ChatSession.site_id == siteId, m.ChatSession.user_id == user.id)
            .order_by(m.ChatSession.created_at.desc())
        )
    ]


@api.post(SITE + "/ai/sessions", status_code=201)
def create_chat(
    siteId: str, user=Depends(authenticated), db=Depends(db_session, scope="function"), cfg=Depends(settings)
):
    get_site(db, siteId, cfg)
    if not cfg.ai_ready:
        fail(503, "AI_NOT_CONFIGURED", "尚未配置模型服务")
    row = m.ChatSession(site_id=siteId, user_id=user.id)
    db.add(row)
    db.flush()
    return chat_data(row)


@api.get(SITE + "/ai/sessions/{sessionId}/messages")
def messages(
    siteId: str,
    sessionId: str,
    user=Depends(authenticated),
    db=Depends(db_session, scope="function"),
    cfg=Depends(settings),
):
    owned_chat(db, siteId, sessionId, user, cfg)
    return [
        message_data(r)
        for r in db.scalars(
            select(m.ChatMessage)
            .where(m.ChatMessage.session_id == sessionId)
            .order_by(m.ChatMessage.created_at, m.ChatMessage.id)
        )
    ]


@api.post(SITE + "/ai/sessions/{sessionId}/messages", status_code=202)
def send_message(
    siteId: str,
    sessionId: str,
    body: s.MessageInput,
    request: Request,
    user=Depends(authenticated),
    db=Depends(db_session, scope="function"),
    cfg=Depends(settings),
):
    owned_chat(db, siteId, sessionId, user, cfg)
    row = db.scalar(select(m.ChatSession).where(m.ChatSession.id == sessionId).with_for_update())
    if not cfg.ai_ready:
        fail(503, "AI_NOT_CONFIGURED", "尚未配置模型服务")
    if row.busy:
        fail(409, "CHAT_BUSY", "请等待上一条消息完成")
    if not body.content.strip():
        fail(422, "EMPTY_MESSAGE", "消息不能为空")
    message = m.ChatMessage(session_id=sessionId, role="user", content=body.content.strip())
    db.add(message)
    row.busy = True
    if row.title == "新会话":
        row.title = body.content.strip()[:40]
    db.flush()
    result = {"messageId": message.id, "userMessage": message_data(message)}
    # 先提交用户消息，再启动后台生成；否则任务可能读到尚未提交的会话。
    db.commit()
    from .runtime import generate_ai

    request.app.state.runtime.spawn(generate_ai(request.app, siteId, sessionId, user.id, body.includeContext))
    return result


@api.post("/internal/sites/{siteId}/telemetry", dependencies=[Depends(ingest_auth)])
def ingest_metrics(
    siteId: str, body: s.Telemetry, db=Depends(db_session, scope="function"), cfg=Depends(settings)
):
    return telemetry(db, siteId, body, cfg)


@api.post("/internal/sites/{siteId}/feedback", dependencies=[Depends(ingest_auth)])
def ingest_feedback(
    siteId: str, body: s.Feedback, db=Depends(db_session, scope="function"), cfg=Depends(settings)
):
    return feedback(db, siteId, body, cfg)


@api.post("/internal/sites/{siteId}/alarms", dependencies=[Depends(ingest_auth)])
def alarm_input(
    siteId: str, body: s.AlarmInput, db=Depends(db_session, scope="function"), cfg=Depends(settings)
):
    return ingest_alarm(db, siteId, body, cfg)


@api.put(SITE + "/configuration")
def configuration(
    siteId: str,
    body: s.SiteConfig,
    user=Depends(admin),
    db=Depends(db_session, scope="function"),
    cfg=Depends(settings),
):
    return configure_site(db, siteId, body, cfg, user.username)


@api.get("/diagnostics")
def diagnostics(
    request: Request, user=Depends(admin), db=Depends(db_session, scope="function"), cfg=Depends(settings)
):
    runtime = request.app.state.runtime
    mqtt = runtime.mqtt
    return dict(
        database={"dialect": db.bind.dialect.name, "schemaVersion": 2},
        mqtt={
            "enabled": cfg.mqtt_enabled,
            "connected": bool(mqtt and mqtt.connected),
            "acceptedMessages": mqtt.accepted if mqtt else 0,
            "rejectedMessages": mqtt.rejected if mqtt else 0,
        },
        modbusMqtt=runtime.modbus_mqtt.diagnostics()
        if runtime.modbus_mqtt
        else {
            "enabled": False,
            "connected": False,
            "ready": False,
            "acceptedMessages": 0,
            "rejectedMessages": 0,
            "publishedRequests": 0,
            "timedOutRequests": 0,
            "failedRequests": 0,
            "lastResponseAt": None,
            "lastError": None,
            "pendingMetricId": None,
        },
        ai={"configured": cfg.ai_ready},
        control={"gatewayConfigured": cfg.gateway_ready, "debugEnabled": cfg.enable_debug_control},
        serverTime=iso(m.now()),
    )


async def ws_session(ws, db):
    cfg = ws.app.state.settings

    def query():
        with db.session() as session:
            _, user = find_session(session, ws.cookies.get(cfg.cookie_name))
            return user

    # SQL连接池等待不能阻塞事件循环，否则HTTP依赖无法清理连接，形成相互等待。
    return await asyncio.to_thread(query)


def realtime_events(database, site_id, user_id, after, cfg):
    """兼容既有完整快照事件；把新遥测引用解析为当前快照，不写回事件表。"""
    with database.session() as db:
        rows = db.scalars(
            select(m.Event)
            .where(
                m.Event.id > after,
                m.Event.site_id == site_id,
                or_(m.Event.user_id.is_(None), m.Event.user_id == user_id),
            )
            .order_by(m.Event.id)
            .limit(200)
        ).all()
        current = None
        events = []
        for row in rows:
            payload = row.payload
            if row.type == "snapshot.updated" and payload == SNAPSHOT_REFERENCE:
                if current is None:
                    current = snapshot(db, get_site(db, site_id, cfg), cfg)
                payload = current
            # 返回独立对象，不能给ORM row.payload赋值，否则只读WS会反向写整份快照。
            events.append(dict(id=row.id, type=row.type, emittedAt=iso(row.emitted_at), payload=payload))
        return events


async def realtime(ws: WebSocket):
    cfg, database = ws.app.state.settings, ws.app.state.db
    if ws.headers.get("origin", "") not in cfg.origins:
        await ws.close(code=1008)
        return
    try:
        user = await ws_session(ws, database)
    except SQLAlchemyError:
        await ws.close(code=1011)
        return
    if not user:
        await ws.close(code=4401)
        return
    await ws.accept()
    try:
        sub = await asyncio.wait_for(ws.receive_json(), timeout=10)
        topics = {
            "snapshot.updated",
            "alarm.updated",
            "command.updated",
            "ai.delta",
            "ai.completed",
            "ai.error",
        }
        if (
            not isinstance(sub, dict)
            or sub.get("type") != "subscribe"
            or not isinstance(sub.get("topics"), list)
            or not set(sub["topics"]) <= topics
        ):
            await ws.close(code=1008)
            return
        site_id = sub.get("siteId")
        if not isinstance(site_id, str):
            await ws.close(code=1008)
            return

        def initial_cursor():
            with database.session() as db:
                db.scalar(select(m.Site).where(m.Site.id == site_id).with_for_update())
                get_site(db, site_id, cfg)
                return db.scalar(select(func.max(m.Event.id))) or 0

        cursor = await asyncio.to_thread(initial_cursor)
        sequence = 0

        while True:
            if not await ws_session(ws, database):
                await ws.close(code=4401)
                return
            rows = await asyncio.to_thread(realtime_events, database, site_id, user.id, cursor, cfg)
            for row in rows:
                cursor = row["id"]
                if row["type"] in sub["topics"]:
                    sequence += 1
                    await ws.send_json(
                        dict(
                            type=row["type"],
                            siteId=site_id,
                            sequence=sequence,
                            emittedAt=row["emittedAt"],
                            payload=row["payload"],
                        )
                    )
            try:
                incoming = await asyncio.wait_for(ws.receive_text(), timeout=0.3)
                if incoming == "ping":
                    continue
                await ws.close(code=1008)
                return
            except asyncio.TimeoutError:
                pass
    except (WebSocketDisconnect, asyncio.TimeoutError):
        return
    except (ValueError, TypeError, HTTPException):
        await ws.close(code=1008)
    except SQLAlchemyError:
        await ws.close(code=1011)


def create_app(config=None):
    cfg = config or Settings()
    database = Database(cfg)

    @asynccontextmanager
    async def lifespan(app):
        database.acquire_runtime_lock()
        runtime = None
        try:
            if cfg.auto_migrate:
                database.migrate()
            if not database.check():
                raise RuntimeError("请先运行 python -m app.cli migrate")
            with database.session() as db:
                seed(db, cfg)
            from .runtime import Runtime

            runtime = Runtime(app)
            app.state.runtime = runtime
            await runtime.start()
            yield
        finally:
            if runtime:
                await runtime.stop()
            database.release_runtime_lock()
            database.engine.dispose()

    app = FastAPI(
        title="智慧农业平台后端",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if cfg.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if cfg.docs_enabled else None,
    )
    app.state.db, app.state.settings = database, cfg
    app.state.login_attempts = defaultdict(deque)

    @app.middleware("http")
    async def boundary(request, call_next):
        request.state.request_id = secrets.token_hex(8)
        origin = request.headers.get("origin")
        if (
            origin
            and origin not in cfg.origins
            and request.method not in ("GET", "HEAD", "OPTIONS")
            and "/internal/" not in request.url.path
        ):
            return JSONResponse(
                {"code": "ORIGIN_DENIED", "message": "请求来源未授权", "requestId": request.state.request_id},
                status_code=403,
            )
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > 262144):
            return JSONResponse(
                {"code": "BODY_TOO_LARGE", "message": "请求体过大", "requestId": request.state.request_id},
                status_code=413,
            )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["Vary"] = "Cookie, Origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        body = (
            exc.detail if isinstance(exc.detail, dict) else {"code": "REQUEST_FAILED", "message": "请求失败"}
        )
        return JSONResponse(
            {**body, "requestId": getattr(request.state, "request_id", None)}, status_code=exc.status_code
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # 不回显 input、密码、令牌或视频签名；只保留字段位置。
        details = [{"field": ".".join(str(v) for v in e["loc"]), "type": e["type"]} for e in exc.errors()]
        return JSONResponse(
            {
                "code": "VALIDATION_ERROR",
                "message": "请求字段不合法",
                "details": details,
                "requestId": request.state.request_id,
            },
            status_code=422,
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        request_id = getattr(request.state, "request_id", None)
        logger.error("database_error request_id=%s type=%s", request_id, type(exc).__name__)
        return JSONResponse(
            {
                "code": "DATABASE_UNAVAILABLE",
                "message": "数据库暂不可用",
                "requestId": request_id,
            },
            status_code=503,
        )

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        logger.error("internal_error request_id=%s type=%s", request.state.request_id, type(exc).__name__)
        return JSONResponse(
            {"code": "INTERNAL_ERROR", "message": "服务内部错误", "requestId": request.state.request_id},
            status_code=500,
        )

    @app.get("/health/live", include_in_schema=False)
    def live():
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    def ready():
        if not database.check():
            fail(503, "NOT_READY", "数据库迁移尚未完成")
        return {"status": "ready"}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.origins,
        allow_credentials=True,
        # 终端会话撤销使用DELETE，分端口开发/部署同样需要允许预检；仍限制精确来源。
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key", "Authorization"],
        expose_headers=["X-Request-ID"],
    )
    app.include_router(api)
    original_openapi = app.openapi

    def documented_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        generated = original_openapi()
        contract_path = Path(__file__).resolve().parents[2] / "docs/api/openapi.yaml"
        if not contract_path.is_file():
            contract_path = Path(__file__).resolve().parent.parent / "contracts/frontend-openapi.json"
        if contract_path.is_file():
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            for path, operations in contract["paths"].items():
                for method, definition in operations.items():
                    generated["paths"]["/api/v1" + path][method] = definition
            generated["components"]["schemas"].update(contract["components"]["schemas"])
            generated["components"]["securitySchemes"] = contract["components"].get("securitySchemes", {})
            generated["security"] = contract.get("security", [])
            generated["components"]["securitySchemes"]["cookieAuth"]["name"] = cfg.cookie_name
        app.openapi_schema = generated
        return generated

    app.openapi = documented_openapi
    app.websocket("/ws")(realtime)
    return app
