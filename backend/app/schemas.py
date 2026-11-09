from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, field_validator

Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")]
Number = StrictFloat | StrictInt
Role = Literal["admin", "operator", "viewer"]
Quality = Literal["good", "stale", "invalid", "unknown"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    @field_validator("*", mode="after")
    @classmethod
    def aware_times(cls, value):
        if isinstance(value, datetime) and value.utcoffset() is None:
            raise ValueError("时间必须包含时区")
        return value


class Login(Input):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class CreateUser(Login):
    username: Identifier
    password: str = Field(min_length=12, max_length=256)
    role: Role


class UpdateUser(Input):
    role: Role
    enabled: StrictBool


class Control(Input):
    actuatorId: Identifier
    action: Identifier
    parameters: dict = Field(default_factory=dict, max_length=20)
    expectedVersion: str = Field(min_length=1, max_length=64)


class ParameterWrite(Input):
    value: Number
    expectedVersion: str = Field(min_length=1, max_length=64)


class ModeWrite(Input):
    mode: Literal["auto", "manual", "stopped"]
    expectedVersion: str = Field(min_length=1, max_length=64)


class MessageInput(Input):
    content: str = Field(min_length=1, max_length=8000)
    includeContext: StrictBool


class MetricInput(Input):
    metricId: Identifier
    value: Number | None
    quality: Quality = "good"
    observedAt: datetime | None = None


class Telemetry(Input):
    messageId: str = Field(min_length=1, max_length=128)
    metrics: list[MetricInput] = Field(min_length=1, max_length=100)


class ActuatorFeedback(Input):
    actuatorId: Identifier
    state: StrictBool | str | Number | None
    mode: Literal["manual", "auto"] | None
    remoteAllowed: StrictBool
    interlockOk: StrictBool
    observedAt: datetime


class ParameterFeedback(Input):
    parameterId: Identifier
    value: Number | None
    observedAt: datetime


class Feedback(Input):
    commandId: str | None = Field(default=None, max_length=36)
    status: Literal["executing", "succeeded", "rejected", "unknown"] | None = None
    result: str | None = Field(default=None, max_length=500)
    actuators: list[ActuatorFeedback] = Field(default_factory=list, max_length=100)
    parameters: list[ParameterFeedback] = Field(default_factory=list, max_length=100)


class AlarmInput(Input):
    id: Identifier
    level: Literal["info", "warning", "critical"]
    title: str = Field(min_length=1, max_length=200)
    status: Literal["open", "closed"] = "open"
    occurredAt: datetime
    detail: str | None = Field(default=None, max_length=2000)
    canAcknowledge: StrictBool = True


class ActionInput(Input):
    id: Identifier
    label: str = Field(min_length=1, max_length=100)
    enabled: StrictBool = False


class ActuatorDefinition(Input):
    id: Identifier
    name: str = Field(min_length=1, max_length=100)
    kind: Identifier
    actions: list[ActionInput] = Field(default_factory=list, max_length=20)
    modeWritable: StrictBool = False


class ParameterDefinition(Input):
    id: Identifier
    name: str = Field(min_length=1, max_length=100)
    unit: str | None = Field(default=None, max_length=32)
    min: Number | None = None
    max: Number | None = None
    step: Number | None = None
    writable: StrictBool = False


class CameraDefinition(Input):
    id: Identifier
    name: str = Field(min_length=1, max_length=100)
    playbackUrl: str | None = Field(default=None, max_length=4096)
    protocol: Literal["hls", "mp4"] | None = None
    online: StrictBool | None = None


class MetricConfig(Input):
    id: Identifier
    unit: str | None = Field(default=None, max_length=32)
    enabled: StrictBool = True


class SiteConfig(Input):
    # 定义配置与现场回读分开；定义接口不能写入伪造的状态或读数。
    controlVerified: StrictBool | None = None
    metrics: list[MetricConfig] = Field(default_factory=list, max_length=100)
    actuators: list[ActuatorDefinition] = Field(default_factory=list, max_length=100)
    parameters: list[ParameterDefinition] = Field(default_factory=list, max_length=100)
    cameras: list[CameraDefinition] = Field(default_factory=list, max_length=100)
