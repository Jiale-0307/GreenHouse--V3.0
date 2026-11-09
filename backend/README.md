# 智赋新质农后端

第一次用 1Panel 部署，请先看 [逐步操作说明](DEPLOY-STEP-BY-STEP.md)：按“在哪里操作、填写什么、成功时看到什么”展开，包含容器网络的检查。本页保留完整配置与接口参考。

FastAPI + SQLAlchemy 2 + MySQL，兼容 `docs/api/openapi.yaml` 与前端 SDK。当前OpenAPI0.3.0共30条路径，包含独立终端会话/撤销、Cookie三角色认证、CSRF、21项环境测点、模式/输出/故障/电表只读监测、历史、报警生命周期、操作日志、幂等控制跟踪、摄像头配置、AI流式会话、WebSocket及管理员诊断。边界和资料缺口见[MONITORING.md](MONITORING.md)。

已按用户授权完成目标服务器HTTP调试部署，并通过MQTT透传Modbus TCP接入18项PLC实测值，约10秒一轮、回包后推送网页，详见 [传感器接入](MQTT-SENSORS.md) 与 [已部署维护说明](DEPLOYED.md)。以下步骤用于后续安装参考。其余不明确地址、实体控制/回读、视频流和模型仍需现场资料与验收。

## 使用现有 MySQL 部署

建议 MySQL 8.0+、Python 3.13，或使用 Docker Compose。首版只运行 **1个实例、1个worker**，MySQL命名锁会拒绝第二实例。不能使用多个Uvicorn worker或多个Compose副本；扩容前需将调度器与任务队列独立。

1. 将项目的 `backend/` 和 `docs/api/openapi.yaml` 上传服务器，保持目录相对位置。前端已部署，可沿用其静态目录。
2. 在现有 MySQL 创建专用数据库（数据库本身需管理员创建，服务负责建表）：

   ```sql
   CREATE DATABASE IF NOT EXISTS zfxzg CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
   ```

   为后端准备只访问此库的账号。首次建表需要 `CREATE, INDEX, REFERENCES, SELECT, INSERT, UPDATE, DELETE` 权限；本服务没有删表、重置或清库命令。账号允许的来源应是后端的实际连接来源。数据库不要复用其他应用的同名表。

3. 在服务器的 `backend/` 中操作：

   ```sh
   cp .env.example .env
   chmod 600 .env
   mkdir -p config
   ```

   编辑 `.env` 的 `DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD`。密码包含 `#`、空格等时使用单引号包裹；不用手工URL编码。容器中的 `127.0.0.1` 指容器自身；MySQL在同一Linux宿主机时可用 `DB_HOST=host.docker.internal`，同时让MySQL监听可达的内网接口并允许该来源。远程数据库可设置 `DB_SSL_CA=/app/config/mysql-ca.pem` 并把CA放进 `config/`。

   HTTPS服务器设置：

   ```dotenv
   APP_ENV=production
   COOKIE_SECURE=true
   COOKIE_SAMESITE=lax
   ALLOWED_ORIGINS=https://你的前端域名
   ```

   `ALLOWED_ORIGINS`是浏览器前端的**来源**（协议+域名+可选端口，无路径、无末尾斜线）；多个来源用逗号隔开。首次本机HTTP调试保留 development 和 COOKIE_SECURE=false。无需在环境变量保存管理员密码。

4. 构建、建表并创建首个管理员：

   ```sh
   docker compose build
   docker compose run --rm backend python -m app.cli migrate
   docker compose run --rm backend python -m app.cli create-admin --username admin
   docker compose up -d
   docker compose ps
   docker compose logs --tail=100 backend
   curl -f http://127.0.0.1:8080/health/ready
   ```

   管理员密码交互输入，至少12位，无默认密码，不进入命令参数或示例文件。`migrate`可重复运行，启动时默认也会迁移；当前v2只新增4张表并保留原账号、历史与配置。SQL可查 `schema.sql`，升级前先备份，旧会话重新登录。

5. 将 `deploy/nginx.conf.example` 中的location合并到现有前端HTTPS站点，保留前端root、证书和SPA回退。运行 `nginx -t` 通过后再重载现有Nginx。后端Compose只监听宿主机回环8080。

