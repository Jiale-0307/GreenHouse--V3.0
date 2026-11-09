from conftest import ingest
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from app import models as m
from app.config import Settings
from app.core import iso
from app.mqtt import Subscription, normalize


def test_mqtt_mapping_zero_missing_scale_and_invalid():
    mapping = Subscription(
        topic="example-only",
        siteId="default-site",
        messageIdPath=["id"],
        observedAtPath=["at"],
        metrics=[
            dict(metricId="co", path=["data", 0], scale=0.1),
            dict(metricId="uv", path=["missing"]),
            dict(metricId="soil-ph", path=["bad"]),
        ],
    )
    packet = normalize({"id": 42, "at": iso(m.now()), "data": [0], "bad": False}, mapping)
    assert packet.messageId == "42"
    assert len(packet.metrics) == 2
    assert packet.metrics[0].value == 0
    assert packet.metrics[1].value is None and packet.metrics[1].quality == "invalid"
    with pytest.raises(ValueError):
        normalize({"id": 1, "data": [0]}, mapping)


def test_deployment_configuration_and_mysql_ddl():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", cookie_secure=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, allowed_origins="*")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, control_enabled=True)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, test_database_url="sqlite:///x")
    for table in m.Base.metadata.sorted_tables:
        sql = str(CreateTable(table).compile(dialect=mysql.dialect()))
        assert "CREATE TABLE" in sql
    cfg = Settings(_env_file=None, db_password="p@ss:/# ?")
    assert cfg.database_url.password == "p@ss:/# ?"


def test_timeout_does_not_claim_success(backend):
    client, app = backend
    with app.state.db.session() as db:
        user = db.query(m.User).filter_by(username="admin").one()
        log = m.OperationLog(
            site_id="default-site", actor="admin", action="test", target="fan", status="executing"
        )
        db.add(log)
        db.flush()
        command = m.Command(
            site_id="default-site",
            user_id=user.id,
            idempotency_key=m.uid(),
            payload_hash="x",
            payload={},
            kind="actuator",
            target_id="fan",
            status="executing",
            log_id=log.id,
            accepted_at=m.now() - timedelta(seconds=100),
        )
        db.add(command)
        db.flush()
        command_id = command.id
    import time

    for _ in range(100):
        result = client.get("/api/v1/sites/default-site/commands/" + command_id).json()
        if result["status"] == "unknown":
            break
        time.sleep(0.02)
    assert result["status"] == "unknown" and result["readbackAt"] is None


def test_aggregate_missing_bucket_is_null(backend):
    client, app = backend
    at = m.now().replace(second=0, microsecond=0) - timedelta(minutes=10)
    for i in [0, 2]:
        result = ingest(
            client,
            "telemetry",
            {
                "messageId": f"gap-{i}",
                "metrics": [{"metricId": "co", "value": i, "observedAt": iso(at + timedelta(minutes=i))}],
            },
        )
        assert result.status_code == 200
    result = client.get(
        "/api/v1/sites/default-site/trends",
        params={
            "metricIds": "co",
            "aggregation": "1m",
            "from": iso(at),
            "to": iso(at + timedelta(minutes=3)),
        },
    ).json()
    assert [p["value"] for p in result[0]["points"]] == [0, None, 2]


def test_example_environment_parses_without_connections(tmp_path):
    from pathlib import Path

    cfg = Settings(_env_file=Path(__file__).resolve().parents[1] / ".env.example")
    assert cfg.db_ssl_ca is None and cfg.mqtt_ca is None
    assert cfg.control_enabled is False
