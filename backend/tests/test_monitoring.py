"""监测与鉴权回归：全部使用临时SQLite和MQTT替身，不访问生产网络。"""

import struct
from datetime import timedelta
from types import SimpleNamespace

import paho.mqtt.client as mqtt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from starlette.websockets import WebSocketDisconnect

from app import models as m
from app.modbus_mqtt import ModbusPoint
from app.monitoring import FAULT_ADDRESSES, store_block, store_mean
from test_modbus_mqtt import config, make_poller, message, response

BASE = "/api/v1/sites/default-site"


def mean(**kw):
    return ModbusPoint.model_validate(
        dict(
            metricId="oxygen",
            address=420,
            slaveId=1,
            dataType="float_word_swap",
            kind="mean",
            enabled=True,
            mappingConfirmed=True,
            unit="%",
            **kw,
        )
    )


def block(kind, address, metric=None, **kw):
    return ModbusPoint(
        metricId=metric or kind, address=address, slaveId=1, dataType="uint16", kind=kind, enabled=True, **kw
    )


def save(backend, point, words):
    _, app = backend
    data = b"" if words is None else struct.pack(">" + "H" * len(words), *words)
    with app.state.db.session() as db:
        store_block(db, "default-site", point, data, app.state.settings)


def reading(client):
    return next(r for r in client.get(BASE + "/snapshot").json()["metrics"] if r["metricId"] == "oxygen")


def test_mean_same_round_degraded_zero_nonfinite_and_retention(backend):
    client, app = backend

    def put(values):
        with app.state.db.session() as db:
            store_mean(db, "default-site", mean(), values, app.state.settings)
        return reading(client)

    assert put([20, 22])["value"] == 21
    r = put([0, float("nan")])
    assert r["value"] == 0 and r["evidence"]["status"] == "degraded"
    assert r["evidence"]["sources"][1]["value"] is None
    # 第二轮只有右路时只能用右路，不能与上一轮左路的零平均。
    assert put([None, 24])["value"] == 24
    before = reading(client)
    r = put([float("inf"), None])
    assert r["value"] == 24 and r["receivedAt"] == before["receivedAt"]
    assert r["evidence"]["status"] == "missing"
    with app.state.db.session() as db:
        samples = list(
            db.scalars(select(m.Sample).where(m.Sample.metric_id == "oxygen").order_by(m.Sample.id))
        )
        assert [s.value for s in samples] == [21, 0, 24, None]


def test_pressure_unit_gate_and_explicit_source_normalization(backend):
    _, app = backend
    data = dict(
        metricId="outside-pressure",
        address=444,
        slaveId=1,
        dataType="float_word_swap",
        kind="mean",
        enabled=True,
    )
    with pytest.raises(ValidationError):
        ModbusPoint(**data, mappingConfirmed=True)
    with app.state.db.session() as db:
        store_mean(db, "default-site", ModbusPoint(**data), [101.3, 1013], app.state.settings)
        assert db.get(m.Metric, ("default-site", "outside-pressure")).value is None
    # 这里只验证已确认转换的配置行为，不宣称现场PLC采用此换算。
    confirmed = ModbusPoint(**data, mappingConfirmed=True, unit="kPa", secondScale=0.1)
    with app.state.db.session() as db:
        store_mean(db, "default-site", confirmed, [101.3, 1013], app.state.settings)
        db.flush()
        metric = db.get(m.Metric, ("default-site", "outside-pressure"))
        assert metric.value == pytest.approx(101.3) and metric.unit == "kPa"


@pytest.mark.parametrize(
    "words,state",
    [
        ([1, 0], "auto"),
        ([0, 1], "manual"),
        ([0, 0], "stopped"),
        ([1, 1], "invalid"),
        ([2, 0], "invalid"),
        (None, "unknown"),
    ],
)
def test_mode_read_only_and_illegal_combinations(backend, words, state):
    client, app = backend
    save(backend, block("mode", 900), words)
    result = client.get(BASE + "/monitoring").json()["mode"]
    assert result["state"] == state and not result["writable"]
    assert (
        client.post(BASE + "/mode", json=dict(mode="stopped", expectedVersion=result["version"])).status_code
        == 403
    )
    with app.state.db.session() as db:
        assert db.scalar(select(func.count()).select_from(m.Command)) == 0


