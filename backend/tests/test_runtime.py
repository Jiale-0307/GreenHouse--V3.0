import asyncio
import threading
import time
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from app import models as m
from app import runtime
from app.config import Settings
from app.db import Database
from app.main import realtime_events
from conftest import ingest, key

BASE = "/api/v1/sites/default-site"
DEBUG = "/api/v1/sites/debug-site"


def test_compact_telemetry_events_preserve_history_and_websocket_contract(backend):
    client, app = backend
    for i in range(3):
        assert ingest(
            client, "telemetry", {"messageId": f"compact-{i}", "metrics": [{"metricId": "co", "value": i}]}
        ).status_code == 200
    with app.state.db.session() as db:
        user_id = db.scalar(select(m.User.id))
        # 旧版完整快照与非遥测事件继续原样返回；私有事件不能泄露给其他用户。
        db.add(m.Event(site_id="default-site", type="snapshot.updated", payload={"legacy": True}))
        db.add(m.Event(site_id="default-site", type="ai.delta", payload={"private": True}, user_id="other"))
        db.add(m.Event(site_id="default-site", type="alarm.updated", payload={"alarm": True}))
    events = realtime_events(app.state.db, "default-site", user_id, 0, app.state.settings)
    assert not any(e["payload"].get("private") for e in events)
    snapshots = [e["payload"] for e in events if e["type"] == "snapshot.updated"]
    assert snapshots[-1] == {"legacy": True}
    assert len(snapshots) == 4
    assert all(next(r for r in s["metrics"] if r["metricId"] == "co")["value"] == 2 for s in snapshots[:3])
    with app.state.db.session() as db:
        from sqlalchemy import func

        assert db.scalar(select(func.count()).select_from(m.Sample)) == 3
        stored = list(db.scalars(select(m.Event).where(m.Event.type == "snapshot.updated").order_by(m.Event.id)))
        assert all(e.payload == {"snapshotRef": True} for e in stored[:3])
        values = list(db.scalars(select(m.Sample.value).order_by(m.Sample.id)))
        assert values == [0, 1, 2]


def test_event_maintenance_is_bounded_and_leaves_business_history(backend):
    client, app = backend
    assert ingest(
        client, "telemetry", {"messageId": "retention-test", "metrics": [{"metricId": "co", "value": 12}]}
    ).status_code == 200
    with app.state.db.session() as db:
        initial = db.scalar(select(m.Event))
        initial.emitted_at = m.now() - timedelta(days=2)
        db.add_all([
            m.Event(site_id="default-site", type="snapshot.updated", payload={}, emitted_at=initial.emitted_at)
            for _ in range(505)
        ])
        current = m.Event(site_id="default-site", type="snapshot.updated", payload={"keep": True})
        db.add(current)
        db.flush()
        current_id = current.id
    app.state.runtime.maintain()
    with app.state.db.session() as db:
        from sqlalchemy import func

        assert db.scalar(select(func.count()).select_from(m.Event)) == 7
        assert db.get(m.Event, current_id).payload == {"keep": True}
        assert db.scalar(select(func.count()).select_from(m.Sample)) == 1
    app.state.runtime.maintain()
    with app.state.db.session() as db:
        assert db.scalar(select(func.count()).select_from(m.Event)) == 1


@pytest.mark.parametrize("worker", ["command_loop", "maintenance_loop"])
def test_background_database_wait_allows_connection_release(tmp_path, monkeypatch, worker):
    """耗尽真实SQL连接池，验证主循环仍能释放占用连接，后台事务最终成功。"""
    monkeypatch.setattr(
        "app.db.create_engine",
        lambda *args, **kwargs: create_engine(
            *args, **kwargs, pool_size=1, max_overflow=0, pool_timeout=0.5
        ),
    )
    cfg = Settings(_env_file=None, app_env="test", test_database_url=f"sqlite:///{tmp_path}/pool.db")
    database = Database(cfg)
    database.migrate()
    original_session = database.session
    finished = threading.Event()
    succeeded = threading.Event()

    @contextmanager
    def session():
        try:
            with original_session() as db:
                yield db
            succeeded.set()
        finally:
            finished.set()

    monkeypatch.setattr(database, "session", session)

    async def exercise():
        held = database.engine.connect()
        instance = runtime.Runtime(SimpleNamespace(state=SimpleNamespace(db=database, settings=cfg)))
        task = asyncio.create_task(getattr(instance, worker)())
        # 模拟HTTP清理必须回到事件循环才能释放连接；同步SQL若阻塞主循环，
        # 后台事务会先触发连接池超时，无法成功执行。
        asyncio.get_running_loop().call_later(0.03, held.close)
        try:
            assert await asyncio.to_thread(finished.wait, 2)
            assert succeeded.is_set()
        finally:
            held.close()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    try:
        asyncio.run(exercise())
    finally:
        database.engine.dispose()


