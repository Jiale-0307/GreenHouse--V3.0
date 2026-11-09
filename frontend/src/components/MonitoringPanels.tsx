import { useState, useRef } from "react";
import { usePlatform } from "../data/Platform";
import { freshMonitoring } from "../data/monitoring";
import { MODE_LABELS } from "../data/brand";
import { displayDate, displayMetricValue } from "../lib/format";
import { api, type SiteMode } from "../sdk";
import { Modal } from "./UI";
import {
  CommandTracker,
  submissionError,
  type Submission,
} from "./CommandFlow";
export function useMonitoring() {
  const p = usePlatform();
  return freshMonitoring(
    p.snapshot.data?.monitoring,
    p.now,
    p.capabilities.data?.staleAfterSeconds ?? 90,
  );
}
export function ModePanel() {
  const p = usePlatform();
  const m = useMonitoring()?.mode;
  const [target, setTarget] = useState<SiteMode>();
  const [submission, setSubmission] = useState<Submission>();
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const allowed = !!m?.writable && !!p.user && p.user.role !== "viewer";
  const submit = async () => {
    if (!allowed || !target || !m || lock.current) return;
    lock.current = true;
    setBusy(true);
    const key = crypto.randomUUID();
    try {
      setSubmission({
        receipt: await api.setSiteMode(p.siteId, target, m.version, key),
        requestId: key,
      });
    } catch (error) {
      setSubmission(submissionError(error, key));
    } finally {
      lock.current = false;
      setBusy(false);
      setTarget(undefined);
    }
  };
  return (
    <section className="panel mode-panel">
      <div className="panel-heading">
        <h2>整棚运行模式</h2>
        <span
          className={`state-label ${m?.state === "invalid" ? "fault" : ""}`}
        >
          {MODE_LABELS[m?.state ?? "unknown"]}
        </span>
      </div>
      <div className="mode-options">
        {(["auto", "manual", "stopped"] as const).map((mode) => (
          <button
            key={mode}
            disabled={!allowed || busy}
            className={m?.state === mode ? "selected" : ""}
            onClick={() => setTarget(mode)}
          >
            {MODE_LABELS[mode]}
          </button>
        ))}
      </div>
      {!allowed && (
        <p className="muted">
          {m?.disabledReason || "尚未取得模式回读；远程切换未启用。"}
        </p>
      )}
      <small className="muted">
        最近回读 {displayDate(m?.receivedAt)} · 停止模式不等同于现场急停
      </small>
      {submission && (
        <CommandTracker submission={submission} key={submission.requestId} />
      )}
      {target && (
        <Modal
          title="确认切换整棚模式"
          onClose={() => {
            if (!busy) setTarget(undefined);
          }}
        >
          <p>切换为{MODE_LABELS[target]}，完成状态以PLC回读为准。</p>
          <button
            className="primary-button"
            disabled={busy || !allowed}
            onClick={submit}
          >
            确认切换
          </button>
        </Modal>
      )}
    </section>
  );
}
export function FaultPanel({ compact = false }: { compact?: boolean }) {
  const m = useMonitoring();
  const faults = m?.faults ?? [];
  const visible = compact
    ? [...faults]
        .sort(
          (a, b) =>
            (a.state === "fault" ? -1 : 1) - (b.state === "fault" ? -1 : 1),
        )
        .slice(0, 5)
    : faults;
  return (
    <div className={`fault-list ${compact ? "compact" : ""}`}>
      {visible.length ? (
        visible.map((f) => (
          <div
            className={`fault-row ${f.state}`}
            key={f.id}
            title={`D${f.address} · ${displayDate(f.receivedAt)}`}
          >
            <i />
            <span>{f.name}</span>
            <b>
              {f.state === "fault"
                ? "故障"
                : f.state === "normal"
                  ? "正常"
                  : "未知"}
            </b>
            {!compact && <small>D{f.address}</small>}
          </div>
        ))
      ) : (
        <div className="monitor-empty">尚未收到故障通道数据</div>
      )}
    </div>
  );
}
export function MeterPanel() {
  const meter = useMonitoring()?.meter;
  return (
    <div className="meter-content">
      <span className="state-label">
        {meter?.mappingConfirmed
          ? meter.status === "good"
            ? "实时读取"
            : "数据未知 / 过期"
          : "映射待确认"}
      </span>
      {meter?.mappingConfirmed && meter.values.length ? (
        <div className="meter-values">
          {meter.values.map((v) => (
            <div key={v.metricId}>
              <span>{v.name}</span>
              <b>
                {displayMetricValue(v.value)} <small>{v.unit}</small>
              </b>
            </div>
          ))}
        </div>
      ) : (
        <div className="meter-pending">
          <b>—</b>
          <p>等待确认电参量与换算关系</p>
          <small>已预留 D270–D273 原始缓冲区读取</small>
        </div>
      )}
      <details>
        <summary>缓冲区与接收时间</summary>
        <div className="raw-registers">
          {[0, 1, 2, 3].map((i) => (
            <span key={i}>
              D{270 + i}
              <b>{meter?.rawRegisters?.[i] ?? "—"}</b>
            </span>
          ))}
        </div>
        <small>{displayDate(meter?.receivedAt)}</small>
      </details>
    </div>
  );
}
