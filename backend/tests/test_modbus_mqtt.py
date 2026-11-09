"""只使用MQTT替身和临时数据库；绝不连接现场Broker或PLC。"""

import json
import struct
import time
from pathlib import Path
from types import SimpleNamespace

import paho.mqtt.client as mqtt
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app import models as m
from app.config import Settings
from app.core import PLC_REGISTERS, seed
from app.modbus_mqtt import (
    ModbusMqttConfig,
    ModbusMqttPoller,
    ModbusPoint,
    PendingRead,
    decode_registers,
    encode_request,
    modbus_request,
    parse_modbus_response,
)

SAMPLE = bytes.fromhex("000100000007010304333341bb")
EXAMPLE = Path(__file__).resolve().parents[1] / "examples/modbus-mqtt.json"


def point(**kwargs):
    return ModbusPoint(
        metricId="soil-temp", address=402, slaveId=1, dataType="float_word_swap", enabled=True, **kwargs
    )


def config(**kwargs):
    data = json.loads(EXAMPLE.read_text())
    data.update(transportConfirmed=True, points=[point().model_dump()])
    data.update(kwargs)
    return ModbusMqttConfig.model_validate(data)


def response(transaction=1, registers=bytes.fromhex("333341bb"), slave=1, function=3):
    return (
        struct.pack(">HHHBBB", transaction, 0, 3 + len(registers), slave, function, len(registers))
        + registers
    )


def message(payload=SAMPLE, topic="dtu/up", retain=False):
    return SimpleNamespace(payload=payload, topic=topic, retain=retain)


def test_user_frame_address_count_and_word_swap():
    assert modbus_request(1, point()).hex(" ") == "00 01 00 00 00 06 01 03 01 92 00 02"
    parsed = parse_modbus_response(SAMPLE)
    assert parsed.transaction_id == 1 and parsed.slave_id == 1
    assert decode_registers(parsed.registers, "float_word_swap") == pytest.approx(23.4, abs=0.00001)
    assert modbus_request(1, point(), -1)[8:10] == bytes.fromhex("0191")
    assert (
        modbus_request(1, ModbusPoint(metricId="co", address=460, slaveId=1, dataType="uint16"))[-2:]
        == b"\x00\x01"
    )


@pytest.mark.parametrize(
    "payload,encoding,path",
    [
        (SAMPLE, "raw", None),
        (SAMPLE, "auto", None),
        (SAMPLE.hex().encode(), "hex", None),
        (b"0001 0000 0007 0103 0433 3341 bb", "auto", None),
        (json.dumps({"data": [{"hex": SAMPLE.hex()}]}).encode(), "json_hex", ["data", 0, "hex"]),
    ],
)
def test_transparent_payload_formats(payload, encoding, path):
    assert parse_modbus_response(payload, encoding, path).registers == SAMPLE[9:]


@pytest.mark.parametrize(
    "frame",
    [
        SAMPLE[:-1],
        SAMPLE + b"\x00",
        SAMPLE + SAMPLE,
        b"bad",
        bytes.fromhex("000100010007010304333341bb"),
        bytes.fromhex("000100000007010604333341bb"),
        bytes.fromhex("000100000007010302333341bb"),
        bytes.fromhex("000100000006010303333341"),
    ],
)
def test_strict_frame_length_protocol_function_and_count(frame):
    with pytest.raises(ValueError):
        parse_modbus_response(frame)


def test_exception_and_integer_decoding():
    assert parse_modbus_response(bytes.fromhex("000100000003018302")).exception_code == 2
    assert decode_registers(b"\xff\xff", "int16") == -1
    assert decode_registers(b"\xff\xff", "uint16") == 65535
    assert decode_registers(bytes.fromhex("00010002"), "uint32") == 65538
    assert decode_registers(struct.pack(">f", 23.4), "float_big_endian") == pytest.approx(23.4)
    with pytest.raises(ValueError):
        decode_registers(b"\x00\x00", "float_word_swap")


@pytest.mark.parametrize(
    "override",
    [
        {"requestTopic": "dtu/#"},
        {"responseTopic": "dtu/down"},
        {"requestTopic": "REPLACE_WITH_REQUEST"},
        {"addressOffset": 65535},
        {"requestEncoding": "json_hex"},
        {"responseEncoding": "json_hex"},
        {"requestHexPath": ["hex"]},
        {"points": [point().model_dump(), point().model_dump()]},
        {"points": [dict(point().model_dump(), functionCode=6)]},
    ],
)
def test_invalid_config_never_reaches_broker(override):
    with pytest.raises(ValidationError):
        config(**override)