def test_ai_stream_context_private_events_and_recovery(backend, monkeypatch):
    client, app = backend
    cfg = app.state.settings
    cfg.ai_base_url = "https://model.test/v1"
    cfg.ai_model = "test-model"
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text='data: {"choices":[{"delta":{"content":"测试"}}]}\n\ndata: {"choices":[{"delta":{"content":"回复"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        runtime.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    chat = client.post(BASE + "/ai/sessions").json()
    result = client.post(
        BASE + f"/ai/sessions/{chat['id']}/messages", json={"content": "检查数据", "includeContext": True}
    )
    assert result.status_code == 202, result.text
    for _ in range(100):
        rows = client.get(BASE + f"/ai/sessions/{chat['id']}/messages").json()
        if len(rows) > 1:
            break
        time.sleep(0.02)
    assert rows[-1]["role"] == "assistant" and rows[-1]["content"] == "测试回复"
    assert rows[-1]["controlIntent"] is None
    assert len(requests) == 1
    assert "数据质量" in requests[0].content.decode()
    with app.state.db.session() as db:
        events = list(db.scalars(select(m.Event).where(m.Event.type.like("ai.%"))))
        assert all(e.user_id is not None for e in events)
        assert events[-1].type == "ai.completed"
        other = m.User(username="other", display_name="other", password_hash="invalid", role="viewer")
        db.add(other)
        db.flush()
        from app.auth import create_session

        token, _ = create_session(db, other, cfg)
    other_client = TestClient(app)
    other_client.cookies.set(cfg.cookie_name, token)
    assert other_client.get(BASE + f"/ai/sessions/{chat['id']}/messages").status_code == 404


def test_ai_provider_failure_does_not_leak_details(backend, monkeypatch):
    client, app = backend
    app.state.settings.ai_base_url = "https://model.test/v1"
    app.state.settings.ai_model = "test-model"
    original = httpx.AsyncClient
    monkeypatch.setattr(
        runtime.httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(lambda request: httpx.Response(500, text="secret_provider_detail")),
            **kwargs,
        ),
    )
    chat = client.post(BASE + "/ai/sessions").json()
    assert (
        client.post(
            BASE + f"/ai/sessions/{chat['id']}/messages", json={"content": "测试", "includeContext": False}
        ).status_code
        == 202
    )
    for _ in range(100):
        rows = client.get(BASE + f"/ai/sessions/{chat['id']}/messages").json()
        if len(rows) > 1:
            break
        time.sleep(0.02)
    assert rows[-1]["role"] == "system"
    assert "secret_provider_detail" not in str(rows)
    with app.state.db.session() as db:
        assert db.get(m.ChatSession, chat["id"]).busy is False


def test_gateway_http_ack_requires_readback_and_no_retry(backend, monkeypatch):
    client, app = backend
    cfg = app.state.settings
    cfg.control_enabled = cfg.control_protocol_confirmed = True
    cfg.control_gateway_url = "https://gateway.test/commands"
    from pydantic import SecretStr

    cfg.control_gateway_token = SecretStr("test-gateway-token")
    assert (
        client.put(
            BASE + "/configuration",
            json={
                "controlVerified": True,
                "actuators": [
                    {
                        "id": "fan",
                        "name": "风扇",
                        "kind": "fan",
                        "actions": [{"id": "on", "label": "开启", "enabled": True}],
                    }
                ],
            },
        ).status_code
        == 200
    )
    assert (
        ingest(
            client,
            "feedback",
            {
                "actuators": [
                    {
                        "actuatorId": "fan",
                        "state": False,
                        "mode": "manual",
                        "remoteAllowed": True,
                        "interlockOk": True,
                        "observedAt": m.now().isoformat(),
                    }
                ]
            },
        ).status_code
        == 200
    )
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(202, json={"accepted": True})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        runtime.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    fan = next(a for a in client.get(BASE + "/actuators").json() if a["id"] == "fan")
    body = {"actuatorId": "fan", "action": "on", "parameters": {}, "expectedVersion": fan["version"]}
    response = client.post(BASE + "/commands", json=body, headers=key())
    assert response.status_code == 202, response.text
    command_id = response.json()["commandId"]
    for _ in range(100):
        if calls:
            break
        time.sleep(0.02)
    result = client.get(BASE + "/commands/" + command_id).json()
    assert result["status"] == "executing" and result["readbackAt"] is None
    with app.state.db.session() as db:
        db.get(m.Command, command_id).accepted_at = m.now() - timedelta(seconds=100)
    for _ in range(100):
        result = client.get(BASE + "/commands/" + command_id).json()
        if result["status"] == "unknown":
            break
        time.sleep(0.02)
    assert result["status"] == "unknown" and len(calls) == 1


def test_database_migration_idempotent_and_data_retained(backend):
    client, app = backend
    ingest(client, "telemetry", {"messageId": "migration-check", "metrics": [{"metricId": "co", "value": 0}]})
    app.state.db.migrate()
    app.state.db.migrate()
    assert client.get(BASE + "/snapshot").json()["metrics"][0]["value"] == 0
    assert client.get("/api/v1/diagnostics").json()["database"]["schemaVersion"] == 2
