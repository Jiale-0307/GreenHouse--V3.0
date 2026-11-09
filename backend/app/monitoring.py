"""PLC只读监测：原始通道、模式、输出及故障事件，绝不生成写入帧。"""

from __future__ import annotations

import math
import struct

from sqlalchemy import select

from . import models as m
from .core import SNAPSHOT_REFERENCE, alarm_data, emit, iso
from .ingestion import telemetry
from .schemas import Telemetry

OUTPUTS = [
    ("fan", "散热风扇"),
    ("heater", "加热器"),
    ("mist-pump", "喷雾水泵"),
    ("drip-pump", "滴灌水泵"),
    ("fertilizer-pump", "施肥水泵"),
    ("light", "补光灯"),
    ("blanket-forward", "棉被电机·正转"),
    ("blanket-reverse", "棉被电机·反转"),
    ("curtain-forward", "卷帘电机·正转"),
    ("curtain-reverse", "卷帘电机·反转"),
]
# D2400/2500按本任务用户明确更正，不能继续沿用图片中颠倒的内外棚标签。
FAULTS = OUTPUTS + [
    ("soil", "土壤传感器"),
    ("uv", "紫外线传感器"),
    ("oxygen", "氧气传感器"),
    ("co2", "CO₂四合一"),
    ("outside", "棚外温湿压"),
    ("inside", "棚内温湿压"),
    ("co", "一氧化碳传感器"),
    ("meter", "电表"),
]
FAULT_ADDRESSES = {1000 + i * 100: (key, label) for i, (key, label) in enumerate(FAULTS)}
# 用户现场更正：当前全部0且无故障；0正常、1故障，其他值未知。
FAULT_ACTIVE_VALUE = 1


def fresh(row, settings):
    return bool(
        row
        and (
            not settings.stale_after_seconds
            or (m.now() - row.received_at).total_seconds() <= settings.stale_after_seconds
        )
    )


def monitoring_data(db, site_id, settings):
    rows = {r.id: r for r in db.scalars(select(m.PlcState).where(m.PlcState.site_id == site_id))}
    mode = rows.get("mode")
    mode_payload = mode.payload if mode else {}
    mode_state = mode_payload.get("state", "unknown") if fresh(mode, settings) else "unknown"
    outputs = rows.get("outputs")
    raw_outputs = outputs.payload.get("raw", []) if outputs else []
    faults = []
    for address, (key, label) in FAULT_ADDRESSES.items():
        row = rows.get(f"fault-{address}")
        raw = row.payload.get("raw") if row else None
        state = (
            ("fault" if raw == FAULT_ACTIVE_VALUE else "normal" if raw == 0 else "unknown")
            if fresh(row, settings)
            else "unknown"
        )
        faults.append(
            dict(
                id=key,
                name=label,
                address=address,
                state=state,
                raw=raw,
                receivedAt=iso(row.received_at) if row else None,
                activeAlarmId=row.payload.get("activeAlarmId") if row else None,
            )
        )
    meter = rows.get("meter")
    meter_payload = meter.payload if meter else {}
    return dict(
        mode=dict(
            state=mode_state,
            raw=mode_payload.get("raw"),
            receivedAt=iso(mode.received_at) if mode else None,
            version=iso(mode.received_at) if mode else "unread",
            writable=False,
            disabledReason="停止行为、现场优先级及写入协议尚未确认",
        ),
        outputs=[
            dict(
                id=key,
                name=label,
                address=600 + i,
                state=(bool(raw_outputs[i]) if raw_outputs[i] in (0, 1) else None)
                if fresh(outputs, settings) and i < len(raw_outputs)
                else None,
                receivedAt=iso(outputs.received_at) if outputs else None,
            )
            for i, (key, label) in enumerate(OUTPUTS)
        ],
        faults=faults,
        meter=dict(
            mappingConfirmed=meter_payload.get("mappingConfirmed", False),
            status=("good" if meter_payload.get("mappingConfirmed") else "unconfirmed")
            if fresh(meter, settings) and meter_payload.get("raw")
            else "unknown",
            rawRegisters=meter_payload.get("raw"),
            values=meter_payload.get("values", []),
            receivedAt=iso(meter.received_at) if meter else None,
        ),
    )


def evidence_data(row, settings):
    return dict(status=row.status, sources=row.sources, attemptedAt=iso(row.attempted_at))


def store_mean(db, site_id, point, raw_values, settings):
    """同一响应内的两个float才可平均，绝不从数据库拼接不同轮次的值。"""
    now = m.now()
    values = [None if value is None or not math.isfinite(value) else value for value in raw_values]
    normalized = [
        v * scale + point.offset if v is not None else None
        for v, scale in zip(values, [point.scale, point.secondScale])
    ]
    normalized = [v if v is not None and math.isfinite(v) else None for v in normalized]
    usable = [v for v in normalized if v is not None]
    status = (
        "unconfirmed"
        if not point.mappingConfirmed
        else ("good" if len(usable) == 2 else "degraded" if usable else "missing")
    )
    evidence = db.get(m.MetricEvidence, (site_id, point.metricId))
    if evidence is None:
        evidence = m.MetricEvidence(site_id=site_id, metric_id=point.metricId)
        db.add(evidence)
    evidence.status, evidence.attempted_at = status, now
    evidence.sources = [
        dict(
            address=point.address + i * 2,
            raw=v,
            value=normalized[i] if point.mappingConfirmed else None,
            unit=point.unit if point.mappingConfirmed else None,
        )
        for i, v in enumerate(values)
    ]
    if point.mappingConfirmed and usable:
        metric = db.get(m.Metric, (site_id, point.metricId))
        metric.unit = point.unit
        telemetry(
            db,
            site_id,
            Telemetry(
                messageId=f"mean-{m.uid()}",
                metrics=[
                    dict(metricId=point.metricId, value=sum(v / len(usable) for v in usable), quality="good")
                ],
            ),
            settings,
        )
    else:
        # 保留最后有效快照；历史写断点，防止图表穿过本轮缺测或待确认阶段。
        db.add(
            m.Sample(
                site_id=site_id,
                metric_id=point.metricId,
                value=None,
                quality="unknown",
                observed_at=None,
                received_at=now,
                timestamp=now,
            )
        )
        emit(db, site_id, "snapshot.updated", SNAPSHOT_REFERENCE)


