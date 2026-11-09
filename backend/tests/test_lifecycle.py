from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models as m
from app.auth import bootstrap_admin
from app.config import Settings
from app.main import create_app


def test_restart_preserves_sessions_data_idempotency_and_marks_unknown(tmp_path):
    config = Settings(_env_file=None, app_env="test", test_database_url=f"sqlite:///{tmp_path}/restart.db")
    app = create_app(config)
    with TestClient(app) as client:
        with app.state.db.session() as db:
            bootstrap_admin(db, "admin", "Test-password-123")
            user = db.scalar(select(m.User))
            log = m.OperationLog(
                site_id="default-site", actor="admin", action="test", target="fan", status="executing"
            )
            db.add(log)
            db.flush()
            cmd = m.Command(
                site_id="default-site",
                user_id=user.id,
                idempotency_key=m.uid(),
                payload_hash="x",
                payload={},
                kind="actuator",
                target_id="fan",
                status="executing",
                log_id=log.id,
                accepted_at=m.now() + timedelta(minutes=1),
            )
            db.add(cmd)
            db.flush()
            command_id = cmd.id
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": "admin", "password": "Test-password-123"}
            ).status_code
            == 200
        )
        cookie = client.cookies.get(config.cookie_name)
    app2 = create_app(config)
    with TestClient(app2) as client:
        client.cookies.set(config.cookie_name, cookie)
        assert client.get("/api/v1/auth/session").status_code == 200
        result = client.get("/api/v1/sites/default-site/commands/" + command_id).json()
        assert result["status"] == "unknown" and result["readbackAt"] is None
