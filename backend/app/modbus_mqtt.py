"""MQTT 透传 Modbus TCP 的只读采集器；只生成功能码 03，不包含 PLC 写操作。"""

from __future__ import annotations

import json
import logging
import math
import secrets
import struct
import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import paho.mqtt.client as mqtt
from pydantic import Field, StrictBool, StrictInt, model_validator
from sqlalchemy import select

from . import models as m
from .core import get_site, iso
from .ingestion import telemetry
from .mqtt import MISSING, lookup
from .schemas import Identifier, Input, Telemetry

logger = logging.getLogger("zfxzg")
PathSegment = str | StrictInt


class MeterField(Input):
    metricId: Identifier
    name: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=32)
    offset: StrictInt = Field(ge=0, le=3)
    dataType: Literal["float_word_swap", "float_big_endian", "uint16", "int16", "uint32"]
    scale: float = 1
    offsetValue: float = 0


class ModbusPoint(Input):
    metricId: Identifier
    # 这里是十进制 D 地址，而不是传感器的 RS485 地址；D402 填 402。
    address: StrictInt = Field(ge=0, le=65535)
    slaveId: StrictInt = Field(ge=1, le=247)
    functionCode: Literal[3] = 3
    dataType: Literal["float_word_swap", "float_big_endian", "uint16", "int16", "uint32"]
    scale: float = 1
    offset: float = 0
    enabled: StrictBool = False
    kind: Literal["metric", "mean", "mode", "outputs", "fault", "meter"] = "metric"
    mappingConfirmed: StrictBool = False
    secondScale: float = 1
    unit: str | None = Field(default=None, max_length=32)
    meterFields: list[MeterField] = Field(default_factory=list, max_length=4)

    @property
    def register_count(self):
        counts = {"mean": 4, "mode": 2, "outputs": 10, "fault": 1, "meter": 4}
        if self.kind in counts:
            return counts[self.kind]
        return 1 if self.dataType in ("uint16", "int16") else 2

    @model_validator(mode="after")
    def confirmed_layout(self):
        from .monitoring import FAULT_ADDRESSES

        fixed = {"mode": ("mode", 900), "outputs": ("outputs", 600), "meter": ("meter", 270)}
        if self.kind in fixed and (self.metricId, self.address) != fixed[self.kind]:
            raise ValueError("监测块ID/地址必须与确认的PLC点位一致")
        if self.kind == "fault" and (
            self.address not in FAULT_ADDRESSES or self.metricId != f"fault-{self.address}"
        ):
            raise ValueError("故障点不在确认的18点范围")
        if self.kind == "mean":
            expected = {"oxygen": 420, "outside-pressure": 444, "inside-pressure": 454}
            if expected.get(self.metricId) != self.address or self.dataType not in (
                "float_word_swap",
                "float_big_endian",
            ):
                raise ValueError("双路均值必须使用已确认地址和浮点类型")
            if self.mappingConfirmed and not self.unit:
                raise ValueError("发布平均值前必须确认单位和两路转换倍率")
        if self.kind == "meter":
            if self.mappingConfirmed and not self.meterFields:
                raise ValueError("电表映射确认前必须提供字段定义")
            occupied = set()
            for field in self.meterFields:
                width = 1 if field.dataType in ("uint16", "int16") else 2
                span = set(range(field.offset, field.offset + width))
                if max(span) > 3 or occupied & span:
                    raise ValueError("电表字段重叠或超出D270至D273")
                occupied |= span
            if len({f.metricId for f in self.meterFields}) != len(self.meterFields):
                raise ValueError("电表测点ID重复")
            if any(not f.metricId.startswith("meter-") for f in self.meterFields):
                raise ValueError("电表测点ID须以meter-开头")
        elif self.meterFields:
            raise ValueError("仅电表通道允许字段映射")
        return self


