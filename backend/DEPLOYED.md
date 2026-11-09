# 已部署服务维护说明

更新时间：2026-11-09T00:38:11+08:00（Asia/Shanghai）。用户明确授权部署、传感器只读轮询与本轮存储性能优化，本文不记录任何密码、Cookie或令牌。

- 网站：http://121.43.210.31/；接口文档：http://121.43.210.31/docs。
- 服务器：Alibaba Cloud Linux 4.0.5；1Panel；Docker 26.1.3、Compose 2.27.0。
- 后端目录：`/opt/zfxzg/backend`；服务容器：`backend-backend-1`；绑定 `127.0.0.1:8080`，不直接开放公网8080。
- MySQL：现有`mysql:8.4.13`容器，接入`1panel-network`。实际数据库为小写`zfxzg`；原有空`test`表保留，新增本项目16张表。未修改原数据库账号权限。
- OpenResty：现有`openresty`容器，使用host网络。站点配置`/opt/1panel/www/conf.d/ZFXZG.conf`，静态目录`/opt/1panel/www/sites/ZFXZG/index`。API、WebSocket转发到127.0.0.1:8080，并添加SPA路由回退。
- 管理员用户名为`admin`，密码独立随机生成；初始凭据仅保存在服务器`/root/.zfxzg-platform-admin.json`，权限600。后端`.env`权限600。不要把这些文件发回聊天或上传至代码仓库。
- Docker开机启动已启用，后端重启策略为`unless-stopped`。仅运行1个实例、1个worker。

## 服务器重启后如何启动

在**服务器的1Panel终端或SSH终端**执行，不能在个人电脑本机执行这些Docker命令。当前需要四个容器：`mysql`数据库、`EMQX`消息服务、`backend-backend-1`平台后端、`openresty`网站/API代理。API、WebSocket与传感器轮询都在同一个平台后端中，无需分别运行Python程序。

先启动Docker和既有依赖，再启动平台后端：

```sh
systemctl start docker
docker start mysql EMQX openresty
cd /opt/zfxzg/backend
docker compose up -d backend
```

这些命令可重复执行，已运行的服务会保持运行；普通重启恢复无需重新构建镜像、建库或创建管理员。MySQL刚启动时可能尚未就绪，后端会按原重启策略恢复，稍等后检查：

```sh
docker ps --format 'table {{.Names}}\t{{.Status}}'
curl -fsS http://127.0.0.1:8080/health/ready
```

应看到上述四个容器为`Up`，后端最终显示`healthy`；健康接口返回`{"status":"ready"}`。然后访问网站并查看接收时间是否推进。刚恢复需等待DTU重连和一轮读取，读请求单项超时会延长恢复时间。若仍失败，执行`docker compose logs --tail=50 backend`与`docker logs --tail=50 EMQX`定位，不把整个.env或凭据贴回聊天。

若使用面板，在1Panel“容器”列表按MySQL、EMQX、OpenResty、后端顺序启动处于停止状态的容器。1Panel自身由`1panel-core.service`和`1panel-agent.service`管理；本次两者已自动启动，面板无法访问时可通过SSH运行`systemctl start 1panel-core 1panel-agent`。

### 本次重启恢复记录

记录时间：2026-11-05T02:03:30+08:00。用户重启服务器后询问全部服务的启动方法。实际检查Docker已active/enabled、1Panel core/agent运行；MySQL、OpenResty和后端已启动，后端healthy，但EMQX退出且Docker重启策略为`no`，未自动恢复。

已执行`docker update --restart unless-stopped EMQX`与`docker start EMQX`。EMQX没有Compose项目标签，修改其既有容器运行策略；未改变Broker认证/主题、PLC或DTU配置。以后普通服务器重启会由Docker恢复EMQX；若主动执行`docker stop EMQX`，`unless-stopped`会保留人为停止状态，需要再次`docker start EMQX`。