def test_outputs_keep_motor_directions_and_expiry_unknown(backend):
    client, app = backend
    save(backend, block("outputs", 600), [0, 1, 2, 0, 1, 0, 1, 0, 0, 1])
    outputs = client.get(BASE + "/monitoring").json()["outputs"]
    assert outputs[0]["state"] is False and outputs[2]["state"] is None
    assert [o["id"] for o in outputs[6:]] == [
        "blanket-forward",
        "blanket-reverse",
        "curtain-forward",
        "curtain-reverse",
    ]
    assert [o["state"] for o in outputs[6:]] == [True, False, False, True]
    with app.state.db.session() as db:
        db.get(m.PlcState, ("default-site", "outputs")).received_at = m.now() - timedelta(seconds=91)
    assert all(o["state"] is None for o in client.get(BASE + "/monitoring").json()["outputs"])


def test_all_fault_mappings_dedup_ack_unknown_recover_recur(backend):
    client, app = backend
    assert len(FAULT_ADDRESSES) == 18
    assert FAULT_ADDRESSES[2400][0] == "outside" and FAULT_ADDRESSES[2500][0] == "inside"
    for address in FAULT_ADDRESSES:
        p = block("fault", address, f"fault-{address}")
        save(backend, p, [0])
    assert client.get(BASE + "/alarms").json()["total"] == 0
    assert all(f["state"] == "normal" for f in client.get(BASE + "/monitoring").json()["faults"])
    for address in FAULT_ADDRESSES:
        p = block("fault", address, f"fault-{address}")
        save(backend, p, [1])
        save(backend, p, [1])
    alarms = client.get(BASE + "/alarms", params={"pageSize": 100}).json()
    assert alarms["total"] == 18 and {a["source"] for a in alarms["items"]} == {
        f"D{a}" for a in FAULT_ADDRESSES
    }
    point = block("fault", 2400, "fault-2400")
    alarm = next(a for a in alarms["items"] if a["source"] == "D2400")
    ack = client.post(BASE + f"/alarms/{alarm['id']}/acknowledge").json()
    assert ack["status"] == "acknowledged" and ack["acknowledgedAt"]
    save(backend, point, [1])
    save(backend, point, [2])
    save(backend, point, None)
    current = client.get(BASE + "/monitoring").json()["faults"][14]
    assert current["state"] == "unknown" and current["activeAlarmId"] == alarm["id"]
    assert client.get(BASE + "/snapshot").json()["summary"]["openAlarms"] == 18
    with app.state.db.session() as db:
        db.get(m.PlcState, ("default-site", "fault-1000")).received_at = m.now() - timedelta(seconds=91)
    assert client.get(BASE + "/monitoring").json()["faults"][0]["state"] == "unknown"
    save(backend, point, [0])
    closed = client.get(BASE + "/alarms", params={"status": "closed"}).json()["items"][0]
    assert closed["id"] == alarm["id"] and closed["recoveredAt"] and closed["acknowledgedAt"]
    save(backend, point, [1])
    assert client.get(BASE + "/alarms").json()["total"] == 19
    assert client.get(BASE + "/monitoring").json()["faults"][14]["activeAlarmId"] != alarm["id"]


def test_old_fault_polarity_records_preserved_with_correction_note(backend):
    client, app = backend
    point = block("fault", 1000, "fault-1000")
    save(backend, point, [1])
    with app.state.db.session() as db:
        row = db.get(m.PlcState, ("default-site", "fault-1000"))
        row.payload = {"raw": 0, "activeAlarmId": row.payload["activeAlarmId"]}
    save(backend, point, [0])
    alarm = client.get(BASE + "/alarms").json()["items"][0]
    assert alarm["status"] == "closed" and alarm["recoveredAt"] is None
    assert "旧判定规则关闭" in alarm["detail"]
    assert client.get(BASE + "/monitoring").json()["faults"][0]["activeAlarmId"] is None


def test_meter_raw_scope_and_confirmed_decoding(backend):
    client, app = backend
    save(backend, block("meter", 270), [0, 1, 2, 3])
    meter = client.get(BASE + "/monitoring").json()["meter"]
    assert meter["rawRegisters"] == [0, 1, 2, 3] and not meter["values"] and meter["status"] == "unconfirmed"
    fields = [
        dict(
            metricId="meter-test",
            name="测试量",
            unit="测试单位",
            offset=0,
            dataType="float_word_swap",
            scale=1,
        )
    ]
    point = block("meter", 270, mappingConfirmed=True, meterFields=fields)
    encoded = struct.pack(">f", 12.5)
    words = struct.unpack(">HH", encoded[2:] + encoded[:2])
    save(backend, point, [*words, 0, 0])
    meter = client.get(BASE + "/monitoring").json()["meter"]
    assert meter["values"][0]["value"] == 12.5
    save(backend, point, None)
    assert client.get(BASE + "/monitoring").json()["meter"]["status"] == "unknown"
    with pytest.raises(ValidationError):
        block("meter", 270, meterFields=[{**fields[0], "offset": 3}])
    with pytest.raises(ValidationError):
        config(
            points=[
                mean().model_dump(),
                ModbusPoint(
                    metricId="co", address=422, slaveId=1, dataType="float_word_swap", enabled=True
                ).model_dump(),
            ]
        )


