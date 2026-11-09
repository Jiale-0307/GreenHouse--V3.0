import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  Maximize,
  Minimize,
  Activity,
  Settings2,
  Waves,
  ShieldAlert,
  Zap,
  Monitor,
  Video,
  Bot,
  History,
  ClipboardList,
} from "lucide-react";
import { usePlatform, useResource } from "../data/Platform";
import { APP_TITLE, MODE_LABELS } from "../data/brand";
import { api } from "../sdk";
import { displayDate, displayMetricValue, readingStatus } from "../lib/format";
import { SessionActions } from "../components/Layout";
import { GreenhouseDiagram } from "../components/GreenhouseDiagram";
import {
  FaultPanel,
  MeterPanel,
  useMonitoring,
} from "../components/MonitoringPanels";
import { Chart } from "../components/Chart";
import { QueryNotice } from "../components/UI";
const shortcuts = [
  ["/trends", "历史趋势", History],
  ["/control", "设备控制", Settings2],
  ["/alarms", "报警中心", ShieldAlert],
  ["/cameras", "视频监控", Video],
  ["/ai", "AI助手", Bot],
  ["/logs", "操作日志", ClipboardList],
  ["/settings", "系统设置", Monitor],
] as const;
export function Dashboard() {
  const p = usePlatform();
  const s = p.snapshot.data;
  const monitoring = useMonitoring();
  const [full, setFull] = useState(false);
  const [fullscreenError, setFullscreenError] = useState("");
  const toggleFull = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
      setFull(!!document.fullscreenElement);
    } catch {
      setFullscreenError("浏览器未允许全屏，可使用浏览器全屏快捷键。");
    }
  };
  const readings = new Map(p.readings.map((r) => [r.metricId, r]));
  const received = p.readings.filter((r) =>
    ["已接收", "单路降级"].includes(
      readingStatus(r, p.capabilities.data?.staleAfterSeconds, p.now),
    ),
  ).length;
  const faults = monitoring?.faults.some((f) => f.state !== "unknown")
    ? monitoring.faults.filter((f) => f.state === "fault").length
    : undefined;
  const unknowns = monitoring?.faults.filter(
    (f) => f.state === "unknown",
  ).length;
  const time = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(p.now));
  function metric(id: string, big = false) {
    const def = p.catalog.find((d) => d.id === id);
    const r = readings.get(id);
    const status = readingStatus(
      r,
      p.capabilities.data?.staleAfterSeconds,
      p.now,
    );
    const unconfirmed = r?.evidence?.status === "unconfirmed";
    return (
      <div
        className={`cockpit-metric ${big ? "big" : ""}`}
        key={id}
        title={`${def?.source || ""}\n接收 ${displayDate(r?.receivedAt)}`}
      >
        <span>{def?.name || id}</span>
        <div>
          <b>
            {unconfirmed
              ? "—"
              : displayMetricValue(r?.value).replace("null", "—")}
          </b>
          <small>{def?.unit || ""}</small>
        </div>
        <em className={status === "已接收" ? "good" : ""}>{status}</em>
      </div>
    );
  }
  return (
    <div className="cockpit">
      <header className="cockpit-header">
        <div className="cockpit-label">
          <span className="system-emblem">农</span>
          <div>
            <b>装备管控</b>
            <small>现场数据监控</small>
          </div>
        </div>
        <div className="cockpit-title">
          <h1>{APP_TITLE}</h1>
          <p>
            <span
              className={`status-dot ${p.connection === "connected" ? "good" : ""}`}
            />
            {p.connection === "connected" ? "实时通道在线" : "实时通道未连接"}
            <span className="title-separator" />
            单棚运行视图
          </p>
        </div>
        <div className="cockpit-clock">
          <b>{time}</b>
          <span>北京时间 +08:00</span>
          <SessionActions />
        </div>
      </header>
      <nav className="cockpit-nav" aria-label="业务功能">
        <span className="current">运行总览</span>
        {shortcuts.map(([to, label, Icon]) => (
          <Link to={to} key={to}>
            <Icon size={14} />
            {label}
          </Link>
        ))}
        <button onClick={toggleFull} title="切换全屏">
          {full ? <Minimize size={14} /> : <Maximize size={14} />}全屏
        </button>
      </nav>
      {(p.snapshot.error || fullscreenError) && (
        <div className="cockpit-notice">
          <QueryNotice
            error={p.snapshot.error}
            loading={false}
            onRetry={() => p.refresh()}
          />
          {fullscreenError}
        </div>
      )}
      <section className="cockpit-kpis" aria-label="关键环境指标">
        {[
          "inside-temp-04",
          "inside-humidity-04",
          "co2",
          "light",
          "oxygen",
          "soil-ph",
        ].map((id) => metric(id, true))}
      </section>
      <div className="cockpit-body">
        <aside className="cockpit-left">
          <ScreenPanel
            title="空气环境"
            icon={<Activity size={16} />}
            to="/trends"
          >
            <div className="sensor-matrix">
              {["co", "uv", "uv-index", "inside-pressure"].map((id) =>
                metric(id),
              )}
            </div>
          </ScreenPanel>
          <ScreenPanel
            title="棚内外对比"
            icon={<Waves size={16} />}
            to="/trends"
          >
            <div className="compare-head">
              <span>指标</span>
              <span>棚内 · 温湿压</span>
              <span>棚外</span>
            </div>
            {[
              ["温度", "inside-temp-06", "outside-temp"],
              ["湿度", "inside-humidity-06", "outside-humidity"],
              ["气压", "inside-pressure", "outside-pressure"],
            ].map(([label, inside, outside]) => (
              <div className="compare-row" key={label}>
                <span>{label}</span>
                {[inside, outside].map((id) => (
                  <b
                    key={id}
                    title={readingStatus(
                      readings.get(id),
                      p.capabilities.data?.staleAfterSeconds,
                      p.now,
                    )}
                  >
                    {readings.get(id)?.evidence?.status === "unconfirmed"
                      ? "—"
                      : displayMetricValue(readings.get(id)?.value).replace(
                          "null",
                          "—",
                        )}{" "}
                    <small>
                      {p.catalog.find((d) => d.id === id)?.unit || ""}
                    </small>
                  </b>
                ))}
              </div>
            ))}
            <p className="panel-footnote">四合一温湿度单独作为顶部主指标</p>
          </ScreenPanel>
          <ScreenPanel
            title="土壤状态"
            icon={<Activity size={16} />}
            to="/trends"
          >
            <div className="sensor-matrix soil-matrix">
              {[
                "soil-temp",
                "soil-humidity",
                "soil-ec",
                "soil-n",
                "soil-p",
                "soil-k",
              ].map((id) => metric(id))}
            </div>
          </ScreenPanel>
        </aside>
        <section className="cockpit-center">
          <div className="equipment-heading">
            <div>
              <span className="section-index">现场装备</span>
              <h2>{s?.site.name || "智慧农业大棚"}</h2>
            </div>
            <Link
              to="/control"
              className={`mode-badge ${monitoring?.mode.state === "invalid" ? "fault" : ""}`}
            >
              <span className="status-dot" />
              {MODE_LABELS[monitoring?.mode.state ?? "unknown"]}
              <ArrowUpRight size={14} />
            </Link>
          </div>
          <GreenhouseDiagram />
          <div className="equipment-summary">
            <div>
              <span>环境有效测点</span>
              <b>
                {s ? received : "—"}
                <small> / {p.catalog.length}</small>
              </b>
            </div>
            <div>
              <span>当前设备故障</span>
              <b className={faults ? "error" : ""}>
                {faults ?? "—"}
                <small> / 18通道</small>
              </b>
            </div>
            <div>
              <span>输出监控</span>
              <b>
                {monitoring?.outputs.filter((o) => o.state !== null).length ??
                  "—"}
                <small> / 10通道</small>
              </b>
            </div>
          </div>
          <div className="output-strip">
            {(monitoring?.outputs ?? []).map((o) => (
              <Link to="/control" key={o.id} title={`PLC D${o.address}`}>
                <i
                  className={
                    o.state === true ? "on" : o.state === false ? "off" : ""
                  }
                />
                <span>{o.name}</span>
              </Link>
            ))}
          </div>
        </section>
        <aside className="cockpit-right">
          <ScreenPanel
            title="故障监测"
            icon={<ShieldAlert size={16} />}
            to="/control#faults"
          >
            <div className="fault-summary">
              <b className={faults ? "error" : ""}>{faults ?? "—"}</b>
              <span>
                当前故障<small>未知通道 {unknowns ?? 18}</small>
              </span>
              <Link to="/alarms">
                事件记录 <ArrowUpRight size={13} />
              </Link>
            </div>
            <FaultPanel compact />
          </ScreenPanel>
          <ScreenPanel title="电力监测" icon={<Zap size={16} />} to="/trends">
            <MeterPanel />
          </ScreenPanel>
          <div className="screen-availability">
            <Link to="/cameras">
              <Video size={15} />
              <span>现场视频</span>
              <b>
                {p.cameras.data?.some((c) => c.online) ? "查看画面" : "未接入"}
              </b>
              <ArrowUpRight size={13} />
            </Link>
            <Link to="/ai">
              <Bot size={15} />
              <span>农业助手</span>
              <b>{p.capabilities.data?.aiEnabled ? "进入会话" : "未配置"}</b>
              <ArrowUpRight size={13} />
            </Link>
          </div>
        </aside>
      </div>
      <section className="trend-strip">
        <TrendPanel
          title="棚内温湿度"
          ids={["inside-temp-04", "inside-humidity-04"]}
        />
        <TrendPanel title="二氧化碳" ids={["co2"]} />
        <TrendPanel title="土壤温湿度" ids={["soil-temp", "soil-humidity"]} />
      </section>
      <footer className="cockpit-footer">
        <span>
          最近数据接收 {displayDate(s?.receivedAt).replace("null", "—")}
        </span>
        <span>PLC输出状态以回读为准 · 未确认能力不执行控制</span>
      </footer>
    </div>
  );
}
function ScreenPanel({
  title,
  icon,
  to,
  children,
}: {
  title: string;
  icon: ReactNode;
  to: string;
  children: ReactNode;
}) {
  return (
    <section className="screen-panel">
      <div className="screen-panel-title">
        <h2>
          {icon}
          {title}
        </h2>
        <Link to={to} aria-label={`查看${title}详情`}>
          <ArrowUpRight size={15} />
        </Link>
      </div>
      {children}
    </section>
  );
}
function TrendPanel({ title, ids }: { title: string; ids: string[] }) {
  const p = usePlatform();
  const aggregation =
    p.capabilities.data?.aggregations.find((a) => a.id === "1m")?.id ??
    p.capabilities.data?.aggregations[0]?.id;
  const series = useResource(
    ["screen-trend", p.siteId, ids.join(","), aggregation],
    (signal) => {
      const to = new Date();
      return api.trend(
        p.siteId,
        ids,
        new Date(to.getTime() - 3600000).toISOString(),
        to.toISOString(),
        aggregation!,
        { signal },
      );
    },
    !!aggregation,
    10000,
  );
  return (
    <section className="screen-panel trend-panel">
      <div className="screen-panel-title">
        <h2>{title}</h2>
        <span>近1小时</span>
        <Link to="/trends" aria-label={`查看${title}历史`}>
          <ArrowUpRight size={15} />
        </Link>
      </div>
      {series.error && <p className="muted">曲线暂不可用</p>}
      <Chart series={series.data || []} definitions={p.catalog} />
    </section>
  );
}
