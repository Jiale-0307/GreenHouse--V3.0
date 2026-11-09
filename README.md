# 智赋新质农—智能大棚装备装调与管控系统

山东省职业技能大赛「智能装配应用赛道」备赛项目。第三版前后端已同源部署，真实传感器上行、模式/输出/故障只读监测与独立终端登录已接入。氧气/气压换算、电表物理映射、实体下行、视频与AI仍有待确认项，见[监测说明](backend/MONITORING.md)和[当前进度](knowledge/current/STATUS.md)。

## 从哪里开始

- AI协作者：先读 [协作规则](AGENTS.md)，再读 [知识库入口](knowledge/current/README.md) 与 [当前进度](knowledge/current/STATUS.md)。
- 项目成员：查看 [项目概况](knowledge/current/PROJECT.md)、[硬件与传感器](knowledge/current/HARDWARE.md)、[通信](knowledge/current/COMMUNICATION.md)、[软件与AI](knowledge/current/SOFTWARE.md)。
- 原始资料与可信度：查看 [来源索引](knowledge/current/SOURCES.md)。
- 版本与更新方法：查看 [知识库维护说明](knowledge/README.md)、[更新日志](knowledge/CHANGELOG.md)。

## 目录约定

- `knowledge/current/`：最新项目知识，日常维护入口。
- `knowledge/releases/`：知识库完整历史快照，不修改旧版本。
- `docs/`：原始说明书、协议、电气图等工程资料。
- `images/`：实体照片，拍摄时间不明时不从文件时间推断。
- `history/`：前两版相关历史工程参考，不代表第三版实现。
- `frontend/`：React + TypeScript + Vite 前端、SDK、测试与运行说明。
- `backend/`：FastAPI 后端调试版、MySQL建表、数据接入、测试与部署说明。
- `docs/api/`：第三版OpenAPI、WebSocket、字段字典和联调指南。
- `src/`、`lib/`：原有空目录，保持原样。
- `scripts/`：维护工具。

## 仓库与协作

仓库：[Jiale-0307/Smart-Greenhouse-Project](https://github.com/Jiale-0307/Smart-Greenhouse-Project)，私有仓库，默认分支为 `main`。获授权的成员可克隆源代码与工程资料：

```sh
git clone https://github.com/Jiale-0307/Smart-Greenhouse-Project.git
cd Smart-Greenhouse-Project
```

1. 仓库保存可复现的源代码、依赖锁、接口文档、说明书、验收截图与知识库；本地密钥、真实环境变量、现场配置、数据库、日志、依赖目录与构建输出不纳入提交。
2. 主分支保留可复现状态，平台、PLC、机械/电气资料分别通过任务分支和小批提交更新；一次变更同时包含相关代码、协议和知识库更新。
3. 用Issue记录待办、负责人、验收条件；用里程碑区分设备联通、平台首版、AI接入、比赛演示。具体时间待赛程与团队确认。
4. PLC工程、DTU配置、电气图同时保存原生文件及可阅读导出件；上传前移除设备密码和云端凭据。协议字段变更应先同步地址表与消息样例。
5. 数据采集文件和视频录像逐步增长后放外部存储；大型工程文件按需使用Git LFS。知识库中保留位置与版本索引。
6. 旧版后端有硬编码连接凭据，旧版页面有带签名视频地址，因此这两个本地原件已暂时加入忽略列表；完成脱敏后再纳入版本管理。不要把密钥复制到知识库或提交记录。

知识库快照版本与产品V3.0是两个独立编号；知识库版本不代表设备或平台已发布。

## 前端启动

```sh
cd frontend
npm ci
npm run dev
```

浏览 `http://localhost:5173/`。登录后加载业务页面；未知数值显示“—”，未确认的控制禁用。配置与构建见 [前端说明](frontend/README.md)，后端生成与联调见 [接口文档](docs/api/README.md)。

## 后端启动与部署

后端已按前端契约实现调试版，使用 MySQL，并自动创建缺失表。填写 `backend/.env.example` 对应配置后，按 [后端部署说明](backend/README.md) 运行建表、首次管理员和 Docker Compose。没有默认管理员密码；真实设备控制默认关闭，可选独立调试沙箱。

第一次通过1Panel部署，参见 [后端逐步操作说明](backend/DEPLOY-STEP-BY-STEP.md)，包含上传、容器网络、数据库配置、建表、管理员和网站反向代理的操作顺序。
