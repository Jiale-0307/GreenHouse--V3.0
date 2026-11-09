# 智赋新质农—智能大棚装备装调与管控系统前端

React + TypeScript + Vite 独立前端。所有业务数据均来自后端，不启用运行时模拟数据。未登录只显示登录页，建立会话后才加载展示大屏与八个业务模块；未知数值显示“—”，未确认的写操作禁用。

## 本地运行

要求 Node.js 22.12+（已在 Node 24 验证）。

```sh
cd frontend
npm ci
cp .env.example .env
npm run dev
```

默认浏览地址为 `http://localhost:5173/`。`.env` 中配置 REST 根地址和 WebSocket 完整地址；生产部署建议同域反向代理 `/api/v1` 与 `/ws`。不要把密码、令牌或模型密钥写入任何 `VITE_` 环境变量，它们会进入浏览器包。

```sh
npm run typecheck
npm test
npm run check:api
npm run build
npm run preview
```

## 代码分层

- `src/pages/`：八个业务页面；`src/components/`：图表、视频、对话框、控制确认和执行跟踪。
- `src/data/`：静态测点定义与 TanStack Query 数据生命周期，不包含模拟读数。
- `src/sdk/`：REST 客户端、类型契约、WebSocket订阅/重连；可由后端对接人员独立阅读。
- `src/lib/`：空值、时间、新鲜度和控制权限规则及测试。

REST 使用 HttpOnly Cookie 会话；写请求附带服务端会话返回的 CSRF Token。前端权限只控制界面，后端必须重复鉴权、联锁检查和幂等处理。控制与参数写入不自动重试，超时后通过日志/回读确认结果。

测点名与来源是资料记载，单位未确认时保持 `null`。正式名称已固定，信息密度可调整。摄像头播放器支持HLS和MP4；实际ONVIF发现、转流和授权服务待接入。

## 后端对接

完整契约入口：[../docs/api/README.md](../docs/api/README.md)。前后端已部署，真实MQTT上行与模式/输出/故障/电表原始块已接入；待确认映射、下行、视频和AI见[监测说明](../backend/MONITORING.md)。未修改PLC/DTU、未下发实体动作。

## 部署

前后端同源部署时使用 `npm run build:same-origin`，强制API为 `/api/v1`、WebSocket跟随当前网站，避免本机 `.env` 的localhost地址被打入线上包。当前传感器实时接入范围与配置见 `../backend/MQTT-SENSORS.md`。

将 `dist/` 部署到静态服务器；SPA 路由需回退到 `index.html`。反向代理保留 Cookie，WebSocket 支持 Upgrade。跨域开发使用精确 Origin 白名单和 `Access-Control-Allow-Credentials: true`，不能用通配符搭配凭据。会话 Cookie 生产环境应设 HttpOnly、Secure 和合适的 SameSite。

## 测试边界

单元测试使用隔离测试对象与替身验证请求/控制语义，不影响运行页面。实际摄像头、PLC动作、模型服务和多棚切换须由后端接入后联调。

验收截图与详细范围见 `verification/README.md`。
