"""MQTT仅订阅，映射由实际DTU载荷提供；不包含任何publish或PLC写入。"""

import json
import logging
import math

import paho.mqtt.client as mqtt
from pydantic import Field

from . import models as m
from .core import timestamp
from .ingestion import telemetry
from .schemas import Identifier, Input, Telemetry

logger = logging.getLogger("zfxzg")
MISSING = object()


class MappingMetric(Input):
    metricId: Identifier
    path: list[str | int] = Field(min_length=1)
    scale: float = 1
    offset: float = 0


class Subscription(Input):
    topic: str = Field(min_length=1)
    siteId: Identifier
    messageIdPath: list[str | int] | None = None
    observedAtPath: list[str | int] | None = None
    metrics: list[MappingMetric] = Field(min_length=1)


class Mapping(Input):
    subscriptions: list[Subscription] = Field(min_length=1)


def lookup(payload, path):
    value = payload
    for segment in path:
        if isinstance(value, dict) and isinstance(segment, str) and segment in value:
            value = value[segment]
        elif isinstance(value, list) and type(segment) is int and 0 <= segment < len(value):
            value = value[segment]
        else:
            return MISSING
    return value


def normalize(payload, mapping):
    observed = None
    if mapping.observedAtPath:
        observed = lookup(payload, mapping.observedAtPath)
        if observed is MISSING or not isinstance(observed, str):
            raise ValueError("observed_time_missing")
        observed = timestamp(observed)
    message_id = m.uid()
    if mapping.messageIdPath:
        message_id = lookup(payload, mapping.messageIdPath)
        if type(message_id) not in (str, int):
            raise ValueError("message_id_missing")
        message_id = str(message_id)
    metrics = []
    for item in mapping.metrics:
        raw = lookup(payload, item.path)
        if raw is MISSING:
            continue
        quality, value = "good", None
        # bool不是物理数值；非法值显式形成缺测，不把它变成0。
        if type(raw) not in (int, float) or not math.isfinite(raw):
            quality = "invalid"
        else:
            value = raw * item.scale + item.offset
            if not math.isfinite(value):
                value, quality = None, "invalid"
        metrics.append(dict(metricId=item.metricId, value=value, quality=quality, observedAt=observed))
    return Telemetry(messageId=message_id, metrics=metrics)


class MqttIngestor:
    def __init__(self, app):
        self.app = app
        cfg = app.state.settings
        with open(cfg.mqtt_mapping_file, encoding="utf-8") as source:
            mapping = Mapping.model_validate(json.load(source))
        if len({s.topic for s in mapping.subscriptions}) != len(mapping.subscriptions):
            raise ValueError("MQTT主题映射重复")
        self.subscriptions = {s.topic: s for s in mapping.subscriptions}
        if any("+" in topic or "#" in topic for topic in self.subscriptions):
            raise ValueError("MQTT映射必须为精确主题")
        self.connected = False
        self.accepted = self.rejected = 0
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cfg.mqtt_client_id)
        if cfg.mqtt_username:
            self.client.username_pw_set(cfg.mqtt_username, cfg.mqtt_password.get_secret_value())
        if cfg.mqtt_tls:
            self.client.tls_set(ca_certs=cfg.mqtt_ca)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.reconnect_delay_set(1, 30)

    def start(self):
        cfg = self.app.state.settings
        self.client.connect_async(cfg.mqtt_host, cfg.mqtt_port, keepalive=60)
        self.client.loop_start()

    def stop(self):
        self.client.disconnect()
        self.client.loop_stop()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self.connected = not reason_code.is_failure
        if self.connected:
            for topic in self.subscriptions:
                client.subscribe(topic, qos=self.app.state.settings.mqtt_qos)

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False

    def on_message(self, client, userdata, message):
        try:
            if len(message.payload) > 262144:
                raise ValueError("payload_limit")
            mapping = self.subscriptions[message.topic]
            body = normalize(json.loads(message.payload), mapping)
            with self.app.state.db.session() as db:
                telemetry(db, mapping.siteId, body, self.app.state.settings)
            self.accepted += 1
        except Exception as exc:
            self.rejected += 1
            logger.warning("mqtt_message_rejected type=%s", type(exc).__name__)