6. 前端建议同源访问 `/api/v1` 和 `/ws`。如果已部署的前端构建中固化了 `localhost:8080`，需修改前端构建环境并重新构建；Vite环境变量是构建期变量。`VITE_API_BASE_URL=/api/v1`，`VITE_WS_URL=wss://你的前端域名/ws`。浏览器登录管理员，选择“智慧农业大棚”。

查看 `/docs`（在线交互API）、`/openapi.json`（契约与扩展）、`GET /api/v1/diagnostics`（管理员认证后查看数据库/MQTT/AI/控制配置状态；不返回凭据）。Swagger写操作需先登录，查询 `/auth/session` 获取 csrfToken，并在该操作的 X-CSRF-Token 填入。

## 不使用 Docker

在服务器 `backend/` 目录，先完成MySQL与.env配置：

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m app.cli migrate
.venv/bin/python -m app.cli create-admin --username admin
.venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8080 --workers 1 --no-access-log
```

本机可加 `--reload`。systemd模板为 `deploy/zfxzg-backend.service`，需调整目录与系统账号后安装。正式启动前务必完成数据库配置，不会静默退回SQLite。

## 数据接入与方便调试

将随机生成的至少32字符令牌填写到 `INGEST_TOKEN` 后重启。它只给服务器侧接入程序使用，不能放到前端环境变量。内部接口使用 `Authorization: Bearer <INGEST_TOKEN>`：

- `POST /api/v1/internal/sites/{siteId}/telemetry`：标准化采集值。
- `POST /api/v1/internal/sites/{siteId}/feedback`：设备/参数实际回读和关联指令结果。
- `POST /api/v1/internal/sites/{siteId}/alarms`：外部报警事件，本版不猜测农业阈值。

`examples/telemetry.json`是**显式测试载荷**，不是自动数据源。调试时建议设置 `ENABLE_DEBUG_CONTROL=true` 并重启，向 `debug-site` 发测试数据；真实站点保持没有收到的值为null。示例里的 `observedAt:null`表示采集时间未知，服务单独记录接收时间。

```sh
# 在服务器自己的终端输入令牌，不把真实令牌写进脚本或仓库
read -r INGEST_TOKEN
curl -f http://127.0.0.1:8080/api/v1/internal/sites/debug-site/telemetry \
  -H "Authorization: Bearer $INGEST_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @examples/telemetry.json
unset INGEST_TOKEN
```

每次新消息使用唯一messageId；相同ID相同载荷只接收一次，不同载荷409。MQTT无稳定ID时不能保证端到端去重。0值保留，bool不能作为物理数值；非法数据值显示null。部分更新保留其他测点；乱序数据进入历史但不倒退快照。采集时间和接收时间分开保存，API时间为 Asia/Shanghai +08:00。`STALE_AFTER_SECONDS`需按实际上传周期填写，未设置时不猜测过期阈值。

历史支持raw/1m/5m/1h、默认最多31天和10000点；超过限制返回422，需缩小时间或增大聚合粒度。没有采集时间时用接收时间作为历史轴；曲线首尾之间的空桶及明确缺测桶均返回null，不补零。

## MQTT接入现有上行

复制 `examples/mqtt-mapping.json` 到 `config/mqtt.json`，按**真实脱敏载荷**填写精确主题、测点ID、字段路径，以及已确认的scale/offset。示例没有真实主题或寄存器地址，不能直接用于现场。

配置 `MQTT_HOST/PORT/USERNAME/PASSWORD/TLS/CA/QOS/CLIENT_ID`，再设置 `MQTT_ENABLED=true` 并重启。当前适配器支持JSON对象/数组路径、数值倍率和偏移；二进制Modbus透传使用下文独立轮询器，不应强行按JSON解析。采集时间字段仅接受带时区的ISO8601；没有该字段就删除 `observedAtPath`。没有稳定消息ID就删除 `messageIdPath`，重复投递将可能产生重复样本。缺失字段跳过，非法值显式记录缺测。此JSON适配器仅订阅。原始Modbus轮询使用独立开关，见下文。

## MQTT透传读取PLC传感器

本轮已增加原始Modbus TCP轮询模块：通过 `dtu/down` 发送二进制03读取帧，订阅 `dtu/up` 后解码、入库并触发网页实时刷新。配置、18个明确地址、待补地址、逐步排查见 [传感器接入说明](MQTT-SENSORS.md)。默认关闭，服务器启用前需填写并确认 `config/modbus-mqtt.json`；原20测点保留并新增紫外线指数，未知值仍为null。

## 配置参数与摄像头

管理员可通过 `PUT /api/v1/sites/{siteId}/configuration` 或本机CLI修改定义。按ID合并更新，没有出现在请求中的条目保持原样；该接口不会写设备状态、采集值或现场回读。

```sh
cp examples/site-config.json config/site.json
# 编辑config/site.json；真实视频签名链接只能放服务器私有配置
# Docker
 docker compose run --rm backend python -m app.cli configure-site --site default-site --file config/site.json
