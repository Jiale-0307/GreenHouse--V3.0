# Web改版与PLC只读监测

本轮包含统一深蓝界面、登录保护首页、设备SVG、双路测量证据、模式/输出/18路故障/电表缓冲区、报警生命周期和终端会话管理。数据结构迁移至v2，只新增4张表，原账号、配置、历史和报警保留。旧版本缺少终端元数据的会话需要重新登录。

## 已实现的读取边界

- 双路：氧气D420/D422，棚外气压D444/D446，棚内气压D454/D456；每组功能码03连续读4寄存器，两个float来自同一回包。字序由原配置决定；默认不额外除厂家倍率。
- `mappingConfirmed=false`时保存原始来源证据和历史缺口，平均值不发布。确认PLC转换、两路物理量和统一单位后，才能填写`unit`、两路`scale`/`secondScale`与`offset`并设为true。压力手册同时记载kPa和hPa，不能直接平均。只有一条有限浮点数时为degraded；都无效/超时时保留末次有效值及原接收时间，历史写null。迟到回包按事务号/时限拒绝。
- 四合一D432/D430是首页温湿度；温湿压D452/D450单独保留，禁止将两类传感器混作同一来源。
- 电表只读D270–D273共4寄存器，保留rawRegisters。厂家资料尚未提供0x2000起始区的物理映射，当前不推测电压、电流、功率或电量。确认后`meterFields`提供metricId（meter-前缀）、name、unit、offset、dataType、scale、offsetValue；禁止重叠或超出4寄存器。真实字段定义会创建测点并写历史，趋势页可选择。
- D900/D901：1/0自动，0/1手动，0/0停止，其余组合异常；超时/90秒过期未知。GET monitoring可读；POST mode始终拒绝MODE_WRITE_UNCONFIRMED。没有生成模式写帧或后端自动停机。
- D600–D609：风扇、加热、喷雾、滴灌、施肥、补光、棉被正/反转、卷帘正/反转。0/1表示PLC输出；其他值或过期未知；不代表机械到位。
- D1000至D2700每100一个共18故障点，顺序为上述10路输出、土壤、UV、氧气、CO₂四合一、棚外温湿压、棚内温湿压、CO、电表。按用户更正D2400棚外、D2500棚内。用户最新现场反馈“没有故障，全是0是对的”，优先于图片标题：改为0正常、1故障，其他/超时/过期未知。
- 故障首次1创建一条报警；连续1不重复，确认仅记录知悉；0恢复并记录时间，再次1新建事件；未知与断线均不恢复已有报警。数据库站点锁使确认和故障边沿串行。更正规则前产生的18条事件保留并标注“旧判定规则关闭”，不填写设备恢复时间，不删除历史。

离线升级配置（输出必须是新文件）：

```sh
python scripts/upgrade_monitoring.py --input config/modbus-mqtt.json --output config/modbus-mqtt.next.json
python -m app.cli preview-modbus --file config/modbus-mqtt.next.json
```

18个旧单值通道不变，新增24个只读请求。正常10秒开始一轮；串行总耗时超10秒顺延，单项超时3秒、间隔0.1秒，90秒过期。轮询独立于浏览器连接数。故障/输出只保存最新块，遥测通知继续采用小引用，不回写全棚快照，历史采样保留。

## 独立会话和接口

`GET /api/v1/auth/sessions`返回活跃终端，管理员可看全部，其他账号仅自己；`DELETE /auth/sessions/{id}`撤销自己或管理员选定的一端，需要CSRF。公开ID不是Cookie/令牌哈希。每次登录独立随机Cookie、HttpOnly、SameSite、非持久、最长12小时；不提供记住我。浏览器会话恢复可能保留Cookie。旧会话Cookie须重新登录以采用新语义。

未登录不挂载业务页、不发业务数据请求。HTTP401或WS4401清理查询缓存/保留值并断开实时连接。退出一端不撤销其他端。HTTP响应no-store及Vary Cookie/Origin，生产代理禁用API缓存，HTML入口不缓存；鉴权不依赖客户端提交身份。

`GET /sites/{siteId}/monitoring`及Snapshot.monitoring包含各通道接收时间、新鲜度、模式、故障和电表；MetricReading.evidence包含双路status/sources/attemptedAt；Alarm增加source/acknowledgedAt/recoveredAt。WS snapshot.updated/alarm.updated使用同一结构。见OpenAPI0.3.0与前端SDK。未确认的能力仍显示未配置/待确认。

## 设计来源

- 用户微信大屏参考：https://mp.weixin.qq.com/s/A8N29azkr7YqOtN4yt6VeA?scene=1&click_id=2 。参考三栏与趋势分区，不复用其演示数值。
- iF官方获奖页：Sandy, Trinity AgTech，iF DESIGN AWARD 2022，User Interface：https://ifdesign.com/en/winner-ranking/project/sandy-trinity-agtech/347900 。已核实奖项、年份并查看界面，参考农业空间示意、侧栏明细和数据优先的信息组织。未把其他未经证实的设计体系列为获奖案例。
- 设备示意依据项目实体结构，用本地SVG表示感知、独立水路及8类执行机构，节点位置为分区示意。

未完成的现场条件：氧气/气压的PLC转换及单位、电表映射、停止语义/写入协议/现场优先级、执行机构真实动作与回读、视频和AI服务接入。只读回包和网页测试不代表计量校准、机械到位或现场整机验收。
