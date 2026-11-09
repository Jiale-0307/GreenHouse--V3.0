import type {
  Capabilities,
  MetricReading,
  User,
  Actuator,
  CommandReceipt,
} from "../sdk";
export const displayValue = (value: unknown, suffix = "") =>
  value === null ||
  value === undefined ||
  value === "" ||
  (typeof value === "number" && !Number.isFinite(value))
    ? "—"
    : `${value}${suffix}`;
// PLC单精度浮点数约有7位有效数字；展示时消除23.3999996等二进制尾差，原始值仍完整保存在后端。
export const displayMetricValue = (value: number | null | undefined) =>
  value != null && Number.isFinite(value)
    ? new Intl.NumberFormat("zh-CN", {
        maximumSignificantDigits: 7,
        useGrouping: false,
      }).format(value)
    : "—";
export const displayDate = (value: string | null | undefined) =>
  value && !Number.isNaN(Date.parse(value))
    ? `${new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date(value))} +08:00`
    : "—";
export function readingStatus(
  reading: MetricReading | undefined,
  staleAfterSeconds: number | null | undefined,
  now = Date.now(),
) {
  if (!reading) return "未接收";
  if (reading.evidence?.status === "unconfirmed") return "单位待确认";
  if (reading.quality === "invalid") return "无效";
  if (reading.value === null) return "未接收";
  // 原始Modbus回包没有采集时间；接收时间同样用于断线后的过期显示。
  const at = reading.observedAt || reading.receivedAt;
  if (
    reading.quality === "stale" ||
    (at &&
      staleAfterSeconds != null &&
      now - Date.parse(at) > staleAfterSeconds * 1000)
  )
    return "过期";
  if (reading.evidence?.status === "missing") return "本轮缺测";
  if (reading.evidence?.status === "degraded") return "单路降级";
  return reading.quality === "good" ? "已接收" : "未知";
}
export function canControl(
  user: User | null | undefined,
  capabilities: Capabilities | undefined,
  actuator: Actuator | undefined,
  action: string,
) {
  return (
    !!user?.enabled &&
    ["admin", "operator"].includes(user.role) &&
    capabilities?.controlEnabled === true &&
    !!actuator &&
    (action === "set_mode"
      ? actuator.modeWritable
      : actuator.actions.some((a) => a.id === action && a.enabled))
  );
}
// 受理、下发和实际回读是不同阶段，只有有回读时间的 succeeded 才能显示已执行。
export function commandLabel(
  command: CommandReceipt | undefined,
  expired = false,
) {
  if (!command || expired) return "结果未知";
  if (command.status === "succeeded")
    return command.readbackAt ? "已执行 · 已回读" : "结果未知 · 缺少回读";
  return {
    accepted: "已受理 · 等待执行",
    executing: "执行中 · 等待回读",
    rejected: "执行被拒绝",
    unknown: "结果未知",
  }[command.status];
}
export const statusLabels = {
  accepted: "已受理",
  executing: "执行中",
  succeeded: "已执行",
  rejected: "被拒绝",
  unknown: "结果未知",
};