# 或本机
 .venv/bin/python -m app.cli configure-site --site default-site --file config/site.json
```

`cameras`可配置HLS/MP4播放地址，未知地址/在线状态保持null。本版不包含ONVIF发现、RTSP转HLS、播放签名刷新或视频服务器；摄像头已有流需要转流服务提供浏览器可播放地址，并配置播放授权/CORS。签名过期后需刷新配置，不把链接提交到知识库。

可写参数必须提供min/max/step，写入仅管理员，且受站点控制能力、状态版本、实际回读约束。单位没有资料就保持null，不预置生产阈值。所有账号当前访问同一工作空间中的站点；AI会话和AI实时事件仅属于创建者。多租户或按站点分配账号权限待后续设计。

## 控制边界

`default-site`默认 `controlEnabled=false`。`ENABLE_DEBUG_CONTROL=true`添加独立“调试沙箱（无实体动作）”，只提供fan的on/off/set_mode和0–100步长1的沙箱参数；这些范围是软件测试值，不是PLC或农业参数。选沙箱可以调试确认、202受理、轮询、日志和WS回读，结果明确注明沙箱。

实体控制需要 **CONTROL_ENABLED、CONTROL_PROTOCOL_CONFIRMED、网关URL和令牌、站点controlVerified** 全部具备，并配置真实动作定义与新鲜的现场回读。通用HTTP网关只是后续适配边界，本版没有实现DTU/PLC写协议。网关需要接受 `{commandId,siteId,kind,targetId,request}`，按commandId去重，在现场再次检查保护/优先级，再通过feedback接口上报实际结果。HTTP 2xx只算送达，不能算执行成功。

`commands`持久保存幂等键，不自动重试或重发。同一键载荷不同409；版本不符409；只读账号403；现场优先级/联锁不允许403。执行超时、网关网络失败或服务重启后状态为unknown；unknown指令阻止同目标新动作，须通过关联现场回读明确成功/拒绝后再操作。succeeded必须附带请求后的目标回读；参数值必须匹配。PLC保留现场联锁与离线自动控制职责。

## AI适配

可填写兼容流式 `chat/completions` 的 `AI_BASE_URL / AI_MODEL / AI_API_KEY`；不预选模型或供应方。未配置时能力false，返回503，无假回复。配置状态不等于供应方连接成功，实际错误通过 `ai.error` 和可恢复历史消息呈现。用户选择includeContext才发送本站快照；不发送摄像头签名或连接凭据。

AI流产生 `ai.delta / ai.completed / ai.error`，最终结果入库。首版controlIntent始终null，不从自由文本解析自动动作；不调用设备工具。未来需定义经验证的结构化建议再走现有前端确认流程。

## 数据与维护

20张SQL表：原16表（站点、账号、会话、测点/历史、执行机构、参数、摄像头、报警、日志、指令、AI会话/消息、实时事件、去重、结构版本）加终端会话元数据、PLC当前块、测量来源证据、报警生命周期。首次创建21环境测点和8类执行机构定义；不注入业务读数、身份、报警或视频。

数据库为持久来源，删除容器不会删除MySQL数据。服务仅自动清理已过期登录会话和1天前WS通知；历史、操作日志、指令、聊天和去重记录不自动清理。长期运行应制定备份、采样保留期和容量策略。升级前做MySQL备份，保留旧镜像；不要用删除数据的方式解决启动问题。

## 本地验证

```sh
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/ruff check app tests
.venv/bin/python -m pytest
```

测试使用独立临时SQLite验证业务与前端契约，MySQL建表SQL经方言编译检查；当前机器无MySQL/Docker，未声称完成真实MySQL事务、容器构建或服务器验收。若设置 `TEST_MYSQL_URL`，测试可运行在专用一次性空MySQL库，库名必须以 `zfxzg_test_` 开头（测试结束清理该测试库内表），**不可指向生产库**。详情见 `verification/README.md`。
