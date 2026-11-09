"""维护后端扩展契约；原有前端路径及schema保持原样。无网络或数据库访问。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import schemas as s

path = Path(__file__).resolve().parents[2] / "docs/api/openapi.yaml"
contract = json.loads(path.read_text())


def openapi3(value):
    if isinstance(value, list):
        return [openapi3(v) for v in value]
    if not isinstance(value, dict):
        return value
    value = {k: openapi3(v) for k, v in value.items()}
    options = value.get("anyOf")
    if options and {"type": "null"} in options:
        options = [v for v in options if v != {"type": "null"}]
        del value["anyOf"]
        value.update(options[0] if len(options) == 1 else {"anyOf": options})
        value["nullable"] = True
    return value


for model in [s.Telemetry, s.Feedback, s.AlarmInput, s.SiteConfig]:
    schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
    definitions = schema.pop("$defs", {})
    for name, definition in {**definitions, model.__name__: schema}.items():
        contract["components"]["schemas"][name] = openapi3(definition)
contract["components"]["securitySchemes"]["ingestBearer"] = {"type": "http", "scheme": "bearer"}
site_param = {"name": "siteId", "in": "path", "required": True, "schema": {"type": "string"}}
csrf = {"name": "X-CSRF-Token", "in": "header", "required": True, "schema": {"type": "string"}}
errors = {k: v for k, v in contract["paths"]["/sites"]["get"]["responses"].items() if k != "200"}
for suffix, model in [("telemetry", s.Telemetry), ("feedback", s.Feedback), ("alarms", s.AlarmInput)]:
    contract["paths"]["/internal/sites/{siteId}/" + suffix] = {
        "post": {
            "summary": "内部数据接入：" + suffix,
            "operationId": "ingest_" + suffix,
            "tags": ["internal"],
            "security": [{"ingestBearer": []}],
            "parameters": [site_param],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/" + model.__name__}}
                },
            },
            "responses": {
                "200": {
                    "description": "已接收（不代表现场动作完成）",
                    "content": {"application/json": {"schema": {"type": "object"}}},
                },
                **errors,
            },
        }
    }
contract["paths"]["/sites/{siteId}/configuration"] = {
    "put": {
        "summary": "管理员更新站点定义；按ID合并，不写现场状态",
        "operationId": "configure_site",
        "parameters": [site_param, csrf],
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/SiteConfig"}}},
        },
        "responses": {
            "200": {
                "description": "配置已保存",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["updated"],
                            "properties": {"updated": {"type": "boolean"}},
                        }
                    }
                },
            },
            **errors,
        },
    }
}
contract["paths"]["/diagnostics"] = {
    "get": {
        "summary": "管理员查看脱敏运行状态",
        "operationId": "diagnostics",
        "responses": {
            "200": {
                "description": "诊断状态",
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            **errors,
        },
    }
}


# 与SDK同步的只读监测响应；缺测使用null/unknown，不以零代替。
def obj(properties, required=None):
    return dict(type="object", properties=properties, required=required or list(properties))


def ref(name):
    return {"$ref": "#/components/schemas/" + name}


def arr(items):
    return dict(type="array", items=items)


string = {"type": "string"}
number = {"type": "number", "nullable": True}
time = {"type": "string", "format": "date-time"}
nullable_time = {**time, "nullable": True}
boolean = {"type": "boolean"}
integer = {"type": "integer"}
schemas = contract["components"]["schemas"]
schemas["MetricEvidence"] = obj(
    dict(
        status=dict(type="string", enum=["good", "degraded", "missing", "unconfirmed"]),
        attemptedAt=time,
        sources=arr(obj(dict(address=integer, raw=number, value=number, unit={**string, "nullable": True}))),
    )
)
schemas["MetricReading"]["properties"]["evidence"] = {**ref("MetricEvidence"), "nullable": True}
schemas["SiteMode"] = obj(
    dict(
        state=dict(type="string", enum=["auto", "manual", "stopped", "invalid", "unknown"]),
        raw=dict(type="array", items=integer, nullable=True),
        receivedAt=nullable_time,
        version=string,
        writable={"type": "boolean", "enum": [False]},
        disabledReason=string,
    )
)
schemas["PlcMonitoring"] = obj(
    dict(
        mode=ref("SiteMode"),
        outputs=arr(
            obj(
                dict(
                    id=string,
                    name=string,
                    address=integer,
                    state={**boolean, "nullable": True},
                    receivedAt=nullable_time,
                )
            )
        ),
        faults=arr(
            obj(
                dict(
                    id=string,
                    name=string,
                    address=integer,
                    state=dict(type="string", enum=["fault", "normal", "unknown"]),
                    raw={
                        **integer,
                        "nullable": True,
                        "description": "用户现场更正：0正常、1故障；其他或过期未知",
                    },
                    receivedAt=nullable_time,
                    activeAlarmId={**string, "nullable": True},
                )
            )
        ),
        meter=obj(
            dict(
                mappingConfirmed=boolean,
                status=dict(type="string", enum=["good", "unconfirmed", "unknown"]),
                rawRegisters=dict(type="array", items=integer, nullable=True),
                receivedAt=nullable_time,
                values=arr(obj(dict(metricId=string, name=string, unit=string, value=number))),
            )
        ),
    )
)
schemas["Snapshot"]["properties"]["monitoring"] = ref("PlcMonitoring")
if "monitoring" not in schemas["Snapshot"]["required"]:
    schemas["Snapshot"]["required"].append("monitoring")
schemas["Alarm"]["properties"].update(
    source={**string, "nullable": True}, acknowledgedAt=nullable_time, recoveredAt=nullable_time
)
schemas["TerminalSession"] = obj(
    dict(id=string, username=string, userAgent=string, createdAt=time, expiresAt=time, current=boolean)
)
schemas["ModeWrite"] = openapi3(s.ModeWrite.model_json_schema())


def operation(summary, operation_id, response_schema, parameters=None, success="200"):
    return dict(
        summary=summary,
        operationId=operation_id,
        parameters=parameters or [],
        responses={
            success: dict(description="成功", content={"application/json": {"schema": response_schema}}),
            **errors,
        },
    )


contract["paths"]["/auth/sessions"] = dict(
    get=operation(
        "活跃会话：管理员查看全部，其他账号仅查看自己", "terminal_sessions", arr(ref("TerminalSession"))
    )
)
contract["paths"]["/auth/sessions/{sessionId}"] = dict(
    delete=dict(
        summary="撤销自己或管理员选定的独立会话",
        operationId="revoke_terminal_session",
        parameters=[dict(name="sessionId", **{"in": "path"}, required=True, schema=string), csrf],
        responses={"204": dict(description="会话已撤销，其他独立会话继续有效"), **errors},
    )
)
contract["paths"]["/sites/{siteId}/monitoring"] = dict(
    get=operation(
        "整棚模式、10路输出、18路故障及电表缓冲区", "plc_monitoring", ref("PlcMonitoring"), [site_param]
    )
)
mode_operation = operation(
    "申请整棚模式切换；协议未确认，当前固定返回403",
    "set_site_mode",
    ref("CommandReceipt"),
    [site_param, csrf, dict(name="Idempotency-Key", **{"in": "header"}, required=True, schema=string)],
    "202",
)
mode_operation["requestBody"] = dict(
    required=True, content={"application/json": {"schema": ref("ModeWrite")}}
)
contract["paths"]["/sites/{siteId}/mode"] = dict(post=mode_operation)
contract["paths"]["/auth/login"]["post"]["description"] = (
    "每次登录生成独立随机会话。HttpOnly会话Cookie不含Max-Age/Expires，最长12小时；浏览器会话恢复可能恢复Cookie。"
)
contract["info"]["version"] = "0.3.0"
contract["info"]["description"] = (
    "第三版前后端契约；支持独立终端会话、PLC只读监测及故障闭环。氧气/气压转换、电表物理量和模式写入仍须确认；视频与AI需独立配置。"
)
path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n")
print("扩展契约已更新；原前端路径保持兼容")
