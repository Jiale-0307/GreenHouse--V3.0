import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select

from . import models as m

SHANGHAI = ZoneInfo("Asia/Shanghai")
# 最新状态与历史已在业务表持久化；遥测通知只存引用，避免每个测点再写整棚快照。
# 此标记仅用于内部事件表，对外WebSocket仍发送完整Snapshot契约。
SNAPSHOT_REFERENCE = {"snapshotRef": True}
METRICS = [
    ("co", "一氧化碳", "空气质量", "地址01"),
    ("uv", "紫外线", "空气质量", "地址02"),
    ("oxygen", "氧气", "空气质量", "地址03"),
    ("co2", "二氧化碳", "棚内", "地址04 · 四合一"),
    ("light", "光照", "棚内", "地址04 · 四合一"),
    ("inside-temp-04", "空气温度", "棚内", "地址04 · 四合一"),
    ("inside-humidity-04", "空气湿度", "棚内", "地址04 · 四合一"),
    ("outside-pressure", "棚外气压", "棚外", "地址05"),
    ("outside-temp", "棚外温度", "棚外", "地址05"),
    ("outside-humidity", "棚外湿度", "棚外", "地址05"),
    ("inside-pressure", "棚内气压", "棚内", "地址06"),
    ("inside-temp-06", "空气温度", "棚内", "地址06 · 温湿压"),
    ("inside-humidity-06", "空气湿度", "棚内", "地址06 · 温湿压"),
    ("soil-temp", "土壤温度", "土壤", "土壤七合一"),
    ("soil-humidity", "土壤湿度", "土壤", "土壤七合一"),
    ("soil-ph", "土壤 pH", "土壤", "土壤七合一"),
    ("soil-ec", "土壤电导率", "土壤", "土壤七合一"),
    ("soil-n", "土壤氮", "土壤", "土壤七合一"),
    ("soil-p", "土壤磷", "土壤", "土壤七合一"),
    ("soil-k", "土壤钾", "土壤", "土壤七合一"),
    ("uv-index", "紫外线指数", "空气质量", "地址02"),
]
# 单值通道；双路氧气/气压另由monitoring处理，发布前须确认单位及PLC转换。
PLC_REGISTERS = {
    "soil-humidity": 400,
    "soil-temp": 402,
    "soil-ec": 404,
    "soil-ph": 406,
    "soil-n": 408,
    "soil-p": 410,
    "soil-k": 412,
    "uv": 414,
    "uv-index": 416,
    "inside-humidity-04": 430,
    "inside-temp-04": 432,
    "co2": 434,
    "light": 436,
    "outside-humidity": 440,
    "outside-temp": 442,
    "inside-humidity-06": 450,
    "inside-temp-06": 452,
    "co": 460,
}
ACTUATORS = [
    ("fan", "散热风扇"),
    ("heater", "加热器"),
    ("light", "补光灯"),
    ("mist-pump", "喷雾水泵"),
    ("fertilizer-pump", "施肥水泵"),
    ("drip-pump", "滴灌水泵"),
    ("blanket-motor", "棉被电机"),
    ("curtain-motor", "卷帘电机"),
]


def fail(status, code, message):
    raise HTTPException(status, detail={"code": code, "message": message})


def iso(value):
    return value.astimezone(SHANGHAI).isoformat(timespec="seconds") if value else None


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.utcoffset() is None:
            raise ValueError()
        return result
    except (ValueError, AttributeError):
        fail(422, "INVALID_TIME", "时间必须为包含时区的 ISO 8601")


def get_site(db, site_id, settings):
    site = db.get(m.Site, site_id)
    if not site or (site.is_debug and not settings.enable_debug_control):
        fail(404, "SITE_NOT_FOUND", "站点不存在")
    return site


