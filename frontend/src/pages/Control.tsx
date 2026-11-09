import {
  ModePanel,
  FaultPanel,
  useMonitoring,
} from "../components/MonitoringPanels";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Fan,
  Flame,
  Lightbulb,
  Droplets,
  Blinds,
  Settings2,
} from "lucide-react";
import { api, type Actuator, type ControlIntent } from "../sdk";
import { usePlatform, useResource } from "../data/Platform";
import { actuatorCatalog } from "../data/catalog";
import { canControl, displayValue } from "../lib/format";
import { QueryNotice, Toolbar } from "../components/UI";
import {
  CommandTracker,
  ControlDialog,
  type Submission,
} from "../components/CommandFlow";
export function Control() {
  const monitoring = useMonitoring();
  const p = usePlatform();
  const location = useLocation();
  const navigate = useNavigate();
  const actuators = useResource(["actuators", p.siteId], (signal) =>
    api.actuators(p.siteId, { signal }),
  );
  const [confirm, setConfirm] = useState<{
    actuator: Actuator;
    intent: ControlIntent;
  } | null>(null);
  const [submission, setSubmission] = useState<Submission>();
  const [blocked, setBlocked] = useState("");
  const [modes, setModes] = useState<Record<string, "manual" | "auto">>({});
  const list = actuators.data || p.snapshot.data?.actuators || [];
  useEffect(() => {
    const state = location.state as {
      intent?: ControlIntent;
      siteId?: string;
    } | null;
    if (!state?.intent || !actuators.data) return;
    const actuator = actuators.data.find(
      (a) => a.id === state.intent!.actuatorId,
    );
    if (
      state.siteId === p.siteId &&
      actuator &&
      canControl(p.user, p.capabilities.data, actuator, state.intent.action)
    )
      setConfirm({ actuator, intent: state.intent });
    else setBlocked("建议暂不能执行：设备能力、站点或当前权限不匹配。");
    navigate("/control", { replace: true, state: null });
  }, [
    location.state,
    actuators.data,
    navigate,
    p.siteId,
    p.user,
    p.capabilities.data,
  ]);
  const icons = [
    Fan,
    Flame,
    Lightbulb,
    Droplets,
    Droplets,
    Droplets,
    Blinds,
    Settings2,
  ];
  return (
    <div className="page">
      <ModePanel />
      <section className="panel output-panel">
        <div className="panel-heading">
          <h2>PLC输出回读</h2>
          <span>输出信号不代表机械到位</span>
        </div>
        <div className="output-grid">
          {monitoring?.outputs.map((o) => (
            <div key={o.id}>
              <span>{o.name}</span>
              <b className={o.state === true ? "green-text" : ""}>
                {o.state === true
                  ? "输出开启"
                  : o.state === false
                    ? "输出关闭"
                    : "未知"}
              </b>
              <small>D{o.address}</small>
            </div>
          )) || <p>尚未收到输出回读</p>}
        </div>
      </section>
      <section className="panel" id="faults">
        <div className="panel-heading">
          <h2>设备与传感器故障</h2>
          <span>0 故障 / 1 正常 · 18通道</span>
        </div>
        <FaultPanel />
      </section>
      <Toolbar title="设备控制" kicker="CONTROL / SAFE ACTION">
        <span className="toolbar-note">二次确认 · 执行跟踪 · 实际回读</span>
      </Toolbar>
      <div className="info-banner">
        {!p.user
          ? "未登录，仅可查看设备状态。"
          : p.user.role === "viewer"
            ? "当前账号为只读角色。"
            : !p.capabilities.data?.controlEnabled
              ? "远程控制能力未启用。"
              : "现场保护与联锁由后端及 PLC 执行。"}{" "}
        未收到能力定义的动作保持禁用。
      </div>
      <QueryNotice
        error={actuators.error}
        loading={actuators.isPending}
        onRetry={() => actuators.refetch()}
      />
      {blocked && <p className="error">{blocked}</p>}
      {submission && (
        <CommandTracker key={submission.requestId} submission={submission} />
      )}
      <div className="control-grid">
        {(list.length
          ? list
          : actuatorCatalog.map(
              (name, i) =>
                ({
                  id: `unconfigured-${i}`,
                  siteId: p.siteId,
                  name,
                  kind: "unknown",
                  state: null,
                  mode: null,
                  version: "",
                  actions: [],
                  modeWritable: false,
                }) as Actuator,
            )
        ).map((a, i) => {
          const Icon = icons[i % icons.length];
          return (
            <div className="control-card" key={a.id}>
              <div className="control-card-head">
                <span className="control-icon">
                  <Icon size={20} />
                </span>
                <div>
                  <b>{a.name}</b>
                  <small>
                    当前状态{" "}
                    {typeof a.state === "boolean"
                      ? a.state
                        ? "开启"
                        : "关闭"
                      : displayValue(a.state)}
                  </small>
                </div>
                <span className="mode-badge">
                  {a.mode === "auto"
                    ? "自动"
                    : a.mode === "manual"
                      ? "手动"
                      : "未回读"}
                </span>
              </div>
              <div className="control-actions">
                {a.actions.length ? (
                  a.actions.map((action) => (
                    <button
                      key={action.id}
                      disabled={
                        !canControl(p.user, p.capabilities.data, a, action.id)
                      }
                      onClick={() =>
                        setConfirm({
                          actuator: a,
                          intent: {
                            actuatorId: a.id,
                            action: action.id,
                            parameters: {},
                            reason: "手动操作",
                          },
                        })
                      }
                    >
                      {action.label}
                    </button>
                  ))
                ) : (
                  <button disabled>动作未配置</button>
                )}
              </div>
              <div className="mode-row">
                <span>控制模式</span>
                <select
                  aria-label={`${a.name}目标模式`}
                  disabled={
                    !canControl(p.user, p.capabilities.data, a, "set_mode")
                  }
                  value={modes[a.id] || "manual"}
                  onChange={(e) =>
                    setModes((m) => ({
                      ...m,
                      [a.id]: e.target.value as "manual" | "auto",
                    }))
                  }
                >
                  <option value="manual">手动</option>
                  <option value="auto">自动</option>
                </select>
                <button
                  disabled={
                    !canControl(p.user, p.capabilities.data, a, "set_mode")
                  }
                  className="text-button"
                  onClick={() =>
                    setConfirm({
                      actuator: a,
                      intent: {
                        actuatorId: a.id,
                        action: "set_mode",
                        parameters: { mode: modes[a.id] || "manual" },
                        reason: "手动切换模式",
                      },
                    })
                  }
                >
                  申请切换
                </button>
              </div>
            </div>
          );
        })}
      </div>
      {confirm && (
        <ControlDialog
          actuator={confirm.actuator}
          intent={confirm.intent}
          onClose={() => setConfirm(null)}
          onSubmitted={setSubmission}
        />
      )}
    </div>
  );
}
