"""只接收明确映射后的数据，不推断 PLC 地址、单位或倍率。"""

from datetime import timedelta
from urllib.parse import urlparse

from sqlalchemy import select

from . import models as m
from .core import SNAPSHOT_REFERENCE, alarm_data, audit, command_data, digest, emit, fail, get_site, snapshot


def telemetry(db, site_id, body, settings):
    site = db.scalar(select(m.Site).where(m.Site.id == site_id).with_for_update())
    get_site(db, site_id, settings)
    payload_hash = digest(body.model_dump(mode="json"))
    previous = db.get(m.IngestReceipt, (site_id, body.messageId))
    if previous:
        if previous.payload_hash != payload_hash:
            fail(409, "MESSAGE_CONFLICT", "相同消息ID的载荷不同")
        return {"accepted": True, "duplicate": True}
    if len({r.metricId for r in body.metrics}) != len(body.metrics):
        fail(422, "DUPLICATE_METRIC", "单条消息不能包含重复测点")
    received = m.now()
    for reading in body.metrics:
        row = db.get(m.Metric, (site_id, reading.metricId))
        if not row:
            fail(422, "UNKNOWN_METRIC", "消息包含未定义测点")
        if reading.observedAt and reading.observedAt > received + timedelta(minutes=5):
            fail(422, "FUTURE_TIME", "采集时间超出允许的服务器时钟偏差")
        quality = reading.quality
        value = reading.value if quality not in ("invalid", "unknown") else None
        if value is None and quality == "good":
            quality = "unknown"
        at = reading.observedAt or received
        db.add(
            m.Sample(
                site_id=site_id,
                metric_id=row.id,
                value=value,
                quality=quality,
                observed_at=reading.observedAt,
                received_at=received,
                timestamp=at,
            )
        )
        # 乱序补报进入历史，但不能把最新快照倒退到旧采集时间。
        old_at = row.observed_at or row.received_at
        if old_at is None or at >= old_at:
            row.value, row.quality = value, quality
            row.observed_at, row.received_at = reading.observedAt, received
    site.last_seen_at = received
    db.add(m.IngestReceipt(site_id=site_id, message_id=body.messageId, payload_hash=payload_hash))
    db.flush()
    emit(db, site_id, "snapshot.updated", SNAPSHOT_REFERENCE)
    return {"accepted": True, "duplicate": False}


def command_status(db, row, status, result=None, readback=None):
    row.status, row.result, row.updated_at = status, result, m.now()
    row.readback_at = readback
    log = db.get(m.OperationLog, row.log_id)
    log.status, log.result = status, result
    emit(db, row.site_id, "command.updated", command_data(row))


def feedback(db, site_id, body, settings):
    site = db.scalar(select(m.Site).where(m.Site.id == site_id).with_for_update())
    get_site(db, site_id, settings)
    received = m.now()
    applied = {}
    for item in body.actuators:
        row = db.get(m.Actuator, (site_id, item.actuatorId))
        if not row:
            fail(422, "UNKNOWN_ACTUATOR", "未定义执行机构")
        if item.observedAt > received + timedelta(minutes=5):
            fail(422, "FUTURE_TIME", "回读时间超前")
        if row.feedback_at and item.observedAt <= row.feedback_at:
            continue
        row.state, row.mode = item.state, item.mode
        row.remote_allowed, row.interlock_ok = item.remoteAllowed, item.interlockOk
        row.feedback_at, row.version = item.observedAt, m.uid()
        applied[("actuator", row.id)] = item.observedAt
    for item in body.parameters:
        row = db.get(m.Parameter, (site_id, item.parameterId))
        if not row:
            fail(422, "UNKNOWN_PARAMETER", "未定义参数")
        if item.observedAt > received + timedelta(minutes=5):
            fail(422, "FUTURE_TIME", "回读时间超前")
        if row.feedback_at and item.observedAt <= row.feedback_at:
            continue
        row.value, row.version, row.feedback_at = item.value, m.uid(), item.observedAt
        applied[("parameter", row.id)] = item.observedAt
    if body.commandId:
        command = db.scalar(
            select(m.Command)
            .where(m.Command.id == body.commandId, m.Command.site_id == site_id)
            .with_for_update()
        )
        if not command:
            fail(404, "COMMAND_NOT_FOUND", "指令不存在")
        if not body.status:
            fail(422, "STATUS_REQUIRED", "关联指令必须包含执行状态")
        if command.status in ("succeeded", "rejected"):
            if body.status != command.status:
                fail(409, "TERMINAL_COMMAND", "指令已经结束")
            return command_data(command)
        readback = None
        if body.status == "succeeded":
            readback = applied.get((command.kind, command.target_id))
            # 成功必须是请求之后的新鲜目标回读，不能把网络发送回执当作执行成功。
            if not readback or readback < command.accepted_at:
                fail(422, "READBACK_REQUIRED", "成功状态必须附带目标的新鲜实际回读")
            if command.kind == "actuator":
                current = db.get(m.Actuator, (site_id, command.target_id))
                action = command.payload.get("action")
                if action == "set_mode" and current.mode != command.payload["parameters"]["mode"]:
                    fail(422, "READBACK_MISMATCH", "模式回读与请求不一致")
                if action in ("on", "off") and current.state is not (action == "on"):
                    fail(422, "READBACK_MISMATCH", "开关回读与请求不一致")
            if command.kind == "parameter":
                current = db.get(m.Parameter, (site_id, command.target_id))
                if current.value != command.payload["value"]:
                    fail(422, "READBACK_MISMATCH", "参数回读与请求值不一致")
        command_status(db, command, body.status, body.result, readback)
    site.last_seen_at = received
    db.flush()
    emit(db, site_id, "snapshot.updated", snapshot(db, site, settings))
    return {"accepted": True}