def seed(db, settings):
    sites = [("default-site", "智慧农业大棚", False)]
    if settings.enable_debug_control:
        sites.append(("debug-site", "调试沙箱（无实体动作）", True))
    for site_id, name, debug in sites:
        if not db.get(m.Site, site_id):
            db.add(m.Site(id=site_id, name=name, is_debug=debug))
            db.flush()
        for order, (mid, label, group, source) in enumerate(METRICS):
            mean_addresses = {
                "oxygen": "420/D422",
                "outside-pressure": "444/D446",
                "inside-pressure": "454/D456",
            }
            register_source = (
                f"{source} · PLC D{PLC_REGISTERS[mid]}"
                if mid in PLC_REGISTERS
                else f"{source} · PLC D{mean_addresses[mid]} · 双路待确认"
                if mid in mean_addresses
                else source
            )
            row = db.get(m.Metric, (site_id, mid))
            if not row:
                db.add(
                    m.Metric(
                        site_id=site_id,
                        id=mid,
                        name=label,
                        group_name=group,
                        source=register_source,
                        unit=None,
                        display_order=order,
                    )
                )
            elif row.source == source:
                # 只升级原始默认来源说明；保留用户已配置的单位、开关、读数和自定义来源。
                row.source = register_source
        for aid, label in ACTUATORS:
            if not db.get(m.Actuator, (site_id, aid)):
                db.add(
                    m.Actuator(
                        site_id=site_id, id=aid, name=label, kind=aid, state=None, mode=None, actions=[]
                    )
                )
        if debug:
            db.flush()
            fan = db.get(m.Actuator, (site_id, "fan"))
            fan.actions = [
                {"id": a, "label": label, "enabled": True}
                for a, label in [("on", "开启（沙箱）"), ("off", "关闭（沙箱）")]
            ]
            fan.mode_writable = True
            fan.remote_allowed = fan.interlock_ok = True
            if not db.get(m.Parameter, (site_id, "debug-value")):
                db.add(
                    m.Parameter(
                        site_id=site_id,
                        id="debug-value",
                        name="沙箱参数",
                        minimum=0,
                        maximum=100,
                        step=1,
                        writable=True,
                    )
                )


def user_data(user):
    return dict(
        id=user.id,
        username=user.username,
        displayName=user.display_name,
        role=user.role,
        enabled=user.enabled,
    )


def site_data(site, settings):
    state = "unknown"
    if site.last_seen_at:
        state = (
            "stale"
            if settings.stale_after_seconds
            and (m.now() - site.last_seen_at).total_seconds() > settings.stale_after_seconds
            else "connected"
        )
    return dict(id=site.id, name=site.name, status=state, lastSeenAt=iso(site.last_seen_at))


def metric_data(row):
    return dict(
        id=row.id,
        siteId=row.site_id,
        name=row.name,
        group=row.group_name,
        source=row.source,
        unit=row.unit,
        order=row.display_order,
        enabled=row.enabled,
    )


def reading_data(row, settings, evidence=None):
    quality = row.quality
    if quality == "good" and settings.stale_after_seconds and row.received_at:
        if (m.now() - (row.observed_at or row.received_at)).total_seconds() > settings.stale_after_seconds:
            quality = "stale"
    result = dict(
        metricId=row.id,
        siteId=row.site_id,
        value=row.value,
        quality=quality,
        observedAt=iso(row.observed_at),
        receivedAt=iso(row.received_at),
    )
    if evidence:
        from .monitoring import evidence_data

        result["evidence"] = evidence_data(evidence, settings)
    return result


def can_control(site, settings):
    return (site.is_debug and settings.enable_debug_control) or (
        not site.is_debug and site.control_verified and settings.gateway_ready
    )


def actuator_data(row, site, settings):
    enabled = can_control(site, settings)
    return dict(
        id=row.id,
        siteId=row.site_id,
        name=row.name,
        kind=row.kind,
        state=row.state,
        mode=row.mode,
        version=row.version,
        actions=[{**a, "enabled": enabled and a["enabled"]} for a in row.actions],
        modeWritable=enabled and row.mode_writable,
    )


