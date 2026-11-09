# MQTT / Modbus TCP 传感器接入

本轮用户确认：Broker 位于已部署服务器，端口1883、无TLS/账号密码；请求主题 `dtu/down`，回包主题 `dtu/up`。DTU接收**二进制帧**，不是ASCII文本。用户名和密码在后端 `.env` 中预留，不能填入前端。

本版只发送功能码03读取，不改变PLC或DTU配置，不实现设备动作或写寄存器。

## 已接入范围

18个明确地址，均按从站01、两个保持寄存器、IEEE754单精度浮点且16位字交换读取。D402的用户样例已确认约为23.4；其余读数沿用相同PLC浮点存储方式，现场数值/单位仍需与仪表核对。

- 土壤：D400含水率、D402温度、D404电导率、D406 pH、D408氮、D410磷、D412钾。
- 紫外线：D414强度、D416指数（本轮新增独立测点 `uv-index`）。
- 四合一：D430空气湿度、D432空气温度、D434 CO₂、D436光照。
- 棚外：D440湿度、D442温度。
- 棚内温湿压：D450湿度、D452温度。
- D460一氧化碳。

原20项定义加紫外线指数共21项；氧气、棚外气压、棚内气压继续显示未接收。按用户要求，D420/D422、D444/D446、D454/D456的同名差异、D462肥力值与D470待具体文档，不发送这些地址。单位不靠数值猜测，未配置时仍为空。

## 服务器配置

服务目录 `/opt/zfxzg/backend`。现有EMQX与后端同在 `1panel-network`，后端可使用容器名 `EMQX` 通过内网连接，等同于服务器公开的Broker。

在后端 `.env` 中设置（保留原有数据库和其他配置）：

```dotenv
MQTT_ENABLED=false
MQTT_MODBUS_ENABLED=true
MQTT_MODBUS_CONFIG_FILE=/app/config/modbus-mqtt.json
MQTT_HOST=EMQX
MQTT_PORT=1883
MQTT_TLS=false
MQTT_USERNAME=
MQTT_PASSWORD=
MQTT_QOS=0
STALE_AFTER_SECONDS=90
```

`MQTT_ENABLED` 是原有JSON字段订阅器，与本次原始Modbus轮询开关不同。不要把它也打开并重复写同一测点。

复制 `examples/modbus-mqtt.json` 到服务器 `config/modbus-mqtt.json`，现场参数核对后将 `transportConfirmed` 改为true。当前已部署设置为10秒轮询周期、3秒单次等待和0.1秒请求间隔。每轮串行读取18项，正常时同一测点约10秒更新一次；一轮耗时超过10秒则完成后开始下一轮，不叠加请求。PLC内部采集周期仍由PLC程序决定，不等于服务器读取周期。

先离线查看生成的读取帧，此命令不连接MQTT和数据库：

```sh
cd /opt/zfxzg/backend
docker compose run --rm backend python -m app.cli preview-modbus --file /app/config/modbus-mqtt.json
```

更新镜像后重建容器以加载环境变量：

```sh
docker compose up -d --force-recreate
```

后续启用Broker认证时，只在服务器 `.env` 私下填写 `MQTT_USERNAME/MQTT_PASSWORD`，并重建容器；不要把真实配置文件发给聊天或提交仓库。

## 请求与回包

D402使用十进制402，即0x0192，不减1：

```text
请求：00 01 00 00 00 06 01 03 01 92 00 02
回包：00 01 00 00 00 07 01 03 04 33 33 41 BB
数值：33 33 41 BB → 41 BB 33 33 → 约23.4
```

事务号由后端递增生成，每次请求会不同；后端等待订阅确认后开始读取，一次只等待一个请求，回包必须匹配事务号、从站、功能码、MBAP长度和字节数量。Modbus TCP帧不加RTU CRC。

`requestEncoding: "raw"` 表示发送二进制，是本DTU的实际配置。`hex` 仅供发送ASCII十六进制的其他设备。`json_hex` 支持按现场JSON模板及字段路径包装，必须同时提供 `requestJson/requestHexPath`；不能凭空假定DTU支持JSON。

`responseEncoding: "auto"` 接受原始二进制或十六进制文本（含分组空格）；也可明确指定 `raw/hex`。JSON回包需使用 `json_hex` 并填写 `responseHexPath`。实际DTU帧在联调时核对。

功能码固定03；当前也支持显式配置 `float_big_endian/uint16/int16/uint32`、倍率和偏移，仅供后续有资料的设备使用，不是本轮任意更换类型的依据。

## 网页和诊断

与后端同源部署的前端使用 `npm run build:same-origin` 构建，避免本机 `.env` 的localhost调试地址进入线上文件；把 `frontend/dist` 部署到站点静态目录。更新后刷新页面并登录。

收到合法回包后自动保存MySQL最新值和历史记录，经现有 `snapshot.updated` WebSocket事件逐项刷新网页，无需手动刷新；总览历史曲线每10秒重新查询。Modbus回包没有采集时间，所以 `observedAt=null`，服务器单独保存 `receivedAt`；页面悬停可查看接收时间。读数不变时仍可通过接收时间推进判断新回包。

为控制系统盘I/O，内部事件表只存小型快照引用，WS发送前按最新业务表组装完整快照；同一批通知可能携带同一份最新状态。历史采样仍逐项保存，不依赖通知表作为历史源；原有完整快照事件保持兼容。事件通知按原1天规则分批维护，不清理历史采样。

请求使用QoS0且retain=false，断线期间不排队旧读请求。历史retained消息、非本轮事务、错误长度、重复消息均拒绝；超时保留最后值，90秒后网页显示过期。非法NaN/Infinity记为无效null，不当成0。

管理员登录后，`GET /api/v1/diagnostics` 的 `modbusMqtt` 可查看连接/订阅状态、发布/接收/拒绝/超时计数、最后回包时间和脱敏错误码；不返回认证凭据。`mqtt` 区域是原有JSON订阅器，关闭时不影响本轮轮询。

停用采集只需将 `.env` 的 `MQTT_MODBUS_ENABLED=false` 后重建容器；不删除历史读数或数据库表。

## 新版读取范围

记录时间：2026-11-09T00:38:11+08:00。上述18项首版接入为历史范围；本次已扩展到42只读请求，包含双路原始证据、模式/输出/故障/电表块，详情与待确认项见[MONITORING.md](MONITORING.md)。不能继续按旧段落认为D420等从未读取。
