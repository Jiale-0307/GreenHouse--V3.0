import { Outlet, useLocation, Link } from "react-router-dom";
import { RefreshCw, Bell, LogOut, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../sdk";
import { Sidebar } from "./Sidebar";
import { usePlatform, resourceError } from "../data/Platform";
import { APP_TITLE } from "../data/brand";
const titles: Record<string, string> = {
  "/": "监控大屏",
  "/trends": "历史趋势",
  "/cameras": "视频监控",
  "/control": "设备控制",
  "/alarms": "报警中心",
  "/logs": "操作日志",
  "/ai": "AI 助手",
  "/settings": "系统设置",
};
export function SessionActions() {
  const p = usePlatform();
  const cache = useQueryClient();
  const logout = useMutation({
    mutationFn: () => api.logout(),
    onSuccess: () => {
      api.setCsrfToken(null);
      p.setAuthExpired(true);
      cache.clear();
    },
  });
  return (
    <div className="session-actions">
      <span className="account-label">
        <ShieldCheck size={14} />
        {p.user?.displayName}
      </span>
      <button
        className="icon-button"
        title="刷新数据"
        onClick={() => p.refresh()}
      >
        <RefreshCw size={16} />
      </button>
      <button
        className="icon-button"
        title="退出当前终端"
        disabled={logout.isPending}
        onClick={() => logout.mutate()}
      >
        <LogOut size={16} />
      </button>
      {logout.error && (
        <span role="alert" className="error">
          {resourceError(logout.error)}
        </span>
      )}
    </div>
  );
}
export function Layout() {
  const location = useLocation();
  const p = usePlatform();
  // 不挂载业务页面，避免未登录时发请求或短暂暴露上一个账号的缓存。
  if (!p.user) return <LoginPage />;
  const screen = location.pathname === "/";
  return (
    <div className={`app-shell ${screen ? "screen-shell" : ""}`}>
      {!screen && <Sidebar />}
      <main className="main">
        {!screen && (
          <header className="topbar">
            <div className="breadcrumb">
              <Link to="/">监控大屏</Link>
              <span>/</span>
              <b>{titles[location.pathname] || "页面"}</b>
            </div>
            <div className="top-actions">
              <Link
                className="icon-button"
                to="/alarms"
                aria-label="打开报警中心"
              >
                <Bell size={16} />
              </Link>
              <SessionActions />
            </div>
          </header>
        )}
        <Outlet />
        {!screen && (
          <footer className="page-footer">
            <span>{APP_TITLE}</span>
            <span>北京时间 · +08:00</span>
          </footer>
        )}
      </main>
    </div>
  );
}
function LoginPage() {
  const p = usePlatform();
  const cache = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => api.login(username, password),
    onSuccess: async (session) => {
      await cache.cancelQueries();
      cache.clear();
      api.setCsrfToken(session.csrfToken);
      cache.setQueryData(["session"], session);
      p.setAuthExpired(false);
      setPassword("");
    },
  });
  return (
    <div className="login-page">
      <div className="login-identity">
        <span className="system-emblem">农</span>
        <div>
          <b>智赋新质农</b>
          <span>智能大棚装备装调与管控系统</span>
        </div>
      </div>
      <div className="login-art" aria-hidden="true">
        <svg viewBox="0 0 700 480">
          <g fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M70 338 286 439 624 248 413 146Z" />
            <path d="M145 318V174L253 65 468 165V309L360 418V274L145 174M253 65V208L468 309M360 274 468 165M145 318 360 418M253 208 360 274" />
            {[0, 1, 2, 3, 4].map((i) => (
              <path
                key={i}
                d={`M${145 + i * 42} ${174 + i * 20}V${318 + i * 20}M${253 + i * 42} ${65 + i * 20}V${208 + i * 20}`}
              />
            ))}
            <path d="M70 338V370L286 471 624 280V248" />
          </g>
        </svg>
        <span>现场感知 · 装备状态 · 协同管控</span>
      </div>
      <form
        className="login-form form-stack"
        onSubmit={(e) => {
          e.preventDefault();
          login.mutate();
        }}
      >
        <div>
          <span className="section-index">系统访问</span>
          <h1>登录管控平台</h1>
          <p>使用你的账号，在当前终端建立独立会话。</p>
        </div>
        <label>
          账号
          <input
            required
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
          />
        </label>
        <label>
          密码
          <input
            required
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {login.error && (
          <p role="alert" className="error">
            {resourceError(login.error)}
          </p>
        )}
        {p.session.isPending && !p.authExpired && (
          <p role="status">正在检查当前终端会话…</p>
        )}
        {p.session.error && !p.authExpired && (
          <p className="muted">{resourceError(p.session.error)}</p>
        )}
        <button className="primary-button" disabled={login.isPending}>
          {login.isPending ? "正在验证…" : "登录"}
        </button>
        <small>会话最长12小时；退出仅影响当前终端。</small>
      </form>
      <footer>智赋新质农 · 装备装调与管控</footer>
    </div>
  );
}
