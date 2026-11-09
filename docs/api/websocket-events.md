# WebSocket 实时契约 v0.1.0

后端在 `/ws` 接受连接，使用同源 HttpOnly 会话 Cookie 认证，并检查 `Origin` 与站点权限。地址由 `VITE_WS_URL` 指定。没有真实会话时前端不连接实时通道。

连接成功后客户端发送：

```json
{"type":"subscribe","siteId":"default-site","topics":["snapshot.updated","alarm.updated","command.updated","ai.delta","ai.completed","ai.error"]}
```

服务端包络为 `{type,siteId,sequence,emittedAt,payload}`：

- `sequence`：本站点、当前订阅连接内单调递增整数；仅计入发给该订阅者的事件。重连开始新序列。
- `emittedAt`：带时区 ISO 8601。
- `payload`：下列具体类型，字段定义与 OpenAPI 同名 schema 一致。

## 事件

- `snapshot.updated`：`payload` 为完整 `Snapshot`。前端收到通知后重新拉取快照，避免部分补丁覆盖未变化读数；缺失测点保留旧值并标为过期。
- `alarm.updated`：`payload` 为 `Alarm`。刷新报警分页与总览统计。
- `command.updated`：`payload` 为 `CommandReceipt`。刷新指令查询、设备快照；只有 `succeeded` 且 `readbackAt != null` 才显示“已执行”。
- `ai.delta`：`{sessionId,messageId,delta}`。`delta` 为追加文本，按序拼接；不是全量替换。
- `ai.completed`：`{sessionId,message:ChatMessage}`。最终消息以完整消息替换流式缓存，`controlIntent` 只进入待确认卡。
- `ai.error`：`{sessionId,messageId?,code,error}`。结束等待并提示错误，禁止自动执行或重发消息。

## 断连与恢复

前端指数退避重连（1、2、4、8、15秒上限），重连重新订阅并刷新该站点所有查询。重复/乱序序号丢弃，跳号触发重新查询；AI最终消息在会话消息接口可恢复。未收到AI终止事件90秒时退出等待并刷新会话。

控制请求只通过 REST 提交，断连不重放指令。会话过期关闭通道，重新登录后恢复订阅。后端不得把相同指令消息当作新动作重复下发。

## v0.3.0 监测扩展

`snapshot.updated.payload.monitoring`与GET monitoring同构，逐通道携带receivedAt。前端90秒过期后显示未知，不能以WebSocket在线代替PLC新鲜度。`metrics[].evidence`携带双路good/degraded/missing/unconfirmed与本轮sources；双路失败时读数receivedAt不推进，attemptedAt推进，历史断点为null。`alarm.updated`增加source、acknowledgedAt、recoveredAt，确认不等于恢复。会话失效WS关闭码4401，前端停止重连、清除缓存并进入登录页。

### 故障极性更正

记录时间：2026-11-09T00:38:11+08:00。用户现场反馈优先于原图片标题：D1000…D2700为0正常/1故障，其他及过期未知；旧规则事件保留关闭说明、无设备恢复时间。其余ACK/恢复/断线语义不变。
