import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type Alarm } from "../sdk";
import { usePlatform, useResource, resourceError } from "../data/Platform";
import { EmptyState } from "../components/EmptyState";
import { QueryNotice, Toolbar, Modal, Pagination } from "../components/UI";
import { displayDate, displayValue, statusLabels } from "../lib/format";
const alarmStatus = {
  open: "待处理",
  acknowledged: "已确认",
  closed: "已关闭",
};
const levels = { info: "提示", warning: "警告", critical: "严重" };
export function Alarms() {
  const p = usePlatform();
  const [page, setPage] = useState(1);
  const [level, setLevel] = useState("");
  const [status, setStatus] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [detail, setDetail] = useState<Alarm>();
  const filters = {
    page: String(page),
    pageSize: "20",
    ...(level ? { level } : {}),
    ...(status ? { status } : {}),
    ...dateFilters(from, to),
  };
  const query = useResource(["alarms", p.siteId, filters], (signal) =>
    api.alarms(p.siteId, filters, { signal }),
  );
  const ack = useMutation({
    mutationFn: (id: string) => api.acknowledge(p.siteId, id),
    onSuccess: (alarm) => {
      setDetail(alarm);
      query.refetch();
      p.refresh();
    },
  });
  const canAck =
    p.user?.enabled &&
    p.user.role !== "viewer" &&
    p.capabilities.data?.alarmAcknowledge;
  return (
    <div className="page">
      <Toolbar title="报警中心" kicker="ALERTS / REVIEW" />
      <div className="record-filters">
        <label>
          报警等级
          <select
            value={level}
            onChange={(e) => {
              setLevel(e.target.value);
              setPage(1);
            }}
          >
            <option value="">全部等级</option>
            {Object.entries(levels).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          处理状态
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="">全部状态</option>
            {Object.entries(alarmStatus).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <DateInputs
          from={from}
          to={to}
          setFrom={(v) => {
            setFrom(v);
            setPage(1);
          }}
          setTo={(v) => {
            setTo(v);
            setPage(1);
          }}
        />
      </div>
      <QueryNotice
        error={query.error}
        loading={query.isFetching}
        onRetry={() => query.refetch()}
      />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>等级</th>
              <th>报警</th>
              <th>状态</th>
              <th>发生时间（+08:00）</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {query.data?.items.length ? (
              query.data.items.map((a) => (
                <tr key={a.id}>
                  <td>
                    <span className={`level ${a.level}`}>
                      {levels[a.level]}
                    </span>
                  </td>
                  <td>{a.title}</td>
                  <td>{alarmStatus[a.status]}</td>
                  <td>{displayDate(a.occurredAt)}</td>
                  <td>
                    <button
                      className="text-button"
                      onClick={() => {
                        setDetail(a);
                        ack.reset();
                      }}
                    >
                      详情
                    </button>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5}>
                  <EmptyState detail="暂无报警记录" />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Pagination
        page={page}
        setPage={setPage}
        total={query.data?.total}
        count={query.data?.items.length || 0}
      />
      {detail && (
        <Modal title="报警详情" onClose={() => setDetail(undefined)}>
          <div className="confirm-copy">
            <h4>{detail.title}</h4>
            <p>{displayValue(detail.detail)}</p>
            <p>
              {displayDate(detail.occurredAt)} · {alarmStatus[detail.status]}
            </p>
            <p>来源：{detail.source || "平台报警"}</p>
            <p>人工确认：{displayDate(detail.acknowledgedAt)}</p>
            <p>故障恢复：{displayDate(detail.recoveredAt)}</p>
            {detail.source && (
              <p className="muted">
                确认表示已知悉；故障恢复由PLC后续正常回读判定。
              </p>
            )}
            {ack.error && (
              <p className="error" role="alert">
                {resourceError(ack.error)}
              </p>
            )}
            <button
              className="primary-button"
              disabled={
                !canAck ||
                !detail.canAcknowledge ||
                detail.status !== "open" ||
                ack.isPending
              }
              onClick={() => ack.mutate(detail.id)}
            >
              {ack.isPending ? "正在确认…" : "确认报警"}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
export function Logs() {
  const p = usePlatform();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [actor, setActor] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const filters = {
    page: String(page),
    pageSize: "20",
    ...(status ? { status } : {}),
    ...(actor ? { actor } : {}),
    ...dateFilters(from, to),
  };
  const query = useResource(["logs", p.siteId, filters], (signal) =>
    api.logs(p.siteId, filters, { signal }),
  );
  return (
    <div className="page">
      <Toolbar title="操作日志" kicker="AUDIT / OPERATIONS">
        <span className="toolbar-note">区分已受理、执行中与实际回读</span>
      </Toolbar>
      <div className="record-filters">
        <label>
          操作人
          <input
            value={actor}
            onChange={(e) => {
              setActor(e.target.value);
              setPage(1);
            }}
            placeholder="按账号检索"
          />
        </label>
        <label>
          执行状态
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="">全部状态</option>
            {Object.entries(statusLabels).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <DateInputs
          from={from}
          to={to}
          setFrom={(v) => {
            setFrom(v);
            setPage(1);
          }}
          setTo={(v) => {
            setTo(v);
            setPage(1);
          }}
        />
      </div>
      <QueryNotice
        error={query.error}
        loading={query.isFetching}
        onRetry={() => query.refetch()}
      />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>操作人</th>
              <th>动作</th>
              <th>对象</th>
              <th>请求时间（+08:00）</th>
              <th>状态</th>
              <th>结果</th>
            </tr>
          </thead>
          <tbody>
            {query.data?.items.length ? (
              query.data.items.map((l) => (
                <tr key={l.id}>
                  <td>{displayValue(l.actor)}</td>
                  <td>{l.action}</td>
                  <td>{l.target}</td>
                  <td>{displayDate(l.requestedAt)}</td>
                  <td>
                    <span className={`status-pill ${l.status}`}>
                      {statusLabels[l.status]}
                    </span>
                  </td>
                  <td>{displayValue(l.result)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6}>
                  <EmptyState detail="暂无操作日志" />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Pagination
        page={page}
        setPage={setPage}
        total={query.data?.total}
        count={query.data?.items.length || 0}
      />
    </div>
  );
}
function dateFilters(from: string, to: string) {
  return {
    ...(from ? { from: `${from}:00+08:00` } : {}),
    ...(to ? { to: `${to}:00+08:00` } : {}),
  };
}
function DateInputs({
  from,
  to,
  setFrom,
  setTo,
}: {
  from: string;
  to: string;
  setFrom: (v: string) => void;
  setTo: (v: string) => void;
}) {
  return (
    <>
      <label>
        起始（+08:00）
        <input
          type="datetime-local"
          value={from}
          max={to || undefined}
          onChange={(e) => setFrom(e.target.value)}
        />
      </label>
      <label>
        截止（+08:00）
        <input
          type="datetime-local"
          value={to}
          min={from || undefined}
          onChange={(e) => setTo(e.target.value)}
        />
      </label>
    </>
  );
}
