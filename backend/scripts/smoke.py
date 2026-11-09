"""真实本机TCP烟测，使用临时测试库，不读取部署.env或连接外部服务。"""

import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from websockets.asyncio.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.auth import bootstrap_admin
from app.config import Settings
from app.core import seed
from app.db import Database


async def websocket_smoke(port, cookie, token):
    async with connect(
        f"ws://127.0.0.1:{port}/ws", origin="http://localhost:5173", additional_headers={"Cookie": cookie}
    ) as ws:
        await ws.send(
            json.dumps({"type": "subscribe", "siteId": "default-site", "topics": ["snapshot.updated"]})
        )
        await asyncio.sleep(0.05)
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://127.0.0.1:{port}/api/v1/internal/sites/default-site/telemetry",
                headers={"Authorization": "Bearer " + token},
                json={"messageId": "smoke-only", "metrics": [{"metricId": "co", "value": 0}]},
            )
            response.raise_for_status()
        event = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        assert event["type"] == "snapshot.updated" and event["sequence"] == 1
        assert event["payload"]["metrics"][0]["value"] == 0


def main():
    with tempfile.TemporaryDirectory(prefix="zfxzg-smoke-") as root:
        cfg = Settings(_env_file=None, app_env="test", test_database_url="sqlite:///" + root + "/smoke.db")
        database = Database(cfg)
        database.migrate()
        password = secrets.token_urlsafe(18)
        token = secrets.token_urlsafe(32)
        with database.session() as db:
            seed(db, cfg)
            bootstrap_admin(db, "smoke", password)
        database.engine.dispose()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")}
        env.update(APP_ENV="test", TEST_DATABASE_URL=cfg.test_database_url, INGEST_TOKEN=token)
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}") as client:
                for _ in range(100):
                    try:
                        client.get("/health/ready").raise_for_status()
                        break
                    except httpx.HTTPError:
                        time.sleep(0.05)
                response = client.post("/api/v1/auth/login", json={"username": "smoke", "password": password})
                response.raise_for_status()
                assert client.get("/api/v1/sites/default-site/snapshot").status_code == 200
                asyncio.run(websocket_smoke(port, "session=" + client.cookies.get("session"), token))
                result = client.post(
                    "/api/v1/auth/logout", headers={"X-CSRF-Token": response.json()["csrfToken"]}
                )
                assert result.status_code == 204
                assert client.get("/api/v1/auth/session").status_code == 401
            print("TCP烟测通过：健康、登录、Cookie、HTTP入库、WebSocket、注销；仅临时SQLite")
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
