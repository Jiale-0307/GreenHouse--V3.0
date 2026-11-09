"""关系表保留关键查询列；JSON 仅用于能力、动作参数和事件载荷。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """MySQL DATETIME 不携带时区，统一存 UTC，API 再明确输出 +08:00。"""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        # 微秒是版本/新鲜度比较的一部分，MySQL默认DATETIME秒精度会截断它。
        return dialect.type_descriptor(DATETIME(fsp=6) if dialect.name == "mysql" else DateTime())

    def process_bind_param(self, value, dialect):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value else None

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value else None


class Base(DeclarativeBase):
    pass


class SchemaVersion(Base):
    __tablename__ = "schema_version"
    version: Mapped[int] = mapped_column(primary_key=True)


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    is_debug: Mapped[bool] = mapped_column(Boolean, default=False)
    control_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Session(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


class SessionDevice(Base):
    """独立公开ID用于撤销会话，不向浏览器暴露会话令牌或其哈希。"""

    __tablename__ = "session_devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    token_hash: Mapped[str] = mapped_column(
        ForeignKey("auth_sessions.token_hash", ondelete="CASCADE"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    user_agent: Mapped[str] = mapped_column(String(256), default="")


class PlcState(Base):
    """只保存当前只读通道快照；故障事件和测量历史另行持久化。"""

    __tablename__ = "plc_states"
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class MetricEvidence(Base):
    __tablename__ = "metric_evidence"
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), primary_key=True)
    metric_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    sources: Mapped[list] = mapped_column(JSON, default=list)
    attempted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class AlarmLifecycle(Base):
    __tablename__ = "alarm_lifecycles"
    alarm_id: Mapped[str] = mapped_column(ForeignKey("alarms.id"), primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    recovered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Metric(Base):
    __tablename__ = "metric_definitions"
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    group_name: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(100))
    unit: Mapped[str | None] = mapped_column(String(32))
    display_order: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    value: Mapped[float | None] = mapped_column(Double)
    quality: Mapped[str] = mapped_column(String(16), default="unknown")
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    received_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Sample(Base):
    __tablename__ = "metric_samples"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"))
    metric_id: Mapped[str] = mapped_column(String(64))
    value: Mapped[float | None] = mapped_column(Double)
    quality: Mapped[str] = mapped_column(String(16))
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # 没有采集时间时，历史轴使用接收时间；不伪造 observed_at。
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime)
    __table_args__ = (Index("ix_samples_site_metric_time", "site_id", "metric_id", "timestamp"),)


class Actuator(Base):
    __tablename__ = "actuators"
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(64))
    state: Mapped[object | None] = mapped_column(JSON, nullable=True)
    mode: Mapped[str | None] = mapped_column(String(16))
    version: Mapped[str] = mapped_column(String(64), default=uid)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    mode_writable: Mapped[bool] = mapped_column(Boolean, default=False)
    remote_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    interlock_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Parameter(Base):
    __tablename__ = "parameters"
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    value: Mapped[float | None] = mapped_column(Double)
    unit: Mapped[str | None] = mapped_column(String(32))
    minimum: Mapped[float | None] = mapped_column(Double)
    maximum: Mapped[float | None] = mapped_column(Double)
    step: Mapped[float | None] = mapped_column(Double)
    writable: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[str] = mapped_column(String(64), default=uid)
    feedback_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Camera(Base):
    __tablename__ = "cameras"
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    playback_url: Mapped[str | None] = mapped_column(Text)
    protocol: Mapped[str | None] = mapped_column(String(16))
    online: Mapped[bool | None] = mapped_column(Boolean)


class Alarm(Base):
    __tablename__ = "alarms"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), index=True)
    level: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="open")
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    detail: Mapped[str | None] = mapped_column(Text)
    can_acknowledge: Mapped[bool] = mapped_column(Boolean, default=True)


class OperationLog(Base):
    __tablename__ = "operation_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), index=True)
    actor: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16))
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now, index=True)
    result: Mapped[str | None] = mapped_column(Text)


class Command(Base):
    __tablename__ = "commands"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(36))
    payload_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    kind: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="accepted", index=True)
    accepted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    readback_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    result: Mapped[str | None] = mapped_column(Text)
    log_id: Mapped[str] = mapped_column(ForeignKey("operation_logs.id"))
    __table_args__ = (UniqueConstraint("site_id", "user_id", "idempotency_key", name="uq_command_key"),)


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(100), default="新会话")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    busy: Mapped[bool] = mapped_column(Boolean, default=False)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    control_intent: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Event(Base):
    __tablename__ = "realtime_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36))
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
    emitted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class IngestReceipt(Base):
    __tablename__ = "ingest_receipts"
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


# 明确使用事务引擎与区分大小写的标识符，避免依赖服务器的默认排序规则。
for _table in Base.metadata.tables.values():
    _table.dialect_options["mysql"].update(engine="InnoDB", charset="utf8mb4", collate="utf8mb4_bin")
