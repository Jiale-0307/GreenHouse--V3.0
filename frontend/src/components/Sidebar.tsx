import {
  LayoutDashboard,
  Activity,
  Video,
  SlidersHorizontal,
  Bell,
  ClipboardList,
  Settings,
  Sparkles,
  Menu,
  X,
  Sprout,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { useState } from "react";
import { usePlatform } from "../data/Platform";
const links = [
  ["/", "监控大屏", LayoutDashboard],
  ["/trends", "历史趋势", Activity],
  ["/cameras", "视频监控", Video],
  ["/control", "设备控制", SlidersHorizontal],
  ["/alarms", "报警中心", Bell],
  ["/logs", "操作日志", ClipboardList],
  ["/ai", "AI 助手", Sparkles],
  ["/settings", "系统设置", Settings],
] as const;
export function Sidebar() {
  const [open, setOpen] = useState(false);
  const { user, connection } = usePlatform();
  const brand = "智赋新质农";
  return (
    <>
      <button
        className="mobile-menu"
        onClick={() => setOpen(!open)}
        aria-label={open ? "关闭导航" : "打开导航"}
        aria-expanded={open}
      >
        {open ? <X /> : <Menu />}
      </button>
      {open && (
        <button
          className="nav-backdrop"
          aria-label="关闭导航"
          onClick={() => setOpen(false)}
        />
      )}
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">
            <Sprout size={23} />
          </div>
          <div>
            <b>{brand}</b>
            <small>装备装调与管控系统</small>
          </div>
        </div>
        <div className="nav-caption">功能导航</div>
        <nav>
          {links.map(([to, label, Icon]) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setOpen(false)}
            >
              <Icon size={17} />
              <span>{label}</span>
              {to === "/ai" && <small className="new-tag">AI</small>}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span
            className={`pulse ${connection === "connected" ? "connected" : ""}`}
          />
          {user ? "已登录" : "未登录"}
        </div>
        <small className="version">系统 V3.0</small>
      </aside>
    </>
  );
}
