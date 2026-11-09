# 1Panel 后端逐步部署说明

适用背景：用户提供的系统为 Alibaba Cloud Linux 4.0.5，使用 1Panel；前端与 MySQL 当前不在同一台服务器，计划后续合并。前端协议的答复写作“httpl4”，本说明暂按 HTTP 调试，实际完整访问地址仍需确认。本文没有访问服务器，容器名称、网络名和端口必须在面板中查看，不能当成已经核实。

建议先在 MySQL 所在服务器的 1Panel 新建一个测试网站，放一份前端，后端也运行在这台服务器上。浏览器用同一个网站地址访问前端和后端，可以直接使用 Cookie 登录。原来的网站先保留。若仍让浏览器从另一台服务器的 HTTP 网站直接调用这里的后端，Cookie 跨站限制会使登录联调复杂化，不适合照抄本文的同源配置。

以下“服务器终端”指 1Panel 的终端或 SSH；“电脑终端”指你自己的 Mac 终端。SQL 只能在 MySQL 控制台/管理工具中执行。

## 1. 查看服务器 Docker 环境

在 1Panel 打开服务器终端，逐条执行：

```sh
cat /etc/os-release
docker --version
docker compose version
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
```

后两条应显示 Compose 版本与容器列表。1Panel 使用容器管理应用，但仍需确认 Docker Compose 命令可用，不要重复安装 Docker/MySQL。若提示权限不足，使用有 Docker 权限的服务器管理员账号。

在容器列表或 1Panel“容器”页面，找到 MySQL、OpenResty 的实际容器名称。名称不一定叫 mysql/nginx；OpenResty 是 1Panel 网站常用的 Web 服务。

## 2. 上传后端部署包

本项目提供精简上传包 `backend/dist/zfxzg-backend-deploy.zip`，只包含部署所需代码、示例配置与契约，不包含本机虚拟环境、真实密码或旧工程。

在 1Panel“文件”里创建示例目录 `/opt/zfxzg`，将压缩包上传到这个目录并解压。解压后的目录至少是：

```text
/opt/zfxzg/
├── .dockerignore
├── docs/api/openapi.yaml
└── backend/
    ├── app/
    ├── Dockerfile
    ├── compose.yaml
    ├── compose.1panel.yaml.example
    ├── requirements.lock
    ├── .env.example
    └── config/
```

注意不要多套一层目录。`.dockerignore`、`.env.example` 是隐藏文件，需要在文件管理里显示隐藏文件。上传目录放在网站公开根目录之外。

在服务器终端：

```sh
cd /opt/zfxzg/backend
ls -la
```

后续全部 `docker compose` 命令都在这里运行。Compose 构建需要上一级的 `docs/api/openapi.yaml`，不能只上传散放的后端文件。

## 3. 核对已有数据库

在 1Panel“数据库”找到对应的 MySQL 实例，确认：

- 数据库名称：用户提供为 `ZFXZG`，以面板实际显示为准，大小写原样保留。
- 数据库用户名：用户提供为 `admin`。这不是网页登录账号。
- MySQL 版本：本项目按 MySQL 8.0+准备；实际版本仍需查看。
- 数据库端口、账号访问来源权限。

如果 `ZFXZG` 已经存在且专供本项目使用，不需要再建库，也不要删除它。如果只是设置了实例/连接名称叫 ZFXZG，数据库列表里并没有这个库，才需要通过面板新建数据库，或在 MySQL 控制台执行：

```sql
CREATE DATABASE IF NOT EXISTS ZFXZG CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
```

后端会创建16张表；不会替你创建 MySQL 账号。用于后端的账号需有本库的 `CREATE, INDEX, REFERENCES, SELECT, INSERT, UPDATE, DELETE` 权限，并允许来自后端容器的连接。仅允许 localhost 的账号不能保证允许另一容器访问。不要复用包含其他应用同名表的库。

本阶段不需要手工导入 `schema.sql`。

## 4. 查清 MySQL 和 OpenResty 的网络

**不要先猜 DB_HOST。** 容器内的 127.0.0.1 指容器自己，并不指 MySQL。

将下面两个容器名称替换为第1步查到的名称，再在服务器终端执行：

