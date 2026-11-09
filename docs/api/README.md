# 第三版前端对接文档

> 本目录描述第三版前后端契约，当前OpenAPI0.3.0共30路径。前后端与真实MQTT上行已部署；新增独立终端会话、模式/输出/18故障/电表原始块和双路证据。PLC换算、电表物理映射、实体下行/回读、视频和模型仍有待确认项，见[监测说明](../../backend/MONITORING.md)。

## 文档

- [OpenAPI](./openapi.yaml)：REST 路径、请求响应、错误和鉴权。
- [WebSocket 事件](./websocket-events.md)：实时快照、告警、控制回读与 AI 流式消息。
- [字段字典](./field-dictionary.md)：站点、测点、质量、执行机构和控制状态。
- [后端联调指南](./backend-integration.md)：实现顺序、适配边界、脱敏示例和验收清单。

## 前端 SDK

```ts
import { ApiClient, RealtimeClient } from './src/sdk';
const api = new ApiClient(import.meta.env.VITE_API_BASE_URL);
const snapshot = await api.snapshot('default-site');
const ws = new RealtimeClient(import.meta.env.VITE_WS_URL!);
ws.connect('default-site', event => console.log(event), console.log, () => api.snapshot('default-site'));
```

所有时间使用 ISO 8601，展示层转换为 `Asia/Shanghai (+08:00)`。`null` 表示服务端没有可用事实值；合法的 `0`、`false` 和空数组不能被前端改成 `null`。写请求不自动重试；`POST /commands` 必须带 `Idempotency-Key`。

## 已实现后端调试版

`backend/` 已提供FastAPI服务，原有路径保持兼容，当前共30路径。服务启动时对已配置的MySQL执行增量迁移v2，不删除或重置已有数据；首次管理员通过 `python -m app.cli create-admin` 交互创建，既有部署无需重新初始化账号。

默认配置不启用MQTT和实体控制；当前服务器已显式启用功能码03只读轮询，实体控制仍关闭。`ENABLE_DEBUG_CONTROL=true`只创建无实体动作的独立调试沙箱，不代表现场能力。参见 [`backend/README.md`](../../backend/README.md)。