def test_raw_hex_and_custom_json_request_encoding():
    frame = modbus_request(1, point())
    assert encode_request(frame, config()) == frame
    assert encode_request(frame, config(requestEncoding="hex")) == frame.hex()
    cfg = config(
        requestEncoding="json_hex",
        requestJson={"id": "device-1", "data": [{"payload": ""}]},
        requestHexPath=["data", 0, "payload"],
    )
    assert json.loads(encode_request(frame, cfg)) == {"id": "device-1", "data": [{"payload": frame.hex()}]}
    assert cfg.requestJson["data"][0]["payload"] == ""


def make_poller(backend, tmp_path, monkeypatch, cfg=None):
    _, app = backend
    cfg = cfg or config()
    path = tmp_path / "modbus.json"
    path.write_text(cfg.model_dump_json())
    app.state.settings.mqtt_modbus_config_file = str(path)
    # 禁止误启动真实网络，即使测试后续改动调用start也会立即失败。
    monkeypatch.setattr(mqtt.Client, "connect_async", lambda *args, **kw: pytest.fail("network forbidden"))
    poller = ModbusMqttPoller(app)
    poller.connected = True
    poller._ready.set()
    poller._next_transaction = 1
    return poller


def test_roundtrip_ingests_once_and_emits_actual_websocket(backend, tmp_path, monkeypatch):
    client, app = backend
    poller = make_poller(backend, tmp_path, monkeypatch)

    def publish(topic, payload, qos, retain):
        assert topic == "dtu/down" and isinstance(payload, bytes) and qos == 0 and retain is False
        assert payload == modbus_request(1, point())
        poller.on_message(None, None, message())
        poller.on_message(None, None, message())  # QoS重复回包不能重复入库。
        return SimpleNamespace(rc=mqtt.MQTT_ERR_SUCCESS)

    monkeypatch.setattr(poller.client, "publish", publish)
    with client.websocket_connect("/ws", headers={"Origin": "http://localhost:5173"}) as ws:
        ws.send_json({"type": "subscribe", "siteId": "default-site", "topics": ["snapshot.updated"]})
        time.sleep(0.05)
        poller._poll_point(point())
        event = ws.receive_json()
        row = next(r for r in event["payload"]["metrics"] if r["metricId"] == "soil-temp")
        assert row["value"] == pytest.approx(23.4, abs=0.00001)
        assert row["observedAt"] is None and row["receivedAt"].endswith("+08:00")
    with app.state.db.session() as db:
        assert db.scalar(select(func.count()).select_from(m.Sample)) == 1
        notification = db.scalar(select(m.Event).where(m.Event.type == "snapshot.updated"))
        assert notification.payload == {"snapshotRef": True}
    assert poller.accepted == 1 and poller.rejected == 1
    assert poller.diagnostics()["lastResponseAt"].endswith("+08:00")
    assert client.get("/api/v1/sites/default-site/capabilities").json()["controlEnabled"] is False


@pytest.mark.parametrize(
    "kind", ["wrong_transaction", "wrong_slave", "retained", "late", "wrong_size", "unsolicited"]
)
def test_unrelated_or_old_responses_cannot_consume_pending(backend, tmp_path, monkeypatch, kind):
    poller = make_poller(backend, tmp_path, monkeypatch)
    pending = PendingRead(1, point(), time.monotonic() + 3)
    poller._pending = pending
    msg = message()
    if kind == "wrong_transaction":
        msg = message(response(transaction=2))
    if kind == "wrong_slave":
        msg = message(response(slave=2))
    if kind == "retained":
        msg = message(retain=True)
    if kind == "late":
        pending.deadline = time.monotonic() - 1
    if kind == "wrong_size":
        msg = message(response(registers=b"\x00\x01"))
    if kind == "unsolicited":
        poller._pending = None
    poller.on_message(None, None, msg)
    assert pending.response is None and not pending.done.is_set()
    assert poller.rejected == 1
    if kind != "unsolicited":
        assert poller._pending is pending