```sh
docker inspect --format '{{.HostConfig.NetworkMode}} {{range $name, $value := .NetworkSettings.Networks}}{{$name}} {{end}}' MYSQL实际容器名
docker inspect --format '{{.HostConfig.NetworkMode}} {{range $name, $value := .NetworkSettings.Networks}}{{$name}} {{end}}' OPENRESTY实际容器名
```

只查看网络信息，不输出容器全部环境变量，避免把密码带出来。

### 情况A：MySQL和OpenResty有共同的自定义桥接网络

这是本文提供附加配置的使用条件。共同网络名可能类似 `1panel-network`，但必须用命令显示的实际名称；默认 `bridge` 不适用此方式。

在服务器的 `/opt/zfxzg/backend`：

```sh
cp .env.example .env
chmod 600 .env
mkdir -p config
cp compose.1panel.yaml.example compose.1panel.yaml
```

打开 `.env`，在末尾添加以下两行：

```dotenv
# Linux Compose 用冒号合并两个文件，后续命令会自动读取。
COMPOSE_FILE=compose.yaml:compose.1panel.yaml
PANEL_DOCKER_NETWORK=上面查到的共同网络名
```

后端将加入已有网络，不会新建或修改 MySQL/OpenResty 容器。此方式后续填写：

- `DB_HOST`：MySQL 的实际容器名称或已配置的网络别名。
- `DB_PORT`：MySQL **容器内部**监听端口，通常为3306，以实例配置为准；不是宿主机映射端口。
- 网站反向代理目标：`http://zfxzg-api:8080`。

### 情况B：MySQL在容器网络，OpenResty使用host网络

使用 MySQL 所在的自定义网络作为 `PANEL_DOCKER_NETWORK`，其他操作与情况A相同。`DB_HOST` 仍用 MySQL 容器名。OpenResty 的反向代理目标改为 `http://127.0.0.1:8080`，因为它使用宿主机网络。

### 其他情况

- MySQL直接安装在宿主机：原始 `compose.yaml` 提供 `host.docker.internal` 别名，可用于访问宿主机上容器可达的 MySQL 监听接口。数据库若仅监听宿主机127.0.0.1，普通桥接容器无法通过此别名连接。不要因此把3306直接开放到公网。
- MySQL在另一服务器：使用后端可达的数据库私网地址、实际端口和对应账号来源权限；这与是否和前端同机是两回事。
- MySQL和OpenResty在不同的自定义桥接网络：后端可以同时加入两边网络，不用断开原容器。先按情况A复制配置；将 `compose.1panel.yaml` 的内容改成下面这段：

  ```yaml
  services:
    backend:
      networks:
        database: {}
        web:
          aliases:
            - zfxzg-api
  networks:
    database:
      external: true
      name: "${PANEL_MYSQL_NETWORK:?请填写MySQL实际网络名}"
    web:
      external: true
      name: "${PANEL_OPENRESTY_NETWORK:?请填写OpenResty实际网络名}"
  ```

  在.env中保留 `COMPOSE_FILE=compose.yaml:compose.1panel.yaml`，再添加 `PANEL_MYSQL_NETWORK=实际数据库网络名`、`PANEL_OPENRESTY_NETWORK=实际网站网络名`。`DB_HOST` 使用MySQL容器名，网站代理仍指向 `http://zfxzg-api:8080`。

若属于“其他情况”，可以提供容器名、端口映射和上述网络输出以调整配置；不要发送密码、整个 `.env` 或整个 `docker inspect` 输出。

## 5. 填写后端.env

在 1Panel“文件”里打开 `/opt/zfxzg/backend/.env`。如果第4步尚未复制，则先执行：

```sh
cp .env.example .env
chmod 600 .env
mkdir -p config
```

保留其他设置，修改：

```dotenv
DB_HOST=第4步确定的数据库地址或容器名
DB_PORT=第4步确定的端口
DB_NAME=ZFXZG
DB_USER=admin
DB_PASSWORD='在服务器私下填入你的数据库密码'

APP_ENV=development
ALLOWED_ORIGINS=http://实际测试网站的地址
COOKIE_SECURE=false
COOKIE_SAMESITE=lax

AUTO_MIGRATE=true
DOCS_ENABLED=true
ENABLE_DEBUG_CONTROL=false
CONTROL_ENABLED=false
CONTROL_PROTOCOL_CONFIRMED=false
MQTT_ENABLED=false
```

`DB_PASSWORD` 的占位文字必须替换，实际密码不写进文档、前端或聊天。不要执行 `source .env`。