恢复检查：四容器均Up，后端healthy，网站HTTP200，MySQL结构版本1；后端MQTT已connected/ready。02:03:19检查尚无合法回包，出现3次超时和1次非法帧拒绝；02:03:30检查已有32次合法接收、累计4次超时/1次拒绝/0处理失败、最后错误清空，18/21测点与站点connected。该记录证明本次恢复，不代表长期稳定性或后续完整重启演练。

## 常用维护命令

在服务器终端执行：

```sh
cd /opt/zfxzg/backend
docker compose ps
docker compose logs --tail=100 backend
curl -f http://127.0.0.1:8080/health/ready
```

修改.env后重新创建容器：

```sh
docker compose up -d --force-recreate
```

更新代码后重新构建并启动；服务器默认PyPI下载很慢，本次使用阿里云维护的镜像，版本仍锁定：

```sh
docker compose --progress plain build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
docker compose up -d
```

修改站点配置后先验证，再平滑重载：

```sh
docker exec openresty nginx -t
# 只有上一条通过后再执行。
docker exec openresty nginx -s reload
```

## 备份与验收

部署前的数据库导出与原`.env`/Compose/站点配置保存在服务器`/opt/zfxzg-deploy-backups/20261104T194327+0800/`，目录权限700；静态前端更新前的备份是`/opt/zfxzg-deploy-backups/frontend-20261104T201417+0800.tar.gz`，文件权限600。备份可能含凭据或业务数据，仅留服务器保管。

实际MySQL建表、结构版本1、20测点初始化、空值、13条认证查询、历史查询、CSRF拒绝、注销后401、API文档、SPA刷新和经OpenResty代理的WebSocket 101/订阅/Ping已验证。容器healthy、无重启；pip check通过。浏览器已实际登录，显示admin、智慧农业大棚与实时连接；截图见`verification/deployed-20261104.jpg`。

浏览器验收修复了前端SDK默认fetch未绑定全局对象的问题，防止Illegal invocation导致请求发不出。修复后的SDK6项测试及前端生产构建通过；服务器已更新静态文件，旧文件保留且有完整备份。

以上为首次部署的验收范围；当前状态以以下传感器接入记录为准。仍为HTTP调试部署，域名HTTPS、AI、视频和实体控制尚未配置/启用。

## 真实传感器接入与刷新

记录时间：2026-11-05T00:12:48+08:00。后端已通过同网络的现有EMQX连接1883端口，向 `dtu/down` 发布二进制功能码03读取帧，订阅 `dtu/up`；账号密码当前为空，服务器 `.env` 预留 `MQTT_USERNAME/MQTT_PASSWORD`。原JSON订阅器关闭，独立Modbus轮询启用。

- 18项明确PLC地址已收到真实回包、保存MySQL并推送网页；新增紫外线指数后共21项定义。氧气与两处气压共3项保持未接收，其他歧义/新增地址等具体文档。映射和字序见 `MQTT-SENSORS.md`。
- 每10秒开始一轮串行读取，单项超时3秒、请求间隔0.1秒；整轮耗时超过周期则顺延。每次回包分别推送，历史曲线每10秒查询。90秒未更新标记过期并保留最后值。此周期不代表PLC内部采集周期。
- Modbus帧没有源采集时间，`observedAt=null`，以服务器 `receivedAt` 判断新鲜度；D402约23.4与用户确认一致。其余值按相同PLC浮点字序接收，单位/校准仍待现场核对，不能以“收到回包”代表测量准确。
- 修复前端每次遥测触发多资源重查的问题，直接使用WS完整快照；同源静态包使用 `npm run build:same-origin`，避免本机localhost配置进入线上包。
- 修复WS与周期维护/命令扫描中的同步SQL连接等待阻塞事件循环，避免并发查询时连接无法释放、登录和刷新卡住。实际36条并发认证GET全部成功，最长1.04秒，期间WS收到 `snapshot.updated`。这是一次有界并发验收，不代表长期容量保证。
- 浏览器保持用户自行登录，显示“实时连接”“已连接”和18/21；接收时间从00:11:55推进至00:12:48。截图 `verification/mqtt-sensors-20261105.png`。后端healthy、重启次数0、8080仅回环监听；本次镜像启动后检查未见错误日志。