def ingest_alarm(db, site_id, body, settings):
    db.scalar(select(m.Site).where(m.Site.id == site_id).with_for_update())
    get_site(db, site_id, settings)
    row = db.get(m.Alarm, body.id)
    if row and row.site_id != site_id:
        fail(409, "ALARM_ID_CONFLICT", "报警ID已被其他站点使用")
    if row is None:
        row = m.Alarm(id=body.id, site_id=site_id)
        db.add(row)
    # 同一次报警的重传不撤销人工确认；重新发生应使用新的事件ID。
    status = "acknowledged" if row.status == "acknowledged" and body.status == "open" else body.status
    row.level, row.title, row.status = body.level, body.title, status
    row.occurred_at, row.detail, row.can_acknowledge = body.occurredAt, body.detail, body.canAcknowledge
    db.flush()
    emit(db, site_id, "alarm.updated", alarm_data(row))
    return alarm_data(row)


def configure_site(db, site_id, body, settings, actor):
    site = db.scalar(select(m.Site).where(m.Site.id == site_id).with_for_update())
    get_site(db, site_id, settings)
    if body.controlVerified is not None:
        site.control_verified = body.controlVerified
    for item in body.metrics:
        row = db.get(m.Metric, (site_id, item.id))
        if not row:
            fail(422, "UNKNOWN_METRIC", "测点ID必须对应契约定义")
        row.unit, row.enabled = item.unit, item.enabled
    for item in body.actuators:
        if len({a.id for a in item.actions}) != len(item.actions):
            fail(422, "DUPLICATE_ACTION", "动作ID重复")
        row = db.get(m.Actuator, (site_id, item.id))
        if not row:
            row = m.Actuator(site_id=site_id, id=item.id)
            db.add(row)
        row.name, row.kind = item.name, item.kind
        row.actions = [a.model_dump() for a in item.actions]
        row.mode_writable, row.version = item.modeWritable, m.uid()
    for item in body.parameters:
        if (item.min is not None and item.max is not None and item.min > item.max) or (
            item.step is not None and item.step <= 0
        ):
            fail(422, "INVALID_BOUNDS", "参数范围或步长不合法")
        if item.writable and any(v is None for v in (item.min, item.max, item.step)):
            fail(422, "BOUNDS_REQUIRED", "可写参数必须定义上下限与步长")
        row = db.get(m.Parameter, (site_id, item.id))
        if not row:
            row = m.Parameter(site_id=site_id, id=item.id)
            db.add(row)
        row.name, row.unit = item.name, item.unit
        row.minimum, row.maximum, row.step = item.min, item.max, item.step
        row.writable, row.version = item.writable, m.uid()
    for item in body.cameras:
        if item.playbackUrl:
            url = urlparse(item.playbackUrl)
            if (
                url.scheme not in ("http", "https")
                or not url.netloc
                or url.username
                or url.password
                or not item.protocol
            ):
                fail(422, "INVALID_PLAYBACK", "播放地址必须为无嵌入凭据的HTTP(S)地址，并指定协议")
        row = db.get(m.Camera, (site_id, item.id))
        if not row:
            row = m.Camera(site_id=site_id, id=item.id)
            db.add(row)
        row.name, row.playback_url, row.protocol, row.online = (
            item.name,
            item.playbackUrl,
            item.protocol,
            item.online,
        )
    # 配置只记录摘要，签名视频地址、连接令牌不写操作日志。
    audit(db, site_id, actor, "site.configure", site_id, "更新测点/设备/参数/视频定义")
    db.flush()
    emit(db, site_id, "snapshot.updated", snapshot(db, site, settings))
    return {"updated": True}
