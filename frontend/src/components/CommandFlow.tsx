import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Clock3 } from "lucide-react";
import {
  api,
  ApiError,
  type Actuator,
  type CommandReceipt,
  type ControlIntent,
} from "../sdk";
import { usePlatform } from "../data/Platform";
import {
  canControl,
  commandLabel,
  displayDate,
  displayValue,
} from "../lib/format";
import { Modal } from "./UI";
export interface Submission {
  receipt?: CommandReceipt;
  requestId: string;
  error?: string;
  rejected?: boolean;
}
export function CommandTracker({ submission }: { submission: Submission }) {
  const p = usePlatform();
  const cache = useQueryClient();
  const [expired, setExpired] = useState(false);
  const initial = submission.receipt;
  const query = useQuery({
    queryKey: ["command", initial?.siteId, initial?.commandId],
    queryFn: ({ signal }) =>
      api.command(initial!.siteId, initial!.commandId, { signal }),
    enabled: !!initial && initial.siteId === p.siteId,
    initialData: initial,
    retry: false,
    refetchInterval: (q) =>
      !expired && ["accepted", "executing"].includes(q.state.data?.status || "")
        ? 2000
        : false,
  });
  const receipt = query.data;
  useEffect(() => {
    setExpired(false);
    if (!initial) return;
    const timer = setTimeout(
      () => setExpired(true),
      (p.capabilities.data?.commandTimeoutSeconds || 30) * 1000,
    );
    return () => clearTimeout(timer);
  }, [initial?.commandId, p.capabilities.data?.commandTimeoutSeconds]);
  useEffect(() => {
    if (receipt?.status === "succeeded") {
      cache.invalidateQueries({ queryKey: ["snapshot", p.siteId] });
      cache.invalidateQueries({ queryKey: ["actuators", p.siteId] });
      cache.invalidateQueries({ queryKey: ["parameters", p.siteId] });
    }
  }, [receipt?.status, cache, p.siteId]);
  const pending =
    !!receipt && ["accepted", "executing"].includes(receipt.status);
  const label = submission.error
    ? submission.rejected
      ? "请求被拒绝"
      : "结果未知"
    : commandLabel(receipt, expired && pending);
  return (
    <div className="command-result" role="status">
      <div className="result-title">
        {receipt?.status === "succeeded" && receipt.readbackAt ? (
          <CheckCircle2 size={18} />
        ) : pending && !expired ? (
          <Clock3 size={18} />
        ) : (
          <AlertCircle size={18} />
        )}
        <b>{label}</b>
      </div>
      <p>{submission.error || receipt?.result || "等待后端返回执行结果"}</p>
      <div className="result-meta">
        请求标识：{submission.requestId}
        <br />
        指令标识：{displayValue(receipt?.commandId)}
        <br />
        实际回读：{displayDate(receipt?.readbackAt)}
      </div>
      {(!receipt || expired) && (
        <p className="warning-copy">
          请查阅操作日志及现场状态，避免重复提交未知结果的动作。
        </p>
      )}
    </div>
  );
}
export function submissionError(error: unknown, requestId: string): Submission {
  const rejected =
    error instanceof ApiError && error.status >= 400 && error.status < 500;
  return {
    requestId,
    rejected,
    error:
      error instanceof Error ? error.message : "连接失败，请查询日志确认结果",
  };
}
export function ControlDialog({
  actuator,
  intent,
  onClose,
  onSubmitted,
}: {
  actuator: Actuator;
  intent: ControlIntent;
  onClose: () => void;
  onSubmitted: (s: Submission) => void;
}) {
  const p = usePlatform();
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [key] = useState(() => crypto.randomUUID());
  const allowed =
    actuator.siteId === p.siteId &&
    intent.actuatorId === actuator.id &&
    !!actuator.version &&
    (intent.action !== "set_mode" ||
      ["manual", "auto"].includes(String(intent.parameters.mode))) &&
    canControl(p.user, p.capabilities.data, actuator, intent.action);
  const submit = async () => {
    if (lock.current || !allowed) return;
    lock.current = true;
    setBusy(true);
    try {
      const receipt = await api.sendCommand(
        p.siteId,
        {
          actuatorId: actuator.id,
          action: intent.action,
          parameters: intent.parameters,
          expectedVersion: actuator.version,
        },
        key,
      );
      onSubmitted({ receipt, requestId: key });
    } catch (error) {
      onSubmitted(submissionError(error, key));
    } finally {
      setBusy(false);
      onClose();
    }
  };
  return (
    <Modal
      title="确认设备动作"
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <div className="confirm-copy">
        <p>
          目标设备：<b>{actuator.name}</b>
        </p>
        <p>
          操作：
          <b>
            {actuator.actions.find((a) => a.id === intent.action)?.label ||
              (intent.action === "set_mode" ? "切换模式" : intent.action)}
          </b>
        </p>
        {intent.reason && <p>依据：{intent.reason}</p>}
        <dl className="intent-details">
          {Object.entries(intent.parameters).map(([key, value]) => (
            <div key={key}>
              <dt>{key === "mode" ? "目标模式" : key}</dt>
              <dd>
                {key === "mode"
                  ? value === "auto"
                    ? "自动"
                    : "手动"
                  : displayValue(
                      typeof value === "object" ? JSON.stringify(value) : value,
                    )}
              </dd>
            </div>
          ))}
        </dl>
        <p className="warning-copy">
          提交后以实际回读为准。未收到结果时请先查询日志与现场状态。
        </p>
        {!allowed && (
          <p role="alert" className="error">
            当前权限或能力不允许此动作。
          </p>
        )}
        <div className="modal-actions">
          <button
            className="secondary-button"
            disabled={busy}
            onClick={onClose}
          >
            取消
          </button>
          <button
            className="primary-button"
            disabled={!allowed || busy}
            onClick={submit}
          >
            {busy ? "正在提交…" : "确认提交"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
