import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth import bootstrap_admin
from app.config import Settings
from app.main import create_app


@pytest.fixture
def backend(tmp_path):
    # 可选的 TEST_MYSQL_URL 必须指向一次性空库；不读取部署 .env。
    url = os.environ.get("TEST_MYSQL_URL", f"sqlite:///{tmp_path}/test.db")
    if os.environ.get("TEST_MYSQL_URL"):
        from sqlalchemy.engine import make_url
        from sqlalchemy import create_engine, inspect

        parsed = make_url(url)
        if not parsed.database or not parsed.database.startswith("zfxzg_test_"):
            raise ValueError("测试MySQL库名必须以 zfxzg_test_ 开头")
        guard = create_engine(url)
        try:
            if inspect(guard).get_table_names():
                raise ValueError("测试MySQL必须是专用空库")
        finally:
            guard.dispose()
    cfg = Settings(
        _env_file=None,
        app_env="test",
        test_database_url=url,
        enable_debug_control=True,
        stale_after_seconds=60,
        ingest_token="local-test-ingest-token-32-characters",
    )
    app = create_app(cfg)
    with TestClient(app) as client:
        with app.state.db.session() as db:
            bootstrap_admin(db, "admin", "Test-password-123")
        result = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "Test-password-123"}
        )
        assert result.status_code == 200, result.text
        client.headers["X-CSRF-Token"] = result.json()["csrfToken"]
        yield client, app
    if os.environ.get("TEST_MYSQL_URL"):
        # 只有显式提供的一次性测试库会清表，不存在部署清库命令。
        from app.models import Base

        Base.metadata.drop_all(app.state.db.engine)


def ingest(client, suffix, body, site="default-site"):
    return client.post(
        f"/api/v1/internal/sites/{site}/{suffix}",
        json=body,
        headers={"Authorization": "Bearer local-test-ingest-token-32-characters"},
    )


def key():
    return {"Idempotency-Key": str(uuid.uuid4())}
