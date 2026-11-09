import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import {
  api,
  type Parameter,
  type Role,
  type User,
  type TerminalSession,
} from "../sdk";
import { usePlatform, useResource, resourceError } from "../data/Platform";
import { EmptyState } from "../components/EmptyState";
import { QueryNotice, Toolbar, Modal } from "../components/UI";
import { APP_TITLE } from "../data/brand";
import { useQueryClient } from "@tanstack/react-query";
import { displayDate, displayValue } from "../lib/format";
import {
  CommandTracker,
  submissionError,
  type Submission,
} from "../components/CommandFlow";
export function Settings() {
  const p = usePlatform();
  const params = useResource(["parameters", p.siteId], (signal) =>
    api.parameters(p.siteId, { signal }),
  );
  const [density, setDensity] = useState(
    localStorage.getItem("platform.density") || "comfortable",
  );
  const [saved, setSaved] = useState("");
  const save = () => {
    localStorage.setItem("platform.density", density);
    document.documentElement.dataset.density = density;
    setSaved("已保存到本机。");
  };
  return (
    <div className="page">
      <Toolbar title="系统设置" kicker="SYSTEM / CONFIGURATION" />
      <div className="settings-grid">
        <div className="panel settings-card">
          <h3>品牌与显示</h3>
          <div className="form-stack">
            <label>
              平台名称
              <input maxLength={64} value={APP_TITLE} readOnly />
            </label>
            <label>
              信息密度
              <select
                value={density}
                onChange={(e) => setDensity(e.target.value)}
              >
                <option value="comfortable">舒适</option>
                <option value="compact">紧凑</option>
              </select>
            </label>
            <p className="muted">显示偏好仅保存到当前浏览器。</p>
            <button className="primary-button" onClick={save}>
              保存显示偏好
            </button>
            {saved && (
              <p className="green-text" role="status">
                {saved}
              </p>
            )}
          </div>
        </div>
        <div className="panel settings-card">
          <h3>当前会话</h3>
          <div className="connection-info">
            <span>账号</span>
            <b>{displayValue(p.user?.displayName)}</b>
            <span>权限角色</span>
            <b>{p.user ? roleLabels[p.user.role] : "未登录"}</b>
            <span>状态</span>
            <b>{p.user ? "已认证" : "未登录"}</b>
          </div>
          <p>
            管理员可管理账号与参数；操作员可执行获准动作；只读账号查看数据。后端负责最终授权。
          </p>
        </div>
        <div className="panel settings-card">
          <h3>连接状态</h3>
          <div className="connection-info">
            <span>API 服务</span>
            <b>{p.snapshot.data ? "已连接" : "未连接"}</b>
            <span>实时通道</span>
            <b>
              {p.connection === "connected"
                ? "已连接"
                : p.connection === "connecting"
                  ? "连接中"
                  : "未连接"}
            </b>
            <span>站点名称</span>
            <b>{displayValue(p.snapshot.data?.site.name)}</b>
            <span>显示时区</span>
            <b>Asia/Shanghai (+08:00)</b>
          </div>
        </div>
        <div className="panel settings-card">
          <h3>设备参数</h3>
          <QueryNotice
            error={params.error}
            loading={params.isPending}
            onRetry={() => params.refetch()}
          />
          {params.data?.length ? (
            params.data.map((parameter) => (
              <ParameterRow
                parameter={parameter}
                key={`${p.siteId}:${parameter.id}:${parameter.version}`}
              />
            ))
          ) : (
            <EmptyState detail="尚未定义参数与可写范围" />
          )}
        </div>
        <div className="panel settings-card full">
          <Sessions />
        </div>
        <div className="panel settings-card full">
          <Users />
        </div>
      </div>
    </div>
  );
}
const roleLabels: Record<Role, string> = {
  admin: "管理员",
  operator: "操作员",
  viewer: "只读",
};
function ParameterRow({ parameter }: { parameter: Parameter }) {
  const p = usePlatform();
  const [value, setValue] = useState(
    parameter.value === null ? "" : String(parameter.value),
  );
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [submission, setSubmission] = useState<Submission>();
  // 未确认单位、范围、步长及版本时不允许写入，避免将草案参数用于现场控制。
  const allowed =
    p.user?.enabled &&
    p.user.role === "admin" &&
    p.capabilities.data?.parametersWritable &&
    parameter.writable &&
    parameter.siteId === p.siteId &&
    parameter.unit !== null &&
    parameter.min !== null &&
    parameter.max !== null &&
    parameter.step !== null &&
    parameter.step > 0 &&
    !!parameter.version;
  const number = Number(value);
  const valid =
    value.trim() !== "" &&
    Number.isFinite(number) &&
    number >= (parameter.min ?? Infinity) &&
    number <= (parameter.max ?? -Infinity) &&
    parameter.step !== null &&
    Math.abs(
      (number - (parameter.min ?? 0)) / parameter.step -
        Math.round((number - (parameter.min ?? 0)) / parameter.step),
    ) < 1e-7;
  const save = async () => {
    if (lock.current || !allowed || !valid) return;
    lock.current = true;
    setBusy(true);
    const key = crypto.randomUUID();
    try {
      const receipt = await api.updateParameter(
        p.siteId,
        parameter,
        number,
        key,
      );
      setSubmission({ receipt, requestId: key });
    } catch (error) {
      setSubmission(submissionError(error, key));
    } finally {
      setConfirm(false);
      setBusy(false);
      lock.current = false;
    }
  };
  return (
    <div className="parameter-block">
      <div className="parameter-row">
        <span>
          {parameter.name}
          <small>
            当前 {displayValue(parameter.value)} {displayValue(parameter.unit)}
          </small>
        </span>
        <div>
          <input
            type="number"
            step={parameter.step || "any"}
            min={parameter.min ?? undefined}
            max={parameter.max ?? undefined}
            placeholder="尚未回读"
            disabled={!allowed}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            aria-label={parameter.name}
          />
          <button
            className="mini-button"
            disabled={!allowed || !valid || busy}
            onClick={() => setConfirm(true)}
          >
            申请修改
          </button>
        </div>
        <small>
          范围 {displayValue(parameter.min)} — {displayValue(parameter.max)} ·
          步长 {displayValue(parameter.step)}
        </small>
      </div>
      {submission && (
        <CommandTracker submission={submission} key={submission.requestId} />
      )}
      {confirm && (
        <Modal
          title="确认参数修改"
          onClose={() => {
            if (!busy) setConfirm(false);
          }}
        >
          <p>
            {parameter.name}：{displayValue(parameter.value)} → {value}{" "}
            {parameter.unit}
          </p>
          <p className="warning-copy">
            提交后等待实际回读，受理不代表参数已写入。
          </p>
          <button
            className="primary-button"
            disabled={busy || !allowed}
            onClick={save}
          >
            {busy ? "正在提交…" : "确认修改"}
          </button>
        </Modal>
      )}
    </div>
  );
}
function Users() {
  const p = usePlatform();
  const allowed = p.user?.enabled && p.user.role === "admin";
  const users = useResource(
    ["users"],
    (signal) => api.users({ signal }),
    allowed,
  );
  const [create, setCreate] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [edit, setEdit] = useState<User>();
  const [enabled, setEnabled] = useState(true);
  const mutation = useMutation({
    mutationFn: () =>
      edit
        ? api.updateUser(edit.id, role, enabled)
        : api.createUser(username, password, role),
    onSuccess: () => {
      users.refetch();
      setCreate(false);
      setEdit(undefined);
      setPassword("");
      p.refresh();
    },
  });
  return (
    <>
      <div className="panel-title">
        <h3>账号管理</h3>
        <button
          className="secondary-button"
          disabled={!allowed}
          onClick={() => {
            setCreate(true);
            setRole("viewer");
            mutation.reset();
          }}
        >
          <Plus size={14} />
          新建账号
        </button>
      </div>
      {!allowed ? (
        <div className="permission-state">
          {p.user
            ? "当前角色没有账号管理权限。"
            : "登录管理员账号后可管理用户。"}
        </div>
      ) : (
        <>
          <QueryNotice error={users.error} loading={users.isPending} />
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>账号</th>
                  <th>姓名</th>
                  <th>角色</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {users.data?.length ? (
                  users.data.map((user) => (
                    <tr key={user.id}>
                      <td>{user.username}</td>
                      <td>{user.displayName}</td>
                      <td>{roleLabels[user.role]}</td>
                      <td>{user.enabled ? "启用" : "停用"}</td>
                      <td>
                        <button
                          className="text-button"
                          onClick={() => {
                            setEdit(user);
                            setRole(user.role);
                            setEnabled(user.enabled);
                            mutation.reset();
                          }}
                        >
                          编辑
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5}>
                      <EmptyState />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
      {(create || edit) && (
        <Modal
          title={edit ? "编辑账号权限" : "新建账号"}
          onClose={() => {
            if (!mutation.isPending) {
              setCreate(false);
              setEdit(undefined);
              setPassword("");
            }
          }}
        >
          <form
            className="form-stack"
            onSubmit={(e) => {
              e.preventDefault();
              if (allowed) mutation.mutate();
            }}
          >
            {!edit && (
              <>
                <label>
                  账号
                  <input
                    required
                    autoComplete="off"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                  />
                </label>
                <label>
                  初始密码
                  <input
                    required
                    type="password"
                    autoComplete="new-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </label>
              </>
            )}
            <label>
              角色
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as Role)}
              >
                {Object.entries(roleLabels).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            {edit && (
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                />
                启用账号
              </label>
            )}
            {mutation.error && (
              <p className="error" role="alert">
                {resourceError(mutation.error)}
              </p>
            )}
            <button
              className="primary-button"
              disabled={mutation.isPending || !allowed}
            >
              {mutation.isPending ? "正在提交…" : "确认保存"}
            </button>
          </form>
        </Modal>
      )}
    </>
  );
}

function Sessions() {
  const p = usePlatform();
  const cache = useQueryClient();
  const sessions = useResource(
    ["terminal-sessions"],
    (signal) => api.terminalSessions({ signal }),
    !!p.user,
    30000,
  );
  const [target, setTarget] = useState<TerminalSession>();
  const revoke = useMutation({
    mutationFn: (session: TerminalSession) => api.revokeSession(session.id),
    onSuccess: (_, session) => {
      setTarget(undefined);
      if (session.current) {
        api.setCsrfToken(null);
        p.setAuthExpired(true);
        cache.clear();
      } else void sessions.refetch();
    },
  });
  return (
    <>
      <div className="panel-title">
        <h3>终端会话管理</h3>
        <button className="text-button" onClick={() => sessions.refetch()}>
          刷新
        </button>
      </div>
      <p className="muted">
        {p.user?.role === "admin"
          ? "显示所有账号的活跃会话"
          : "显示当前账号的活跃会话"}
        。撤销一端仅使该会话失效。浏览器会话恢复功能可能保留登录状态。
      </p>
      <QueryNotice error={sessions.error} loading={sessions.isPending} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>账号 / 终端</th>
              <th>登录时间（+08:00）</th>
              <th>最晚失效（+08:00）</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {sessions.data?.map((session) => (
              <tr key={session.id}>
                <td>
                  <b>
                    {session.username}
                    {session.current && " · 当前终端"}
                  </b>
                  <small className="session-agent">
                    {session.userAgent || "浏览器信息未提供"}
                  </small>
                </td>
                <td>{displayDate(session.createdAt)}</td>
                <td>{displayDate(session.expiresAt)}</td>
                <td>
                  <button
                    className="text-button"
                    onClick={() => {
                      setTarget(session);
                      revoke.reset();
                    }}
                  >
                    撤销会话
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {target && (
        <Modal
          title="撤销终端会话"
          onClose={() => {
            if (!revoke.isPending) setTarget(undefined);
          }}
        >
          <p>
            撤销 {target.username} 的{target.current ? "当前" : "所选"}
            会话，其他独立登录的终端继续有效。
          </p>
          {revoke.error && (
            <p role="alert" className="error">
              {resourceError(revoke.error)}
            </p>
          )}
          <button
            className="primary-button"
            disabled={revoke.isPending}
            onClick={() => revoke.mutate(target)}
          >
            {revoke.isPending ? "正在撤销…" : "确认撤销"}
          </button>
        </Modal>
      )}
    </>
  );
}