本轮更新前已备份数据库、后端和完整静态前端，保存在服务器 `/opt/zfxzg-deploy-backups/mqtt-20261104T233355+0800/`；权限目录700/文件600。旧镜像标签 `zfxzg-backend:pre-mqtt-20261104T233355-0800`，备份指针 `/opt/zfxzg/.mqtt-backup-path`。备份只留服务器；上线仍沿用原 `.env`、数据库与Compose网络配置。

没有修改PLC/DTU或EMQX配置，没有写寄存器或下发执行机构动作。完整地址/单位、实体下行回读、断网自动接管、视频、AI与长期运行验收仍待后续。

## 系统盘IOPS告警与本轮优化

记录时间：2026-11-05T18:49:36+08:00。用户提供阿里云`StoragePerformanceReachLimit / SysDiskIOPS`告警，截图显示事件时间2026-11-04T20:48:54+08:00；用户确认实例`ecs.e-c1m1.large`、2vCPU/2GiB，来自其99元/年活动套餐。系统盘类型与云侧IOPS上限未获得，截图告警早于真实传感器接入，不能据此确定历史告警根因。

当前实测：40GB系统盘仅用约12GB（30%），余27GB，inode用7%；内核可见内存约1.63GiB，排查时可用约196MiB，1GiB交换区未使用。不是磁盘容量耗尽，也未见交换写入证据。进程累计I/O显示MySQL读取约392GiB；1分钟负载84.42，磁盘127个未完成请求，SSH/HTTP严重延迟。

已定位当前后端的明显放大因素：`realtime_events`数据页约891MiB，而`metric_samples`数据和索引共约15MiB；事件每个点重复存全棚快照。旧维护任务每分钟按无索引`emitted_at`删除过期事件，实际EXPLAIN为全表扫描ALL；MySQL缓冲池仅128MiB，反复读大表会与其他进程争用磁盘/内存。Docker日志实测网站约2.1MiB、EMQX约174KiB、MySQL约13KiB，未见日志体积异常。

本轮部署三项代码优化：

- 遥测事件只持久化内部快照引用，WS读取时组装当前完整快照；同次读取复用组装结果，旧版事件兼容，私有事件仍按用户过滤。实际JSON payload从旧样本4644字节降到23字节（约99.5%），这只代表事件载荷，不代表总磁盘I/O同幅降低。所有原始采样继续逐项保存，10秒轮询不变。
- 通知保留规则仍为1天，改为每分钟沿主键最多检查最早500条的ID/时间，再按ID删除其中确已过期的通知；不扫描payload、不清空表、不执行OPTIMIZE TABLE。历史采样、操作日志、指令和聊天不参与清理；现有约891MiB表空间不会立即归还操作系统。
- 命令队列为空时先轻量检查，跳过对全站点的锁事务；队列有指令时仍走原权限/联锁/回读流程，扫描间隔0.25秒不变。

代码和旧镜像已先备份：`/opt/zfxzg-deploy-backups/io-20261105T184546+0800/app-before.tar.gz`（600/目录700），旧镜像标签`zfxzg-backend:pre-io-20261105T184546-0800`。只替换4个后端源码文件，构建镜像后重建后端；没有修改.env、数据库表结构、MySQL持久性、Broker或PLC/DTU配置。`innodb_flush_log_at_trx_commit=1`、`sync_binlog=1`及binlog保持原值，没有通过削弱断电保护换性能。