`ALLOWED_ORIGINS` 填浏览器地址栏里的“协议+域名/IP+端口”，不加页面路径、不加末尾斜线。例如 `http://203.0.113.10:8088` 仅演示格式；不能原样填示例IP。若测试网站使用80端口则不用写 `:80`。这不是1Panel管理页面的地址，除非它就是实际前端页面。

如果实际网站是 HTTPS，则改为：

```dotenv
APP_ENV=production
ALLOWED_ORIGINS=https://实际网站域名
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
```

HTTP和HTTPS要配套；当前代码生产模式要求安全Cookie，HTTP调试不能设成production。数据库库名/账号按实际大小写，不再照抄原示例里的小写zfxzg。

模型、MQTT、网关和INGEST_TOKEN可以先留空；本次先让数据库、登录和页面连起来。

## 6. 构建后端镜像

在服务器终端：

```sh
cd /opt/zfxzg/backend
docker compose config --quiet
docker compose build
```

`config --quiet` 成功时通常没有输出，它检查配置但不展示密码。不要把不带quiet的完整渲染配置贴出来。若缺少实际网络，先回第4步核对。

第一次构建会下载Python 3.13镜像并安装依赖。无需在服务器单独安装Python。出现网络下载/镜像仓库错误时先处理具体下载错误，不要误判成MySQL密码错误；构建阶段还没有连数据库。

若服务器从默认PyPI下载很慢，可只给本次构建指定阿里云维护的镜像，依赖仍按requirements.lock锁定版本安装：

```sh
docker compose --progress plain build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
```

## 7. 建表

```sh
docker compose run --rm backend python -m app.cli migrate
```

**看到“操作完成”才继续。** 在1Panel数据库管理工具刷新，应能看到16张表。`--rm`只移除本次临时任务容器，不删除数据库。

如果失败，先检查库名是否真实存在、密码、账号连接来源权限、端口与第4步网络。当前CLI只显示异常类型与通用提示，不需要把密码贴出来排查。

## 8. 创建网页登录管理员

```sh
docker compose run --rm backend python -m app.cli create-admin --username admin
```

终端会要求输入两次**自己设置的平台密码，至少12位**。输入时没有星号、没有字符显示，这是正常现象。成功后显示“操作完成”。

MySQL的admin是数据库连接账号；这一步的admin是网页登录账号，两者存储位置和密码用途不同。没有默认网页登录密码；已存在的管理员不会被命令覆盖。

## 9. 启动并验证后端

```sh
docker compose up -d
docker compose ps
curl -f http://127.0.0.1:8080/health/ready
```

最后应返回：

```json
{"status":"ready"}
```

`-d`表示后台运行，关掉终端也继续运行。`ps`应显示running/Up，健康检查随后显示healthy。如果不是：

```sh
docker compose logs --tail=100 backend
```

先让服务器本机的健康检查成功。8080只绑定宿主机回环，不能直接从自己电脑访问“服务器公网IP:8080”；同机部署方案也不需要为它开公网端口。

## 10. 在这台服务器准备前端测试网站

如果已经把前端移到该服务器，可以使用现有前端网站，先备份站点配置。否则在1Panel“网站”里创建一个新的**静态网站**，使用你实际有的域名或可用的测试地址/端口，将 `backend/dist/zfxzg-frontend-1panel.zip` 上传到该网站实际运行目录并解压。这个包已经按同源 `/api/v1` 与自动WS地址构建，无需为了首次部署再编译。解压后 `index.html` 应直接位于网站运行目录根部，`assets`与它同级。

如果以后修改前端源码，按下面方式重新构建。项目当前本地 `.env` 中有localhost地址，直接使用旧构建可能让浏览器访问自己的电脑。

在**电脑终端**的项目 `frontend` 目录运行：

```sh
VITE_API_BASE_URL=/api/v1 VITE_WS_URL='' npm run build
```

这是Mac/Linux shell写法，不修改现有.env；空WS配置会让代码按网站当前地址自动选择ws或wss。若本机还未安装项目依赖，先按前端环境要求执行 `npm ci`。

然后把新生成的 `frontend/dist` **内部文件**上传到静态网站运行目录，使其中的 `index.html` 位于运行目录根部、`assets`为其同级目录。不要覆盖1Panel自动生成的网站配置文件。若刷新子页面404，检查该站点已有的SPA回退配置：应回退到 `/index.html`。

