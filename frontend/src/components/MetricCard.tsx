import { Droplets, Thermometer, Wind, Leaf } from "lucide-react";
import type { MetricDefinition, MetricReading } from "../sdk";
import { displayDate, displayMetricValue, readingStatus } from "../lib/format";
export function MetricCard({
  definition,
  reading,
  staleAfter,
  now,
}: {
  definition: MetricDefinition;
  reading?: MetricReading;
  staleAfter?: number | null;
  now?: number;
}) {
  const status = readingStatus(reading, staleAfter, now);
  const Icon = definition.id.includes("temp")
    ? Thermometer
    : definition.id.includes("humidity")
      ? Droplets
      : definition.group === "土壤"
        ? Leaf
        : Wind;
  return (
    <article
      className="metric-card"
      title={`来源：${definition.source}\n通道：${reading?.evidence?.sources.map((s) => `D${s.address}=${s.value ?? "缺测"}`).join(" / ") || "单值读取"}\n采集：${displayDate(reading?.observedAt)}\n接收：${displayDate(reading?.receivedAt)}`}
    >
      <div className="metric-head">
        <span>
          <Icon size={13} />
          {definition.name}
        </span>
        <span className={`quality ${status === "已接收" ? "ok" : ""}`}>
          {status}
        </span>
      </div>
      <div className="metric-value">
        {displayMetricValue(
          reading?.quality === "invalid" ||
            reading?.evidence?.status === "unconfirmed"
            ? null
            : reading?.value,
        )}{" "}
        <small>{definition.unit || ""}</small>
      </div>
      <div className="metric-meta">
        {definition.group} · {definition.source}
        {reading?.evidence?.status === "missing" && (
          <small>保留末次有效值 · {displayDate(reading.receivedAt)}</small>
        )}
      </div>
    </article>
  );
}
