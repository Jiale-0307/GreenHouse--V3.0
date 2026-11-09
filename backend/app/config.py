from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: Literal["development", "production", "test"] = "development"
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "zfxzg"
    db_user: str = "zfxzg"
    db_password: SecretStr = SecretStr("")
    db_ssl_ca: str | None = None
    # SQLite 只供隔离测试；部署始终使用用户的 MySQL，不静默回退。
    test_database_url: str | None = None
    auto_migrate: bool = True
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_name: str = "session"
    session_hours: int = Field(default=12, ge=1, le=12)
    docs_enabled: bool = True
    stale_after_seconds: int | None = Field(default=None, ge=1)
    command_timeout_seconds: int = Field(default=30, ge=2, le=300)
    max_history_days: int = Field(default=31, ge=1, le=366)
    max_trend_points: int = Field(default=10000, ge=100, le=100000)
    ingest_token: SecretStr = SecretStr("")
    enable_debug_control: bool = False
    control_enabled: bool = False
    control_protocol_confirmed: bool = False
    control_gateway_url: str = ""
    control_gateway_token: SecretStr = SecretStr("")
    ai_base_url: str = ""
    ai_api_key: SecretStr = SecretStr("")
    ai_model: str = ""
    ai_timeout_seconds: int = Field(default=60, ge=5, le=75)
    mqtt_enabled: bool = False
    mqtt_host: str = ""
    mqtt_port: int = 8883
    mqtt_username: str = ""
    mqtt_password: SecretStr = SecretStr("")
    mqtt_tls: bool = True
    mqtt_ca: str | None = None
    mqtt_client_id: str = "zfxzg-backend"
    mqtt_qos: int = Field(default=0, ge=0, le=2)
    mqtt_mapping_file: str = "config/mqtt.json"
    # 与JSON订阅开关独立；本模式仅发布Modbus 03读取请求。
    mqtt_modbus_enabled: bool = False
    mqtt_modbus_config_file: str = "config/modbus-mqtt.json"

    @field_validator("db_ssl_ca", "mqtt_ca", mode="before")
    @classmethod
    def blank_optional_paths(cls, value):
        return value or None

    @cached_property
    def origins(self):
        return [v.strip().rstrip("/") for v in self.allowed_origins.split(",") if v.strip()]

    @property
    def database_url(self):
        if self.test_database_url:
            return self.test_database_url
        return URL.create(
            "mysql+pymysql",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"charset": "utf8mb4"},
        )

    @property
    def ai_ready(self):
        return bool(self.ai_base_url and self.ai_model)

    @property
    def gateway_ready(self):
        return bool(
            self.control_enabled
            and self.control_protocol_confirmed
            and self.control_gateway_url
            and self.control_gateway_token.get_secret_value()
        )

    @model_validator(mode="after")
    def validate_deployment(self):
        if self.test_database_url and self.app_env != "test":
            raise ValueError("TEST_DATABASE_URL 仅允许 APP_ENV=test")
        if "*" in self.origins or not self.origins:
            raise ValueError("ALLOWED_ORIGINS 必须为精确来源白名单")
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("SameSite=None 要求 COOKIE_SECURE=true")
        if self.app_env == "production" and not self.cookie_secure:
            raise ValueError("生产环境要求 HTTPS 与 COOKIE_SECURE=true")
        if self.ingest_token.get_secret_value() and len(self.ingest_token.get_secret_value()) < 32:
            raise ValueError("INGEST_TOKEN 至少32字符")
        if self.mqtt_enabled and (not self.mqtt_host or not Path(self.mqtt_mapping_file).is_file()):
            raise ValueError("启用 MQTT 前必须配置主机和映射文件")
        if self.mqtt_modbus_enabled:
            if not self.mqtt_host or not Path(self.mqtt_modbus_config_file).is_file():
                raise ValueError("启用 Modbus MQTT 前必须配置主机和读取配置文件")
            if self.stale_after_seconds is None:
                raise ValueError("Modbus轮询必须设置 STALE_AFTER_SECONDS，避免断线后旧值一直显示正常")
        if self.control_enabled and not self.gateway_ready:
            raise ValueError("启用实体控制必须确认协议并配置网关及令牌")
        return self