class ModbusMqttConfig(Input):
    transportConfirmed: StrictBool = False
    requestTopic: str = Field(min_length=1, max_length=512)
    responseTopic: str = Field(min_length=1, max_length=512)
    siteId: Identifier
    requestEncoding: Literal["raw", "hex", "json_hex"]
    responseEncoding: Literal["raw", "hex", "json_hex", "auto"]
    # JSON 包装由现场消息决定；只替换指定路径，不擅自添加设备ID等字段。
    requestJson: dict | None = None
    requestHexPath: list[PathSegment] | None = Field(default=None, min_length=1)
    responseHexPath: list[PathSegment] | None = Field(default=None, min_length=1)
    addressOffset: StrictInt = Field(default=0, ge=-65535, le=65535)
    pollIntervalSeconds: float = Field(ge=1, le=3600)
    timeoutSeconds: float = Field(ge=1, le=60)
    requestGapSeconds: float = Field(ge=0.05, le=10)
    points: list[ModbusPoint] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def check_mapping(self):
        for topic in (self.requestTopic, self.responseTopic):
            if any(c in topic for c in ("+", "#", "\x00")):
                raise ValueError("Modbus MQTT 必须使用精确主题")
            if topic != topic.strip() or "REPLACE_WITH" in topic:
                raise ValueError("MQTT 主题未填写或包含首尾空白")
        if self.requestTopic == self.responseTopic:
            raise ValueError("请求和响应主题不能相同")
        if len({p.metricId for p in self.points}) != len(self.points):
            raise ValueError("测点ID重复")
        occupied = set()
        for point in self.points:
            if not point.enabled:
                continue
            span = {
                (point.slaveId, address)
                for address in range(point.address, point.address + point.register_count)
            }
            if occupied & span:
                raise ValueError("启用的寄存器范围重叠")
            occupied |= span
        for point in self.points:
            start = point.address + self.addressOffset
            if not 0 <= start <= 65536 - point.register_count:
                raise ValueError("寄存器范围超出 Modbus 地址空间")
        if self.requestEncoding == "json_hex":
            if self.requestJson is None or not self.requestHexPath:
                raise ValueError("JSON 请求必须指定模板和十六进制字段路径")
            if lookup(self.requestJson, self.requestHexPath) is MISSING:
                raise ValueError("JSON 请求模板中不存在指定字段")
        elif self.requestJson is not None or self.requestHexPath is not None:
            raise ValueError("仅 JSON 请求允许指定模板/字段路径")
        if (self.responseEncoding == "json_hex") != (self.responseHexPath is not None):
            raise ValueError("仅 JSON 回包必须指定十六进制字段路径")
        return self


def load_config(path: str) -> ModbusMqttConfig:
    return ModbusMqttConfig.model_validate_json(Path(path).read_text(encoding="utf-8"))


def modbus_request(transaction_id: int, point: ModbusPoint, address_offset: int = 0) -> bytes:
    """MBAP 的 length=6 包含从站地址；D402 = 402 = 0x0192，不再减1。"""
    start = point.address + address_offset
    if not 0 <= start <= 65536 - point.register_count:
        raise ValueError("register_address_out_of_range")
    return struct.pack(">HHHBBHH", transaction_id, 0, 6, point.slaveId, 3, start, point.register_count)


def encode_request(frame: bytes, config: ModbusMqttConfig) -> bytes | str:
    if config.requestEncoding == "raw":
        return frame
    if config.requestEncoding == "hex":
        return frame.hex()
    body = deepcopy(config.requestJson)
    parent = body
    for key in config.requestHexPath[:-1]:
        parent = parent[key]
    parent[config.requestHexPath[-1]] = frame.hex()
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def _decode_payload(payload: bytes, encoding: str, hex_path: list | None) -> bytes:
    if len(payload) > 262144:
        raise ValueError("payload_limit")
    if encoding == "raw":
        return payload
    if encoding == "json_hex":
        value = lookup(json.loads(payload), hex_path)
        if not isinstance(value, str):
            raise ValueError("response_hex_field_missing")
        text = value
    else:
        try:
            text = payload.decode("ascii")
        except UnicodeDecodeError:
            if encoding == "auto":
                return payload
            raise ValueError("invalid_hex_payload") from None
    compact = "".join(text.split())
    if not compact or len(compact) % 2 or any(c not in "0123456789abcdefABCDEF" for c in compact):
        if encoding == "auto":
            return payload
        raise ValueError("invalid_hex_payload")
    return bytes.fromhex(compact)


@dataclass(frozen=True)
class ModbusResponse:
    transaction_id: int
    slave_id: int
    registers: bytes
    exception_code: int | None = None


def parse_modbus_response(payload: bytes, encoding: str = "auto", hex_path: list | None = None):
    frame = _decode_payload(payload, encoding, hex_path)
    if not 9 <= len(frame) <= 259:
        raise ValueError("modbus_frame_size")
    transaction, protocol, length, slave, function = struct.unpack(">HHHBB", frame[:8])
    # 不接受尾随帧或额外字节，避免把粘包/错误包装误当成单次正确回读。
    if protocol != 0 or length + 6 != len(frame):
        raise ValueError("modbus_mbap_mismatch")
    if function == 0x83:
        if length != 3:
            raise ValueError("modbus_exception_length")
        return ModbusResponse(transaction, slave, b"", frame[8])
    if function != 3:
        raise ValueError("modbus_function_not_read")
    byte_count = frame[8]
    if not 2 <= byte_count <= 250 or byte_count % 2 or length != 3 + byte_count:
        raise ValueError("modbus_byte_count_mismatch")
    return ModbusResponse(transaction, slave, frame[9:])


