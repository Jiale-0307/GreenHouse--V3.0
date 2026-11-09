import { useState } from "react";
import { SlidersHorizontal, RotateCcw, Search } from "lucide-react";
import { api } from "../sdk";
import { usePlatform, useResource } from "../data/Platform";
import { Chart } from "../components/Chart";
import { QueryNotice, Toolbar } from "../components/UI";
export function Trends() {
  const p = usePlatform();
  const ranges = p.capabilities.data?.historyRanges || [];
  const aggregations = p.capabilities.data?.aggregations || [];
  const [selected, setSelected] = useState<string[]>(["inside-temp-04"]);
  const [range, setRange] = useState("");
  const [aggregation, setAggregation] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [error, setError] = useState("");
  const [request, setRequest] = useState<{
    ids: string[];
    from: string;
    to: string;
    aggregation: string;
    site: string;
  }>();
  const rangeId = range || ranges[0]?.id || "";
  const aggregationId = aggregation || aggregations[0]?.id || "";
  const query = useResource(
    ["trends", request],
    (signal) =>
      api.trend(
        request!.site,
        request!.ids,
        request!.from,
        request!.to,
        request!.aggregation,
        { signal },
      ),
    !!request && request.site === p.siteId,
  );
  const search = () => {
    setError("");
    const ids = selected.filter((id) => p.catalog.some((m) => m.id === id));
    if (!ids.length || !aggregationId) {
      setError("请选择测点与后端支持的聚合方式。");
      return;
    }
    const end = rangeId === "custom" ? new Date(`${to}:00+08:00`) : new Date();
    const start =
      rangeId === "custom"
        ? new Date(`${from}:00+08:00`)
        : new Date(
            end.getTime() -
              (ranges.find((r) => r.id === rangeId)?.seconds || 0) * 1000,
          );
    if (
      !Number.isFinite(start.getTime()) ||
      !Number.isFinite(end.getTime()) ||
      start >= end
    ) {
      setError("请填写有效的开始/结束时间，开始时间必须早于结束时间。");
      return;
    }
    setRequest({
      ids,
      from: start.toISOString(),
      to: end.toISOString(),
      aggregation: aggregationId,
      site: p.siteId,
    });
  };
  return (
    <div className="page">
      <Toolbar title="历史趋势" kicker="HISTORY / TRENDS">
        <span className="toolbar-note">范围与聚合方式由站点能力提供</span>
      </Toolbar>
      <QueryNotice
        error={p.capabilities.error}
        loading={p.capabilities.isPending}
        onRetry={() => p.capabilities.refetch()}
      />
      <div className="filter-bar">
        <div className="filter-title">
          <SlidersHorizontal size={15} />
          选择测点
        </div>
        <div className="metric-select-list">
          {p.catalog.map((m) => (
            <label key={m.id}>
              <input
                type="checkbox"
                checked={selected.includes(m.id)}
                onChange={(e) =>
                  setSelected((v) =>
                    e.target.checked
                      ? [...v, m.id]
                      : v.filter((id) => id !== m.id),
                  )
                }
              />
              {m.name}
              <small>{m.source}</small>
            </label>
          ))}
        </div>
        <div className="custom-range">
          <label>
            时间范围
            <select
              disabled={!ranges.length}
              value={rangeId}
              onChange={(e) => setRange(e.target.value)}
            >
              {!ranges.length && <option value="">未配置</option>}
              {ranges.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
              {!!ranges.length && <option value="custom">自定义</option>}
            </select>
          </label>
          <label>
            聚合
            <select
              disabled={!aggregations.length}
              value={aggregationId}
              onChange={(e) => setAggregation(e.target.value)}
            >
              {!aggregations.length && <option value="">未配置</option>}
              {aggregations.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </select>
          </label>
          {rangeId === "custom" && (
            <>
              <label>
                开始（+08:00）
                <input
                  type="datetime-local"
                  value={from}
                  onChange={(e) => setFrom(e.target.value)}
                />
              </label>
              <label>
                结束（+08:00）
                <input
                  type="datetime-local"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                />
              </label>
            </>
          )}
          <button
            className="secondary-button"
            onClick={() => {
              setFrom("");
              setTo("");
              setRequest(undefined);
              setError("");
              setSelected([]);
            }}
          >
            <RotateCcw size={13} />
            重置
          </button>
          <button
            className="primary-button"
            disabled={
              !ranges.length || !aggregations.length || query.isFetching
            }
            onClick={search}
          >
            <Search size={14} />
            查询
          </button>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>
      <QueryNotice error={query.error} loading={query.isFetching} />
      <div className="panel large">
        <Chart
          series={request?.site === p.siteId ? query.data || [] : []}
          definitions={p.catalog}
        />
        <p className="chart-caption">
          时间显示与查询使用 Asia/Shanghai (+08:00) · 曲线保留缺测断点
        </p>
      </div>
    </div>
  );
}
