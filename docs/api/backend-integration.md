# 后端联调指南（第三版契约与调试实现）

## 交付与边界

前端在 `frontend/`，后端在 `backend/` 独立实现。机器可读契约为 `openapi.yaml`（JSON格式的合法YAML），SDK为 `frontend/src/sdk/`。接口变化需同步修改契约、SDK与文档。

传感器→PLC→DTU→MQTT→服务器的上行已经由用户确认跑通。后续对接现有真实载荷，不需要从零验证链路。目前缺少脱敏主题/消息、完整PLC地址表、下行回读和视频播放资料，不据旧代码猜测。

MQTT主题/载荷、PLC寄存器与地址基准/数据类型/字节序/倍率、DTU配置、ONVIF发现/转流均属于后端及现场适配。浏览器不直连MQTT、PLC或ONVIF，也不包含模型密钥。

## 启动与认证

1. 后端本机监听8080；前端从`.env.example`复制`.env`，填REST根URL与WS完整URL。未配置时使用同源`/api/v1`、`/ws`。
2. 浏览器请求会话、站点、能力、测点、快照和摄像头。没有后端时仍可查看8页空状态，不创造虚假身份/业务数据。
3. `POST /auth/login`返回Session，并设置session Cookie；Session必须包含user和csrfToken。SDK使用credentials:include，所有写请求（登录除外）附加X-CSRF-Token。
4. 401撤销界面写权限、关闭实时通道；403显示权限拒绝。管理员管理账号/参数，操作员执行获准控制与报警确认，只读账号不能写设备。AI会话需认证及aiEnabled。
5. Cookie生产使用HttpOnly、Secure、合适SameSite；跨域开发使用精确Origin白名单与凭据，不能搭配`*`。WS验证Origin、会话和站点权限。后端禁止停用最后一名管理员。

响应不得包含密码、哈希、MQTT凭据或模型令牌。注销必须实际撤销服务端会话。

## 最短实现路径

- 先实现`/auth/*`、`/sites`和站点`/capabilities`、`/metrics`、`/snapshot`。映射真实载荷和20项测点；单位未知给null，不合并地址04/06温湿度。
- 能力默认保守：controlEnabled、parametersWritable、alarmAcknowledge、aiEnabled仅在服务可用时true。历史范围/聚合以真实清单返回，未支持返回空数组。
- 实现历史、视频、报警/日志分页。页码从1开始，pageSize默认20，total未知可null。日期过滤闭区间，from晚于to返回422；趋势每条曲线独立时间戳，缺测value:null，不补零。
- 取得真实PLC/DTU读写定义、保护边界、模式优先级，并确认下行及回读后才启用controlEnabled。离线自动控制要求由PLC实现，前端不替代PLC保护。
- 接WS事件并按订阅连接连续编号，重连/跳号刷新快照；AI最终结果必须可从会话消息接口恢复。

## 控制与参数

示例仅说明形状，不代表已有可用动作：

```json
{"actuatorId":"<能力接口设备ID>","action":"<能力接口动作ID>","parameters":{},"expectedVersion":"<最新状态版本>"}
```

控制POST与参数PATCH必须带Idempotency-Key（本次UUID）与X-CSRF-Token。相同键相同载荷返回同一指令，相同键不同载荷409；幂等保存期覆盖指令生命周期和客户端追查窗口。

- 202+CommandReceipt只表示受理，不代表现场动作完成；前端轮询指令并接WS。
- 后端重复检查身份、角色、站点、动作能力、现场/远程优先级、状态版本及PLC联锁/保护。
- succeeded必须含实际readbackAt；只有发送成功而未回读不能算成功。超时或网络失败为unknown，前端不自动重试/重发。
- 参数检查min/max/step/unit/writable/version及PLC范围；管理员二次确认后提交，仍需跟踪回读。
- AI controlIntent仅携带意图，跳控制页重新匹配站点/设备/能力后确认。模型不能直接驱动PLC。

## 视频与AI

摄像头只返回可播放HLS/MP4地址；ONVIF不是网页视频格式。hls.js支持MSE浏览器，Safari优先原生HLS。后端负责转流、CORS/MIME、播放授权、地址有效期；未配置playbackUrl:null。签名URL仅运行时使用，不进日志/知识库/提交。

消息POST返回`{messageId,userMessage}`，userMessage是服务端确认的用户记录。助手以ai.delta追加文本，ai.completed给完整ChatMessage，全部携带sessionId防串会话。includeContext由用户选择，后端仅附本站已授权数据，保留质量/时间。模型与部署方案不由本阶段指定。

## 错误与验收

错误统一`{code,message,details?,requestId?}`：400格式、401会话、403拒绝、404不存在、409版本/幂等冲突、422业务校验、429限流、500/503服务错误。message不得泄露堆栈、密钥或签名URL。

- 无后端：8页可打开、20值null、控制禁用、登录错误明确。
- 数据：0/false有效，缺失不抹掉其他值，过期值有标识，动态单位/来源正确。
- 实时：断线、重连、序号跳跃、会话失效和查询刷新。
- 控制：重复点击只发一次；202仍等待；拒绝/409不算成功；无回读超时unknown；AI建议仍需确认。
- 视频/AI：未配置空状态、播放错误和流中断。真实设备、模型、视频与多棚后续联调。

本阶段仅本地验证，不连接生产服务器、不改PLC/DTU、不下发实体动作。

## 当前后端实现边界（2026-11-04）

`backend/` 已按本契约实现可部署调试服务：MySQL 自动建表、Cookie/CSRF 三角色、20项测点、历史曲线、报警/日志、控制命令幂等和回读跟踪、AI 流式会话、WebSocket、受令牌保护的 telemetry/feedback/alarm 接入。默认控制能力为 false；只在 `debug-site` 沙箱对数据库做本地动作，不连接 PLC。默认 AI/MQTT/视频也未配置。

实体控制只有在协议已确认、站点已标记 `controlVerified`、控制网关与新鲜现场回读均具备时才会被能力接口开启。网关 HTTP 2xx 只算送达；实际成功必须通过 feedback 接口回读。服务重启、网关通信异常和超时均转 `unknown`，不会自动重发。缺少真实消息映射、寄存器表、下行主题和视频转流资料时，后端不会猜测。

## v0.3.0 只读监测与独立终端

新增GET `/sites/{siteId}/monitoring`、POST `/sites/{siteId}/mode`（当前固定403）、GET `/auth/sessions`、DELETE `/auth/sessions/{sessionId}`。会话Cookie不含Expires/Max-Age，服务端最长12小时；各终端独立登录/撤销。管理员查看全部活跃会话，普通账号仅自己。升级旧会话需重新登录。具体来源、缺测和映射开关见`backend/MONITORING.md`与OpenAPI；数据库v2采用新增表，保留账号、历史和配置。新增读取仍为功能码03，远程模式写入、实体动作未启用。

### 故障极性更正

记录时间：2026-11-09T00:38:11+08:00。用户现场反馈优先于原图片标题：D1000…D2700为0正常/1故障，其他及过期未知；旧规则事件保留关闭说明、无设备恢复时间。其余ACK/恢复/断线语义不变。
