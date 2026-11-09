import json
import time
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft7Validator
from sqlalchemy import func, select

from app import models as m
from app.core import iso
from conftest import ingest, key

BASE = "/api/v1/sites/default-site"
DEBUG = "/api/v1/sites/debug-site"


def test_terminal_revocation_cors_preflight(backend):
    client, app = backend
    headers = {
        "Origin": app.state.settings.origins[0],
        "Access-Control-Request-Method": "DELETE",
        "Access-Control-Request-Headers": "X-CSRF-Token",
    }
    response = client.options("/api/v1/auth/sessions/test-session", headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == headers["Origin"]
    assert "DELETE" in response.headers["access-control-allow-methods"]
    assert client.options(
        "/api/v1/auth/sessions/test-session",
        headers={**headers, "Origin": "https://untrusted.invalid"},
    ).status_code == 400


def wait_command(client, command_id):
    for _ in range(100):
        value = client.get(DEBUG + "/commands/" + command_id).json()
        if value["status"] not in ("accepted", "executing"):
            return value
        time.sleep(0.02)
    raise AssertionError("command did not finish")


def test_bootstrap_empty_state_and_contract(backend):
    client, app = backend
    snap = client.get(BASE + "/snapshot").json()
    assert len(snap["metrics"]) == 21
    assert all(r["value"] is None and r["observedAt"] is None for r in snap["metrics"])
    assert all(a["state"] is None for a in snap["actuators"])
    assert snap["summary"] == {"openAlarms": 0, "onlineDevices": None, "totalDevices": None}
    assert client.get(BASE + "/capabilities").json()["controlEnabled"] is False
    assert client.get(BASE + "/capabilities").json()["aiEnabled"] is False
    contract = json.loads((Path(__file__).resolve().parents[2] / "docs/api/openapi.yaml").read_text())

    # OpenAPI 3.0 nullable 转换为JSON Schema，按原契约校验真实响应。
    def schema(value):
        if isinstance(value, list):
            return [schema(v) for v in value]
        if not isinstance(value, dict):
            return value
        value = {k: schema(v) for k, v in value.items() if k != "nullable"} | (
            {"nullable": value["nullable"]} if "nullable" in value else {}
        )
        if value.pop("nullable", False):
            return {"anyOf": [value, {"type": "null"}]}
        return value

    root = schema(contract)
    samples = [("/auth/session", client.get("/api/v1/auth/session")), ("/sites", client.get("/api/v1/sites"))]
    for suffix in (
        "snapshot",
        "monitoring",
        "metrics",
        "capabilities",
        "actuators",
        "cameras",
        "parameters",
        "alarms",
        "logs",
    ):
        samples.append(("/sites/{siteId}/" + suffix, client.get(BASE + "/" + suffix)))
    samples.append(("/sites/{siteId}/ai/sessions", client.get(BASE + "/ai/sessions")))
    samples.append(("/auth/sessions", client.get("/api/v1/auth/sessions")))
    samples.append(("/users", client.get("/api/v1/users")))
    for path, response in samples:
        assert response.status_code == 200, response.text
        response_schema = root["paths"][path]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        full = {**response_schema, "components": root["components"]}
        Draft7Validator(full).validate(response.json())
    actual = app.openapi()["paths"]
    for path, operations in contract["paths"].items():
        for method in operations:
            assert method in actual["/api/v1" + path]


def test_csrf_roles_and_session_revocation(backend):
    client, app = backend
    assert (
        client.post(
            "/api/v1/users",
            json={"username": "viewer", "password": "Test-password-123", "role": "viewer"},
            headers={"X-CSRF-Token": ""},
        ).status_code
        == 403
    )
    created = client.post(
        "/api/v1/users", json={"username": "viewer", "password": "Test-password-123", "role": "viewer"}
    )
    assert created.status_code == 201
    assert "password" not in created.text and "hash" not in created.text
    other = TestClient(app)
    login = other.post("/api/v1/auth/login", json={"username": "viewer", "password": "Test-password-123"})
    other.headers["X-CSRF-Token"] = login.json()["csrfToken"]
    assert other.get(BASE + "/snapshot").status_code == 200
    assert other.get("/api/v1/users").status_code == 403
    assert (
        other.post(
            DEBUG + "/commands",
            json={"actuatorId": "fan", "action": "on", "parameters": {}, "expectedVersion": "v"},
            headers=key(),
        ).status_code
        == 403
    )
    result = client.patch("/api/v1/users/" + created.json()["id"], json={"role": "viewer", "enabled": False})
    assert result.status_code == 200
    assert other.get(BASE + "/snapshot").status_code == 401
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401


def test_last_admin_and_failed_logins(backend):
    client, app = backend
    admin = client.get("/api/v1/auth/session").json()["user"]
    assert (
        client.patch("/api/v1/users/" + admin["id"], json={"role": "viewer", "enabled": True}).status_code
        == 409
    )
    assert (
        client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    )
    for _ in range(10):
        response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 429


def test_telemetry_zero_null_partial_duplicate_and_out_of_order(backend):
    client, app = backend
    observed = m.now() - timedelta(seconds=2)
    body = {
        "messageId": "message-1",
        "metrics": [
            {"metricId": "co", "value": 0, "observedAt": iso(observed)},
            {"metricId": "uv", "value": None, "quality": "invalid"},
        ],
    }
    assert ingest(client, "telemetry", body).status_code == 200
    assert ingest(client, "telemetry", body).json()["duplicate"] is True
    with app.state.db.session() as db:
        assert db.scalar(select(func.count()).select_from(m.Sample)) == 2
    body["metrics"][0]["value"] = 2
    assert ingest(client, "telemetry", body).status_code == 409
    assert (
        ingest(
            client,
            "telemetry",
            {
                "messageId": "message-2",
                "metrics": [
                    {"metricId": "co", "value": 9, "observedAt": iso(observed - timedelta(seconds=10))}
                ],
            },
        ).status_code
        == 200
    )
    readings = {r["metricId"]: r for r in client.get(BASE + "/snapshot").json()["metrics"]}
    assert readings["co"]["value"] == 0
    assert readings["uv"]["value"] is None and readings["uv"]["quality"] == "invalid"
    assert readings["uv"]["observedAt"] is None
    assert readings["inside-temp-04"]["value"] is None
    assert (
        ingest(
            client, "telemetry", {"messageId": "bad", "metrics": [{"metricId": "co", "value": True}]}
        ).status_code
        == 422
    )
    assert (
        ingest(
            client, "telemetry", {"messageId": "bad", "metrics": [{"metricId": "missing", "value": 1}]}
        ).status_code
        == 422
    )
    assert (
        client.post(BASE.replace("/sites/", "/internal/sites/") + "/telemetry", json=body).status_code == 401
    )


def test_stale_and_history_inclusive_validation(backend):
    client, app = backend
    at = m.now() - timedelta(minutes=3)
    for i, value in enumerate([0, None, 10]):
        ingest(
            client,
            "telemetry",
            {
                "messageId": str(i),
                "metrics": [
                    {"metricId": "co", "value": value, "observedAt": iso(at + timedelta(seconds=i * 60))}
                ],
            },
        )
    reading = client.get(BASE + "/snapshot").json()["metrics"][0]
    assert reading["value"] == 10 and reading["quality"] == "stale"
    query = dict(
        metricIds="co", aggregation="raw", **{"from": iso(at), "to": iso(at + timedelta(seconds=120))}
    )
    series = client.get(BASE + "/trends", params=query).json()
    assert [p["value"] for p in series[0]["points"]] == [0, None, 10]
    assert client.get(BASE + "/trends", params={**query, "aggregation": "bad"}).status_code == 422
    assert (
        client.get(BASE + "/trends", params={**query, "from": query["to"], "to": query["from"]}).status_code
        == 422
    )
    assert client.get(BASE + "/trends", params={**query, "from": "2026-01-01T00:00:00"}).status_code == 422
    assert client.get(BASE + "/logs", params={"page": 0}).status_code == 422
    assert client.get(BASE + "/alarms", params={"status": "bad"}).status_code == 422


def test_command_idempotency_version_and_real_site_disabled(backend):
    client, app = backend
    fan = next(a for a in client.get(DEBUG + "/actuators").json() if a["id"] == "fan")
    body = dict(actuatorId="fan", action="off", parameters={}, expectedVersion=fan["version"])
    headers = key()
    first = client.post(DEBUG + "/commands", json=body, headers=headers)
    assert first.status_code == 202, first.text
    command_id = first.json()["commandId"]
    assert client.post(DEBUG + "/commands", json=body, headers=headers).json()["commandId"] == command_id
    assert client.post(DEBUG + "/commands", json={**body, "action": "on"}, headers=headers).status_code == 409
    result = wait_command(client, command_id)
    assert result["status"] == "succeeded" and result["readbackAt"] is not None
    assert "沙箱" in result["result"]
    assert next(a for a in client.get(DEBUG + "/actuators").json() if a["id"] == "fan")["state"] is False
    assert client.post(DEBUG + "/commands", json=body, headers=key()).status_code == 409
    assert client.post(BASE + "/commands", json=body, headers=key()).status_code == 403
    assert client.post(DEBUG + "/commands", json=body).status_code == 422
    with app.state.db.session() as db:
        assert db.scalar(select(func.count()).select_from(m.Command)) == 1


def test_parameter_bounds_and_mode(backend):
    client, app = backend
    param = client.get(DEBUG + "/parameters").json()[0]
    body = {"value": 101, "expectedVersion": param["version"]}
    url = DEBUG + "/parameters/" + param["id"]
    assert client.patch(url, json=body, headers=key()).status_code == 422
    assert client.patch(url, json={**body, "value": 1.5}, headers=key()).status_code == 422
    response = client.patch(url, json={**body, "value": 0}, headers=key())
    assert response.status_code == 202
    assert wait_command(client, response.json()["commandId"])["status"] == "succeeded"
    fan = next(a for a in client.get(DEBUG + "/actuators").json() if a["id"] == "fan")
    response = client.post(
        DEBUG + "/commands",
        json=dict(
            actuatorId="fan", action="set_mode", parameters={"mode": "auto"}, expectedVersion=fan["version"]
        ),
        headers=key(),
    )
    assert response.status_code == 202
    assert wait_command(client, response.json()["commandId"])["status"] == "succeeded"


def test_alarm_ack_pagination_and_event(backend):
    client, app = backend
    alarm = dict(id="alarm-1", level="warning", title="测试报警", occurredAt=iso(m.now()))
    assert ingest(client, "alarms", alarm).status_code == 200
    assert client.get(BASE + "/alarms").json()["total"] == 1
    assert client.get(BASE + "/snapshot").json()["summary"]["openAlarms"] == 1
    response = client.post(BASE + "/alarms/alarm-1/acknowledge")
    assert response.json()["status"] == "acknowledged"
    ingest(client, "alarms", alarm)
    assert client.get(BASE + "/alarms").json()["items"][0]["status"] == "acknowledged"
    assert client.get(BASE + "/logs").json()["items"][0]["action"] == "alarm.acknowledge"


def test_configuration_does_not_invent_states_and_validation_redacts(backend):
    client, app = backend
    body = {
        "metrics": [{"id": "co", "unit": "ppm"}],
        "cameras": [{"id": "cam", "name": "入口", "playbackUrl": None}],
        "parameters": [{"id": "p", "name": "参数", "min": 0, "max": 10, "step": 0.5, "writable": True}],
    }
    assert client.put(BASE + "/configuration", json=body).status_code == 200
    assert client.get(BASE + "/metrics").json()[0]["unit"] == "ppm"
    assert client.get(BASE + "/parameters").json()[0]["value"] is None
    assert client.get(BASE + "/parameters").json()[0]["writable"] is False
    bad = client.post("/api/v1/users", json={"username": "x", "password": "SECRET", "role": "invalid"})
    assert bad.status_code == 422 and "SECRET" not in bad.text
    assert "requestId" in bad.json()
    assert (
        client.put(
            BASE + "/configuration",
            json={"cameras": [{"id": "cam", "name": "入口", "playbackUrl": "rtsp://x"}]},
        ).status_code
        == 422
    )


def test_websocket_sequence_origin_and_logout(backend):
    client, app = backend
    with client.websocket_connect("/ws", headers={"Origin": "http://localhost:5173"}) as ws:
        ws.send_json(
            {"type": "subscribe", "siteId": "default-site", "topics": ["snapshot.updated", "alarm.updated"]}
        )
        # Ping使连接完成订阅初始化后，后台轮询接收新事件。
        time.sleep(0.05)
        ingest(client, "telemetry", {"messageId": "ws1", "metrics": [{"metricId": "co", "value": 0}]})
        first = ws.receive_json()
        assert first["type"] == "snapshot.updated" and first["sequence"] == 1
        ingest(client, "alarms", dict(id="ws-alarm", level="info", title="测试", occurredAt=iso(m.now())))
        second = ws.receive_json()
        assert second["type"] == "alarm.updated" and second["sequence"] == 2
        assert client.post("/api/v1/auth/logout").status_code == 204
        with pytest.raises(Exception):
            ws.receive_json()
    with pytest.raises(Exception):
        with client.websocket_connect("/ws", headers={"Origin": "https://unauthorized.invalid"}):
            pass


def test_ai_disabled_without_fake_reply(backend):
    client, app = backend
    assert client.get(BASE + "/ai/sessions").json() == []
    assert client.post(BASE + "/ai/sessions").status_code == 503


def test_success_requires_actual_target_readback(backend):
    client, app = backend
    # 人工插入待回读记录；绝不启用实体网关，不发网络命令。
    with app.state.db.session() as db:
        user = db.scalar(select(m.User).where(m.User.username == "admin"))
        log = m.OperationLog(
            site_id="default-site", actor="admin", action="on", target="fan", status="unknown"
        )
        db.add(log)
        db.flush()
        cmd = m.Command(
            site_id="default-site",
            user_id=user.id,
            idempotency_key=str(uuid.uuid4()),
            payload_hash="x",
            payload={},
            kind="actuator",
            target_id="fan",
            status="unknown",
            log_id=log.id,
        )
        db.add(cmd)
        db.flush()
        command_id = cmd.id
    assert ingest(client, "feedback", {"commandId": command_id, "status": "succeeded"}).status_code == 422
    assert (
        ingest(
            client,
            "feedback",
            {
                "commandId": command_id,
                "status": "succeeded",
                "actuators": [
                    {
                        "actuatorId": "heater",
                        "state": False,
                        "mode": "manual",
                        "remoteAllowed": True,
                        "interlockOk": True,
                        "observedAt": iso(m.now() + timedelta(seconds=1)),
                    }
                ],
            },
        ).status_code
        == 422
    )
    result = ingest(
        client,
        "feedback",
        {
            "commandId": command_id,
            "status": "succeeded",
            "actuators": [
                {
                    "actuatorId": "fan",
                    "state": False,
                    "mode": "manual",
                    "remoteAllowed": True,
                    "interlockOk": True,
                    "observedAt": iso(m.now() + timedelta(seconds=1)),
                }
            ],
        },
    )
    assert result.status_code == 200, result.text
    assert client.get(BASE + "/commands/" + command_id).json()["readbackAt"] is not None
