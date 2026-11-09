# 数据字段与空值规则

完整机器可读定义见 `openapi.yaml` 的 `components.schemas`；TypeScript镜像为 `frontend/src/sdk/types.ts`。

## 时间与事实值

- 业务字段未知必须使用 `null`，不能用0、false、空字符串或假时间代替；0与false是合法事实值。
- 空列表 `[]` 表示已查询且没有记录。未收到统计/列表时显示 `null`；后端明确统计为0才显示0。
- `observedAt` 为传感器/PLC采集时间，`receivedAt` 为服务端接收时间；不能假设二者相同。
- ISO 8601带时区传输；前端时间文本使用 `Asia/Shanghai`，精确到秒并注明 `+08:00`。
- `quality` 为 `good / stale / invalid / unknown`；已过期仍保留最后值并标识“过期”，无效值显示 `null`。
- `staleAfterSeconds` 由能力接口提供，不猜测设备上传周期。未知时前端不自行假定过期阈值。

## 原20项与新增紫外线指数（定义，不是模拟数据）

稳定前端ID与来源：

- 地址01：`co` 一氧化碳。
- 地址02：`uv` 紫外线。
- 地址03：`oxygen` 氧气。
- 地址04四合一：`co2` 二氧化碳、`light` 光照、`inside-temp-04` 空气温度、`inside-humidity-04` 空气湿度。
- 地址05：`outside-pressure` 棚外气压、`outside-temp` 棚外温度、`outside-humidity` 棚外湿度。
- 地址06：`inside-pressure` 棚内气压、`inside-temp-06` 空气温度、`inside-humidity-06` 空气湿度。
- 土壤七合一：`soil-temp` 温度、`soil-humidity` 湿度、`soil-ph` pH、`soil-ec` 电导率、`soil-n` 氮、`soil-p` 磷、`soil-k` 钾。

新增 `uv-index` 紫外线指数，对应用户本轮图片 D416。原有20项ID保持兼容。18个已确认读取地址见 `backend/MQTT-SENSORS.md`；后端来源说明附带PLC D地址。氧气与两组气压的同名地址差异待资料，当前不自动映射。地址420/422等是PLC寄存器，与原传感器RS485地址不是同一概念。

所有单位初始为 `null`，待真实资料确认。地址04与地址06温湿度独立，禁止合并。上述地址是已记载的传感器标识，不是PLC寄存器或新配置。

`GET /sites/{siteId}/metrics` 返回动态名称、来源、分组、单位、顺序与 enabled；后端定义优先。能力未返回时本地清单仅用于空状态排版。

## 执行机构、参数与能力

8类执行机构是资料记载的类别，不等于仅有8个物理设备。后端返回实际 `Actuator[]`，每个独立 `id/siteId/version`。

`actions[]` 是后端认可的无参数动作清单；前端不内置on/off、方向或范围。`set_mode` 为统一模式动作，仅在 `modeWritable` 时显示可用，参数为 `{mode:'manual'|'auto'}`。其他带参数意图仍由后端校验。

`Capabilities` 提供 controlEnabled、parametersWritable、alarmAcknowledge、aiEnabled、historyRanges、aggregations、新鲜度与控制等待时长。任何未确认能力默认不可写。

参数 `Parameter` 必须有名称、value/unit/min/max/step/writable/version；前端管理员写入要求单位、范围、步长和版本均已定义。`expectedVersion` 冲突返回409。

## 指令状态

- `accepted`：后端已受理，尚不能证明下发或现场执行。
- `executing`：执行中，等待后端确认与实际回读。
- `succeeded`：只有同时存在 `readbackAt` 才显示“已执行·已回读”。
- `rejected`：后端明确拒绝。
- `unknown`：结果未知，不能自动重发。

`result` 为可显示的结果说明，不得含凭据/上游签名URL。`Idempotency-Key`标识同一次写请求，服务端必须去重，写操作前端不自动重试。