def parameter_data(row, site, settings):
    return dict(
        id=row.id,
        siteId=row.site_id,
        name=row.name,
        value=row.value,
        unit=row.unit,
        min=row.minimum,
        max=row.maximum,
        step=row.step,
        writable=row.writable and can_control(site, settings),
        version=row.version,
    )


def camera_data(row):
    return dict(
        id=row.id,
        siteId=row.site_id,
        name=row.name,
        playbackUrl=row.playback_url,
        protocol=row.protocol,
        online=row.online,
    )


def alarm_data(row):
    from sqlalchemy.orm import object_session

    db = object_session(row)
    lifecycle = db.get(m.AlarmLifecycle, row.id) if db else None
    return dict(
        id=row.id,
        siteId=row.site_id,
        level=row.level,
        title=row.title,
        status=row.status,
        occurredAt=iso(row.occurred_at),
        detail=row.detail,
        canAcknowledge=row.can_acknowledge and row.status == "open",
        source=lifecycle.source if lifecycle else None,
        acknowledgedAt=iso(lifecycle.acknowledged_at) if lifecycle else None,
        recoveredAt=iso(lifecycle.recovered_at) if lifecycle else None,
    )


def log_data(row):
    return dict(
        id=row.id,
        siteId=row.site_id,
        actor=row.actor,
        action=row.action,
        target=row.target,
        status=row.status,
        requestedAt=iso(row.requested_at),
        result=row.result,
    )


def command_data(row):
    return dict(
        commandId=row.id,
        siteId=row.site_id,
        status=row.status,
        acceptedAt=iso(row.accepted_at),
        updatedAt=iso(row.updated_at),
        readbackAt=iso(row.readback_at),
        result=row.result,
    )


def chat_data(row):
    return dict(id=row.id, siteId=row.site_id, title=row.title, createdAt=iso(row.created_at))


def message_data(row):
    return dict(
        id=row.id,
        sessionId=row.session_id,
        role=row.role,
        content=row.content,
        createdAt=iso(row.created_at),
        controlIntent=row.control_intent,
    )


def snapshot(db, site, settings):
    from .monitoring import monitoring_data

    monitoring = monitoring_data(db, site.id, settings)
    evidence = {
        r.metric_id: r
        for r in db.scalars(select(m.MetricEvidence).where(m.MetricEvidence.site_id == site.id))
    }
    metrics = db.scalars(
        select(m.Metric).where(m.Metric.site_id == site.id).order_by(m.Metric.display_order)
    ).all()
    actuators = db.scalars(
        select(m.Actuator).where(m.Actuator.site_id == site.id).order_by(m.Actuator.id)
    ).all()
    alarms = db.scalar(
        select(func.count())
        .select_from(m.Alarm)
        .where(m.Alarm.site_id == site.id, m.Alarm.status.in_(["open", "acknowledged"]))
    )
    return dict(
        site=site_data(site, settings),
        metrics=[reading_data(r, settings, evidence.get(r.id)) for r in metrics if r.enabled],
        actuators=[actuator_data(r, site, settings) for r in actuators],
        receivedAt=iso(site.last_seen_at),
        monitoring=monitoring,
        summary=dict(openAlarms=alarms, onlineDevices=None, totalDevices=None),
    )


def emit(db, site_id, event_type, payload, user_id=None):
    # 同站事件在提交前持有站点锁，避免并发事务按ID读取时漏掉迟提交事件。
    db.scalar(select(m.Site).where(m.Site.id == site_id).with_for_update())
    db.add(m.Event(site_id=site_id, type=event_type, payload=payload, user_id=user_id))


def audit(db, site_id, actor, action, target, result=None, status="succeeded"):
    row = m.OperationLog(
        site_id=site_id, actor=actor, action=action, target=target, status=status, result=result
    )
    db.add(row)
    db.flush()
    return row