def decode_meter(registers, field):
    start = field.offset * 2
    length = 2 if field.dataType in ("uint16", "int16") else 4
    data = registers[start : start + length]
    if field.dataType == "float_word_swap":
        data = data[2:4] + data[:2]
    fmt = {"float_word_swap": ">f", "float_big_endian": ">f", "uint16": ">H", "int16": ">h", "uint32": ">I"}[
        field.dataType
    ]
    value = struct.unpack(fmt, data)[0] * field.scale + field.offsetValue
    return value if math.isfinite(value) else None


def store_block(db, site_id, point, registers, settings):
    # 站点锁串行化故障边沿和人工确认，避免并发生成同一故障的多个事件。
    db.scalar(select(m.Site).where(m.Site.id == site_id).with_for_update())
    row = db.get(m.PlcState, (site_id, point.metricId))
    if row is None:
        row = m.PlcState(site_id=site_id, id=point.metricId, payload={})
        db.add(row)
    words = list(struct.unpack(">" + "H" * (len(registers) // 2), registers)) if registers else []
    payload = {"raw": words}
    if point.kind == "mode":
        payload["state"] = (
            "unknown"
            if not words
            else {(1, 0): "auto", (0, 1): "manual", (0, 0): "stopped"}.get(tuple(words), "invalid")
        )
    elif point.kind == "fault":
        raw = words[0] if words else None
        active = row.payload.get("activeAlarmId")
        alarm = db.get(m.Alarm, active) if active else None
        if alarm and row.payload.get("faultActiveValue", 0) != FAULT_ACTIVE_VALUE:
            # 保留旧极性产生的事件，说明关闭原因；不伪造设备实际恢复时间。
            alarm.status = "closed"
            alarm.detail = (alarm.detail or "") + (
                f"\n{iso(m.now())} 依据用户现场反馈更正为0正常、1故障；"
                "本记录因旧判定规则关闭，不表示设备实际恢复。"
            )
            db.flush()
            emit(db, site_id, "alarm.updated", alarm_data(alarm))
            alarm, active = None, None
        if raw == FAULT_ACTIVE_VALUE and not alarm:
            _, name = FAULT_ADDRESSES[point.address]
            alarm = m.Alarm(
                id=m.uid(),
                site_id=site_id,
                title=f"{name}故障",
                level="warning",
                occurred_at=m.now(),
                detail=f"PLC D{point.address}=1；请核查现场，平台不自动停机。",
            )
            db.add(alarm)
            db.flush()
            db.add(m.AlarmLifecycle(alarm_id=alarm.id, source=f"D{point.address}"))
            active = alarm.id
            emit(db, site_id, "alarm.updated", alarm_data(alarm))
        elif raw == 0 and alarm:
            lifecycle = db.get(m.AlarmLifecycle, alarm.id)
            lifecycle.recovered_at = m.now()
            alarm.status = "closed"
            db.flush()
            emit(db, site_id, "alarm.updated", alarm_data(alarm))
            active = None
        # 非0/1及超时不关闭当前故障，也不重复创建故障。
        payload = {"raw": raw, "activeAlarmId": active, "faultActiveValue": FAULT_ACTIVE_VALUE}
    elif point.kind == "meter":
        payload.update(mappingConfirmed=point.mappingConfirmed, values=[])
        if point.mappingConfirmed and registers:
            metrics = []
            for field in point.meterFields:
                value = decode_meter(registers, field)
                payload["values"].append(
                    dict(metricId=field.metricId, name=field.name, unit=field.unit, value=value)
                )
                metric = db.get(m.Metric, (site_id, field.metricId))
                if metric is None:
                    metric = m.Metric(
                        site_id=site_id,
                        id=field.metricId,
                        name=field.name,
                        unit=field.unit,
                        source=f"电表 · PLC D{270 + field.offset}",
                        group_name="电力",
                        display_order=100 + field.offset,
                    )
                    db.add(metric)
                metrics.append(
                    dict(
                        metricId=field.metricId,
                        value=value,
                        quality="good" if value is not None else "invalid",
                    )
                )
            db.flush()
            telemetry(db, site_id, Telemetry(messageId=f"meter-{m.uid()}", metrics=metrics), settings)
    row.payload, row.received_at = payload, m.now()
    db.flush()
    emit(db, site_id, "snapshot.updated", SNAPSHOT_REFERENCE)
