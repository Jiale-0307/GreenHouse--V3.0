import type { PlcMonitoring } from "../sdk";
// 实时连接仍在线不代表PLC点位新鲜；每个通道分别检查接收时间。
export function freshMonitoring(
  value: PlcMonitoring | undefined,
  now: number,
  staleAfter = 90,
): PlcMonitoring | undefined {
  if (!value) return undefined;
  const fresh = (at: string | null) =>
    !!at && now - Date.parse(at) <= staleAfter * 1000;
  return {
    ...value,
    mode: {
      ...value.mode,
      state: fresh(value.mode.receivedAt) ? value.mode.state : "unknown",
      writable: false,
    },
    outputs: value.outputs.map((r) => ({
      ...r,
      state: fresh(r.receivedAt) ? r.state : null,
    })),
    faults: value.faults.map((r) => ({
      ...r,
      state: fresh(r.receivedAt) ? r.state : "unknown",
    })),
    meter: {
      ...value.meter,
      status: fresh(value.meter.receivedAt) ? value.meter.status : "unknown",
    },
  };
}