Vite配置只在构建时生效；在服务器修改前端.env不会改掉已经生成的JS。

## 11. 配置该网站的反向代理

在1Panel“网站”中找到上述前端测试网站，打开它的配置编辑入口（菜单名称随1Panel版本可能不同）。在实际处理这个网站的 `server { ... }` 内添加下面两段。若同名location已存在，修改原段，不要重复添加；保留现有root、证书和SPA配置。

情况A（OpenResty与后端共享桥接网络）使用：

```nginx
location /api/v1/ {
    client_max_body_size 256k;
    proxy_pass http://zfxzg-api:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 90s;
}

location = /ws {
    proxy_pass http://zfxzg-api:8080/ws;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_buffering off;
}
```

情况B（OpenResty使用host网络）把两处 `zfxzg-api` 替换为 `127.0.0.1`，其他不变。不要把两种配置同时添加。

第一段的proxy_pass末尾不要加斜线或再拼 `/api/v1`，以保留原请求路径。第二段包含WebSocket升级头，不能省略。

保存时使用面板的配置检查并重载；如需手工检查，容器运行的OpenResty通常用以下命令（容器名替换为实际值）：

```sh
docker exec OPENRESTY实际容器名 nginx -t
```

成功后再通过面板重载。宿主机未必有nginx命令，因此不要盲目运行宿主机 `systemctl reload nginx`。若提示 `host not found in upstream zfxzg-api`，核对后端是否已启动且与OpenResty共享网络。

测试网站的HTTP端口需能被浏览器访问；阿里云安全组与服务器防火墙仅按实际网站端口放行（通常HTTP为80，若自选测试端口则以自选为准）。不必开放MySQL 3306或后端8080。

## 12. 浏览器验收

1. 在自己电脑浏览器打开第10步的测试网站地址。此地址必须与后端的 `ALLOWED_ORIGINS` 一致。
2. 点击登录，输入第8步的平台admin账号和平台密码。
3. 应出现登录账号名和站点“智慧农业大棚”。
4. 开发者工具 → Network：登录后 `/api/v1/auth/session` 和 `/api/v1/sites/default-site/snapshot` 返回200；未登录session返回401属正常鉴权。
5. WebSocket `/ws` 应建立连接，通常显示101。

空读数、视频空白、AI未配置、实体控制禁用可能是此阶段的预期结果。软件不会自动继承旧后端MQTT主题/视频/模型配置；后续按真实映射接入，保持现场“既有上行已跑通”与“本版服务映射尚待填写”两者的区别。

## 13. 可选：仅在沙箱测试控制按钮

服务器.env改为：

```dotenv
ENABLE_DEBUG_CONTROL=true
```

然后在服务器终端：

```sh
docker compose up -d --force-recreate
```

网页刷新并切到“调试沙箱（无实体动作）”，可验证风扇开关、模式、沙箱参数与日志。仅改变数据库测试状态，不代表PLC已执行。

修改.env后用 `up -d --force-recreate`；单独restart不会重新加载env_file。修改代码后需重新build。首版只启1个后端实例、1个worker。

## 故障定位

- 构建时找不到Dockerfile/契约：上传目录结构不完整或多套一层目录。
- migrate失败：数据库、账号权限、连接来源、网络和端口未对应；别直接重建或删库。
- 本机ready成功，网站502：先查OpenResty网络与代理目标；OpenResty桥接容器中的127.0.0.1不是宿主机。
- 请求返回HTML而不是JSON：API请求落到静态网站回退，检查API代理段。
- 登录后仍401：检查HTTP/HTTPS、COOKIE_SECURE、网站地址和前端实际请求目标。
- 写入403：检查来源白名单、CSRF和角色；实体控制默认拒绝是预期结果。
- 前端请求localhost：重新构建并上传dist；浏览器localhost是访问者自己的电脑。
- 重建后网站偶发502：容器IP可能改变，先确认后端healthy，再在面板重载OpenResty使其重新解析名称。

首次文档交付时本地没有Docker/MySQL。后续经用户明确授权，已完成目标服务器实际部署与MySQL/登录/WebSocket验收；实际网络和维护位置参见 [已部署维护说明](DEPLOYED.md)。部署不会自动完成真实MQTT、视频、模型与实体控制的适配。