def decode_registers(registers: bytes, data_type: str) -> float | int:
    formats = {
        "float_word_swap": ">f",
        "float_big_endian": ">f",
        "uint16": ">H",
        "int16": ">h",
        "uint32": ">I",
    }
    if data_type not in formats:
        raise ValueError("unsupported_data_type")
    if len(registers) != struct.calcsize(formats[data_type]):
        raise ValueError("unexpected_register_count")
    # H3U 示例 33 33 41 BB 按两个16位寄存器交换成 41 BB 33 33，约为23.4。
    if data_type == "float_word_swap":
        registers = registers[2:4] + registers[:2]
    return struct.unpack(formats[data_type], registers)[0]


@dataclass
class PendingRead:
    transaction_id: int
    point: ModbusPoint
    deadline: float
    message_id: str = field(default_factory=m.uid)
    done: threading.Event = field(default_factory=threading.Event)
    response: ModbusResponse | None = None


class ModbusMqttPoller:
    def __init__(self, app):
        self.app = app
        cfg = app.state.settings
        self.mapping = load_config(cfg.mqtt_modbus_config_file)
        if not self.mapping.transportConfirmed or not any(p.enabled for p in self.mapping.points):
            raise ValueError("启用前必须确认 DTU 主题/编码并启用已确认的测点")
        # 配置错误在连接Broker前报错；不能边发请求边发现未知测点。
        with app.state.db.session() as db:
            get_site(db, self.mapping.siteId, cfg)
            known = set(
                db.scalars(
                    select(m.Metric.id).where(
                        m.Metric.site_id == self.mapping.siteId, m.Metric.enabled.is_(True)
                    )
                )
            )
            if (
                not {p.metricId for p in self.mapping.points if p.enabled and p.kind in ("metric", "mean")}
                <= known
            ):
                raise ValueError("Modbus 配置包含未知或禁用测点")
        self.connected = False
        self.accepted = self.rejected = self.published = self.timeouts = self.failures = 0
        self.last_error = self.last_response_at = None
        self._ready, self._stop = threading.Event(), threading.Event()
        self._lock = threading.Lock()
        self._next_transaction = secrets.randbelow(65535) + 1
        self._pending: PendingRead | None = None
        self._thread = None
        self._subscription_mid = None
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{cfg.mqtt_client_id}-modbus")
        if cfg.mqtt_username:
            self.client.username_pw_set(cfg.mqtt_username, cfg.mqtt_password.get_secret_value())
        if cfg.mqtt_tls:
            self.client.tls_set(ca_certs=cfg.mqtt_ca)
        # 请求使用QoS0且retain=false，断线期间不排队/重放旧读请求。
        self.client.max_queued_messages_set(1)
        self.client.reconnect_delay_set(1, 30)
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def start(self):
        cfg = self.app.state.settings
        self._thread = threading.Thread(target=self._poll_loop, name="modbus-mqtt-poller", daemon=True)
        self.client.connect_async(cfg.mqtt_host, cfg.mqtt_port, keepalive=60)
        self.client.loop_start()
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._ready.clear()
        with self._lock:
            if self._pending:
                self._pending.done.set()
        if self._thread:
            self._thread.join(timeout=15)
        self.client.disconnect()
        self.client.loop_stop()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self._ready.clear()
        self.connected = not reason_code.is_failure
        if self.connected:
            rc, self._subscription_mid = client.subscribe(
                self.mapping.responseTopic, qos=self.app.state.settings.mqtt_qos
            )
            if rc != mqtt.MQTT_ERR_SUCCESS:
                self.last_error = "subscribe_failed"
        else:
            self.last_error = "connect_rejected"

    def on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if mid == self._subscription_mid and reason_codes and not any(r.is_failure for r in reason_codes):
            self._ready.set()
        else:
            self.last_error = "subscribe_rejected"

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False
        self._ready.clear()
        self.last_error = "disconnected"
        with self._lock:
            if self._pending:
                self._pending.done.set()

    def _reject(self, code):
        self.rejected += 1
        self.last_error = code
        logger.warning("modbus_mqtt_message_rejected code=%s", code)

    def on_message(self, client, userdata, message):
        # retained 是历史值，不能关联成当前请求的实时回复，尤其是服务重启之后。
        if message.topic != self.mapping.responseTopic or message.retain:
            self._reject("unexpected_or_retained_response")
            return
        try:
            response = parse_modbus_response(
                message.payload, self.mapping.responseEncoding, self.mapping.responseHexPath
            )
        except (ValueError, TypeError, UnicodeError):
            self._reject("malformed_response")
            return
        with self._lock:
            pending = self._pending
            if not pending or pending.response is not None or pending.done.is_set():
                self._reject("unsolicited_or_duplicate_response")
                return
            if (
                response.transaction_id != pending.transaction_id
                or response.slave_id != pending.point.slaveId
            ):
                self._reject("transaction_or_slave_mismatch")
                return
            if time.monotonic() > pending.deadline:
                self._reject("late_response")
                return
            if (
                response.exception_code is None
                and len(response.registers) != pending.point.register_count * 2
            ):
                self._reject("register_count_mismatch")
                return
            # 网络线程只关联数据；数据库操作留给轮询线程，避免阻塞MQTT心跳。
            pending.response = response
            pending.done.set()

    def _poll_point(self, point):
        with self._lock:
            if not self._ready.is_set() or self._stop.is_set():
                return
            transaction = self._next_transaction
            self._next_transaction = transaction % 65535 + 1
            pending = PendingRead(transaction, point, time.monotonic() + self.mapping.timeoutSeconds)
            self._pending = pending
        frame = modbus_request(transaction, point, self.mapping.addressOffset)
        info = self.client.publish(
            self.mapping.requestTopic, encode_request(frame, self.mapping), qos=0, retain=False
        )
        if info.rc == mqtt.MQTT_ERR_SUCCESS:
            self.published += 1
            pending.done.wait(self.mapping.timeoutSeconds)
        with self._lock:
            if self._pending is pending:
                self._pending = None
        if self._stop.is_set():
            return
        if info.rc != mqtt.MQTT_ERR_SUCCESS or not self._ready.is_set():
            self.failures += 1
            self.last_error = "publish_failed_or_disconnected"
            self._missing(point)
            return
        response = pending.response
        if response is None:
            self.timeouts += 1
            self.last_error = "response_timeout"
            self._missing(point)
            return
        if response.exception_code is not None:
            self.failures += 1
            self._reject(f"modbus_exception_{response.exception_code:02x}")
            self._missing(point)
            return
        if point.kind != "metric":
            from .monitoring import store_block, store_mean

            with self.app.state.db.session() as db:
                if point.kind == "mean":
                    values = [decode_registers(response.registers[i : i + 4], point.dataType) for i in (0, 4)]
                    store_mean(db, self.mapping.siteId, point, values, self.app.state.settings)
                else:
                    store_block(db, self.mapping.siteId, point, response.registers, self.app.state.settings)
            self.accepted += 1
            self.last_response_at = iso(m.now())
            self.last_error = None
            return
        raw = decode_registers(response.registers, point.dataType)
        value = raw * point.scale + point.offset
        quality = "good" if math.isfinite(value) else "invalid"
        # Modbus 帧没有PLC采集时间，observedAt 保留null；不能伪造为服务器当前时间。
        body = Telemetry(
            messageId=f"modbus-{pending.message_id}",
            metrics=[
                dict(metricId=point.metricId, value=value if quality == "good" else None, quality=quality)
            ],
        )
        with self.app.state.db.session() as db:
            telemetry(db, self.mapping.siteId, body, self.app.state.settings)
        self.accepted += 1
        self.last_response_at = iso(m.now())
        self.last_error = None if quality == "good" else "non_finite_value"

    def _missing(self, point):
        if point.kind == "metric":
            return
        from .monitoring import store_block, store_mean

        with self.app.state.db.session() as db:
            if point.kind == "mean":
                store_mean(db, self.mapping.siteId, point, [None, None], self.app.state.settings)
            else:
                store_block(db, self.mapping.siteId, point, b"", self.app.state.settings)

    def _poll_loop(self):
        while not self._stop.is_set():
            if not self._ready.wait(0.5):
                continue
            start = time.monotonic()
            for point in self.mapping.points:
                if self._stop.is_set() or not self._ready.is_set():
                    break
                if not point.enabled:
                    continue
                try:
                    # 同一时刻只有一个未完成请求，减轻透传DTU及PLC通信负载。
                    self._poll_point(point)
                except Exception as exc:
                    with self._lock:
                        self._pending = None
                    self.failures += 1
                    self.last_error = "poll_processing_failed"
                    logger.warning("modbus_mqtt_poll_failed type=%s", type(exc).__name__)
                if self._stop.wait(self.mapping.requestGapSeconds):
                    return
            self._stop.wait(max(0, self.mapping.pollIntervalSeconds - (time.monotonic() - start)))

    def diagnostics(self):
        with self._lock:
            pending_id = self._pending.point.metricId if self._pending else None
        return dict(
            enabled=True,
            connected=self.connected,
            ready=self._ready.is_set(),
            acceptedMessages=self.accepted,
            rejectedMessages=self.rejected,
            publishedRequests=self.published,
            timedOutRequests=self.timeouts,
            failedRequests=self.failures,
            lastResponseAt=self.last_response_at,
            lastError=self.last_error,
            pendingMetricId=pending_id,
        )