验收：后端65测试、Ruff、隔离TCP烟测通过；线上12条并发查询和WS完整21项快照通过，最长0.76秒。诊断235次合法回包、0超时/拒绝/失败，后端healthy、错误日志为空。18:47:46至18:48:46（均+08:00）60秒跨维护周期采样：平均111.14读IOPS、48.08写IOPS、读4.611MiB/s、写0.692MiB/s、磁盘busy约5.52%，队列末值0，1分钟负载1.24。guest指标不等于阿里云配额监控；前后为不同负载时段，不是严格同条件基准。

目前可先继续用现有实例，观察云侧正常业务监控是否仍持续告警；尚无24小时数据或云侧告警恢复证明。2GiB内存余量有限，若后续增加转流/更多连接，或正常负载下仍频繁超限，再按内存与实例/云盘IOPS限制决定升级；单纯增加容量不保证解决性能上限。未自动购买或更改云资源规格。

## Web改版、独立会话与监测升级

记录时间：2026-11-09T00:38:11+08:00。前后端已更新；数据库结构v2只新增4表，现20业务表+原test，账号/密码/采样历史保留。原16表/版本1为此前历史状态。全站登录保护、独立终端会话、18故障/模式/输出/4字电表/双路证据上线，见[MONITORING.md](MONITORING.md)和[本轮验收](verification/WEB-UPGRADE.md)。旧会话需要重新登录；浏览器会话恢复的例外保持。

用户最新现场更正故障0正常/1故障；旧规则的18条事件保留并说明关闭，不写设备恢复时间。D2400棚外/D2500棚内。氧气/气压转换、电表映射未确认，模式写入保持禁用；未改PLC/DTU、未下发实体动作。

上线前备份在服务器 /opt/zfxzg/backups/web-upgrade-20261108-234511（目录700/文件600）：database.sql 118816010字节，application-site-config.tar.gz 2812693字节，backend-image.tar 191204352字节，image-id.txt、backup-location.txt、modbus-mqtt-before.json。备份含敏感信息，仅留服务器。旧镜像保留标签 zfxzg-backup:web-before-20261108-234511。

镜像基础下载缓慢，改用本地旧镜像做基础离线COPY新代码及契约；依赖lock SHA256完全一致，没有改依赖或Python版本。最终镜像由backend-backend标签运行，仍单实例/worker、8080仅回环，Compose网络/.env保持。后端配置42读取点权限644、root拥有，容器uid10001可读；不要改成root独占600。API代理proxy_cache off/no_cache/bypass，index.html响应no-store；静态旧哈希资源保留以兼容已打开页面。

### 回滚步骤

先保存故障期间的新业务状态与当前配置。出现功能错误时可停后端、将旧标签重新标记为backend-backend，恢复备份中的后端源码、原读取配置和站点配置/静态文件，再用实际Compose重建。增量表无需删除：旧代码会忽略新增表；如必须回到结构版本1，只调整schema_version记录为1，不drop任何新表，不以旧SQL覆盖上线后历史。数据库全量恢复只用于单独确认的数据恢复，应先备份当前库以免丢失新增采样。

示例只在服务器执行（停服前先确认备份存在）：

```sh
cd /opt/zfxzg/backend
docker compose -f compose.yaml -f compose.1panel.yaml stop backend
docker tag zfxzg-backup:web-before-20261108-234511 backend-backend
# 按备份实际内容恢复应用、原modbus-mqtt.json和站点静态文件；不覆盖数据库历史。
# 原代码只识别schema_version=1；通过数据库管理工具将该版本记录改回1，新增表保留。
docker compose -f compose.yaml -f compose.1panel.yaml up -d --no-build --force-recreate backend
docker exec openresty nginx -t
# 检查通过后才执行 reload，再检查健康/上行/登录/WS。
```

本轮未触发回滚，也未实际演练上述回滚。验收数据和限制见verification/WEB-UPGRADE.md；HTTP调试站点仍未配置域名HTTPS，不能声称已达到HTTPS上线验收。