@pytest.mark.parametrize("kind", ["timeout", "publish_failure", "exception", "nan"])
def test_timeout_exception_and_invalid_float_do_not_fabricate_good_values(
    backend, tmp_path, monkeypatch, kind
):
    client, app = backend
    poller = make_poller(backend, tmp_path, monkeypatch)

    def publish(*args, **kw):
        # 只替换本次请求的计时器，不影响TestClient及后台线程的Event。
        monkeypatch.setattr(poller._pending.done, "wait", lambda *args, **kw: False)
        if kind == "exception":
            poller.on_message(None, None, message(bytes.fromhex("000100000003018302")))
        if kind == "nan":
            poller.on_message(None, None, message(response(registers=bytes.fromhex("00007fc0"))))
        return SimpleNamespace(
            rc=mqtt.MQTT_ERR_NO_CONN if kind == "publish_failure" else mqtt.MQTT_ERR_SUCCESS
        )

    monkeypatch.setattr(poller.client, "publish", publish)
    poller._poll_point(point())
    monkeypatch.undo()
    data = client.get("/api/v1/sites/default-site/snapshot").json()
    row = next(r for r in data["metrics"] if r["metricId"] == "soil-temp")
    assert row["value"] is None
    if kind == "nan":
        assert row["quality"] == "invalid" and poller.accepted == 1
    else:
        assert row["receivedAt"] is None and poller.accepted == 0
        assert poller.timeouts == int(kind == "timeout")


def test_subscription_ack_required_and_disconnect_aborts_wait(backend, tmp_path, monkeypatch):
    poller = make_poller(backend, tmp_path, monkeypatch)
    monkeypatch.setattr(poller.client, "subscribe", lambda *a, **kw: (0, 42))
    reason = SimpleNamespace(is_failure=False)
    poller.on_connect(poller.client, None, None, reason, None)
    assert not poller._ready.is_set()
    poller.on_subscribe(poller.client, None, 42, [reason], None)
    assert poller._ready.is_set()
    pending = PendingRead(1, point(), time.monotonic() + 3)
    poller._pending = pending
    poller.on_disconnect(poller.client, None, None, None, None)
    assert not poller._ready.is_set() and pending.done.is_set()


def test_example_only_enables_explicit_points_and_seeding_preserves_user_configuration(
    backend, tmp_path, monkeypatch
):
    client, app = backend
    cfg = ModbusMqttConfig.model_validate_json(EXAMPLE.read_text())
    assert {p.metricId: p.address for p in cfg.points} == PLC_REGISTERS
    assert len(cfg.points) == 18 and all(p.enabled for p in cfg.points)
    assert not ({420, 422, 444, 446, 454, 456, 462, 470} & {p.address for p in cfg.points})
    with app.state.db.session() as db:
        row = db.get(m.Metric, ("default-site", "soil-temp"))
        row.unit = "custom-unit"
        row.source = "custom-source"
        row.enabled = False
        db.flush()
        seed(db, app.state.settings)
    with app.state.db.session() as db:
        row = db.get(m.Metric, ("default-site", "soil-temp"))
        assert row.unit == "custom-unit" and row.source == "custom-source" and not row.enabled
    with pytest.raises(ValueError):
        make_poller(backend, tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        make_poller(backend, tmp_path, monkeypatch, cfg)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            mqtt_modbus_enabled=True,
            mqtt_host="example.invalid",
            mqtt_modbus_config_file=str(EXAMPLE),
        )


def test_websocket_database_wait_does_not_block_http_cleanup(monkeypatch):
    """模拟SQL连接池等待，事件循环必须仍能执行释放连接的HTTP清理。"""
    import asyncio
    import threading
    from contextlib import contextmanager
    from app.main import ws_session

    released = threading.Event()
    started = threading.Event()

    @contextmanager
    def session():
        started.set()
        if not released.wait(1):
            raise AssertionError("event loop could not release database connection")
        yield object()

    monkeypatch.setattr("app.main.find_session", lambda db, token: (None, "user"))
    ws = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(cookie_name="session"))),
        cookies={"session": "test"},
    )

    async def exercise():
        task = asyncio.create_task(ws_session(ws, SimpleNamespace(session=session)))
        await asyncio.sleep(0.05)
        assert started.is_set() and not task.done()
        released.set()
        assert await task == "user"

    asyncio.run(exercise())