def test_group_poller_word_swap_timeout_and_late_response(backend, tmp_path, monkeypatch):
    client, _ = backend
    point = mean()
    poller = make_poller(backend, tmp_path, monkeypatch, config(points=[point.model_dump()]))

    def publish(*args, **kw):
        data = b"".join((struct.pack(">f", v)[2:] + struct.pack(">f", v)[:2]) for v in [20, 22])
        poller.on_message(None, None, message(response(registers=data)))
        return SimpleNamespace(rc=mqtt.MQTT_ERR_SUCCESS)

    monkeypatch.setattr(poller.client, "publish", publish)
    poller._poll_point(point)
    assert reading(client)["value"] == 21

    def missing(*args, **kw):
        # 不等待真实超时；模拟等待结束后仍无回包。
        poller._pending.done.set()
        return SimpleNamespace(rc=mqtt.MQTT_ERR_SUCCESS)

    monkeypatch.setattr(poller.client, "publish", missing)
    poller._poll_point(point)
    poller.on_message(None, None, message(response(transaction=2, registers=b"\0" * 8)))
    assert reading(client)["value"] == 21 and reading(client)["evidence"]["status"] == "missing"
    assert poller.timeouts == 1 and poller.rejected == 1


def test_independent_terminals_logout_revoke_and_ws_denial(backend):
    a, app = backend
    b = TestClient(app)
    assert b.get(BASE + "/snapshot").status_code == 401
    with pytest.raises(WebSocketDisconnect):
        with b.websocket_connect("/ws", headers={"Origin": "http://localhost:5173"}):
            pass
    login = b.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Test-password-123"},
        headers={"User-Agent": "isolated-B"},
    )
    cookie = login.headers["set-cookie"].lower()
    assert "httponly" in cookie and "max-age" not in cookie and "expires=" not in cookie
    assert "cookie" in login.headers["vary"].lower() and "no-store" in login.headers["cache-control"]
    b.headers["X-CSRF-Token"] = login.json()["csrfToken"]
    assert a.cookies.get(app.state.settings.cookie_name) != b.cookies.get(app.state.settings.cookie_name)
    assert len(a.get("/api/v1/auth/sessions").json()) == 2
    assert a.post("/api/v1/auth/logout").status_code == 204
    assert a.get(BASE + "/snapshot").status_code == 401 and b.get(BASE + "/snapshot").status_code == 200
    current = next(s for s in b.get("/api/v1/auth/sessions").json() if s["current"])
    assert b.delete("/api/v1/auth/sessions/" + current["id"], headers={"X-CSRF-Token": ""}).status_code == 403
    assert b.delete("/api/v1/auth/sessions/" + current["id"]).status_code == 204
    assert b.get(BASE + "/snapshot").status_code == 401


def test_session_scope_and_maximum_age(backend):
    a, app = backend
    a.post("/api/v1/users", json={"username": "viewer", "password": "Test-password-123", "role": "viewer"})
    b = TestClient(app)
    login = b.post("/api/v1/auth/login", json={"username": "viewer", "password": "Test-password-123"})
    b.headers["X-CSRF-Token"] = login.json()["csrfToken"]
    admin_session = next(s for s in a.get("/api/v1/auth/sessions").json() if s["current"])
    assert len(b.get("/api/v1/auth/sessions").json()) == 1
    assert b.delete("/api/v1/auth/sessions/" + admin_session["id"]).status_code == 404
    with app.state.db.session() as db:
        device = db.scalar(
            select(m.SessionDevice).join(m.Session).join(m.User).where(m.User.username == "viewer")
        )
        device.created_at = m.now() - timedelta(hours=12, seconds=1)
    assert b.get("/api/v1/auth/session").status_code == 401


def test_additive_migration_keeps_accounts_and_history(backend):
    client, app = backend
    with app.state.db.session() as db:
        db.execute(m.SchemaVersion.__table__.update().values(version=1))
        db.add(
            m.Sample(
                site_id="default-site",
                metric_id="co",
                value=0,
                quality="good",
                received_at=m.now(),
                timestamp=m.now(),
            )
        )
    app.state.db.migrate()
    app.state.db.migrate()
    with app.state.db.session() as db:
        assert db.scalar(select(m.SchemaVersion.version)) == 2
        assert db.scalar(select(func.count()).select_from(m.User)) == 1
        assert db.scalar(select(m.Sample.value)) == 0
    assert client.get(BASE + "/snapshot").status_code == 200
