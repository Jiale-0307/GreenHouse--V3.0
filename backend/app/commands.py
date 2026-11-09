import uuid
from decimal import Decimal

from sqlalchemy import select

from . import models as m
from .core import audit, can_control, command_data, digest, emit, fail, get_site


def submit(db, site_id, user, body, key, kind, target_id, settings):
    try:
        key = str(uuid.UUID(key))
    except (ValueError, TypeError):
        fail(422, "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key 必须为 UUID")
    # 按站点串行校验与受理；唯一约束同时保证跨进程幂等持久化。
    site = db.scalar(select(m.Site).where(m.Site.id == site_id).with_for_update())
    get_site(db, site_id, settings)
    payload = body.model_dump(mode="json")
    payload_hash = digest({"kind": kind, "target": target_id, "payload": payload})
    old = db.scalar(
        select(m.Command).where(
            m.Command.site_id == site_id, m.Command.user_id == user.id, m.Command.idempotency_key == key
        )
    )
    if old:
        if old.payload_hash != payload_hash:
            fail(409, "IDEMPOTENCY_CONFLICT", "相同幂等键不能用于不同请求")
        return command_data(old)
    if not can_control(site, settings):
        fail(403, "CONTROL_DISABLED", "本站控制尚未启用或协议尚未确认")
    row = db.get(m.Actuator if kind == "actuator" else m.Parameter, (site_id, target_id))
    if not row:
        fail(404, "TARGET_NOT_FOUND", "目标不存在")
    if row.version != body.expectedVersion:
        fail(409, "VERSION_CONFLICT", "目标状态已变化，请刷新后重新确认")
    if not site.is_debug:
        if not settings.stale_after_seconds or not row.feedback_at:
            fail(403, "FRESH_FEEDBACK_REQUIRED", "实体控制需要配置有效期并获得实际回读")
        if (m.now() - row.feedback_at).total_seconds() > settings.stale_after_seconds:
            fail(403, "STALE_FEEDBACK", "状态回读已过期")
    pending = db.scalar(
        select(m.Command.id).where(
            m.Command.site_id == site_id,
            m.Command.kind == kind,
            m.Command.target_id == target_id,
            m.Command.status.in_(["accepted", "executing", "unknown"]),
        )
    )
    if pending:
        fail(409, "TARGET_BUSY", "目标存在未完成或结果未知的指令，请先取得关联回读")
    if kind == "actuator":
        if not row.remote_allowed or not row.interlock_ok:
            fail(403, "INTERLOCK_DENIED", "现场优先级或联锁条件不允许远程操作")
        if body.action == "set_mode":
            if (
                not row.mode_writable
                or set(body.parameters) != {"mode"}
                or body.parameters["mode"] not in ("manual", "auto")
            ):
                fail(422, "INVALID_MODE", "模式写入不允许或参数不合法")
        elif not any(a["id"] == body.action and a["enabled"] for a in row.actions):
            fail(403, "ACTION_DISABLED", "动作未定义或未启用")
    else:
        if not row.writable or any(v is None for v in (row.minimum, row.maximum, row.step)):
            fail(403, "PARAMETER_READONLY", "参数只读或范围未确认")
        value, minimum, maximum, step = map(
            lambda v: Decimal(str(v)), (body.value, row.minimum, row.maximum, row.step)
        )
        if not minimum <= value <= maximum or (value - minimum) % step != 0:
            fail(422, "PARAMETER_RANGE", "参数超出范围或不符合步长")
    action = body.action if kind == "actuator" else "parameter.write"
    log = audit(db, site_id, user.username, action, target_id, status="accepted")
    command = m.Command(
        site_id=site_id,
        user_id=user.id,
        idempotency_key=key,
        payload_hash=payload_hash,
        payload=payload,
        kind=kind,
        target_id=target_id,
        log_id=log.id,
    )
    db.add(command)
    db.flush()
    emit(db, site_id, "command.updated", command_data(command))
    return command_data(command)
