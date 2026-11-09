import { describe, expect, it } from "vitest";
import {
  canControl,
  commandLabel,
  displayDate,
  displayValue,
  displayMetricValue,
  readingStatus,
} from "./format";
import { metricCatalog } from "../data/catalog";
import type {
  Actuator,
  Capabilities,
  CommandReceipt,
  MetricReading,
  User,
} from "../sdk";
const actuator: Actuator = {
  id: "fan",
  siteId: "s",
  name: "风扇",
  kind: "switch",
  state: false,
  mode: "manual",
  version: "1",
  actions: [{ id: "start", label: "开启", enabled: true }],
  modeWritable: true,
};
const user: User = {
  id: "u",
  username: "u",
  displayName: "操作员",
  enabled: true,
  role: "operator",
};
const capabilities = { controlEnabled: true } as Capabilities;
describe("事实值与来源", () => {
  it("区分未收到、合法零和 false", () => {
    expect(displayValue(undefined)).toBe("—");
    expect(displayValue(null)).toBe("—");
    expect(displayValue(NaN)).toBe("—");
    expect(displayValue(0)).toBe("0");
    expect(displayValue(false)).toBe("false");
    expect(displayMetricValue(23.399999618530273)).toBe("23.4");
    expect(displayMetricValue(0)).toBe("0");
    expect(displayMetricValue(0.00000001)).toBe("0.00000001");
  });
  it("保留原20项与新增紫外线指数，包括两组棚内温湿度", () => {
    expect(metricCatalog).toHaveLength(21);
    expect(new Set(metricCatalog.map((m) => m.id)).size).toBe(21);
    expect(metricCatalog.filter((m) => m.name === "空气温度")).toHaveLength(2);
    expect(metricCatalog.every((m) => m.unit === null)).toBe(true);
  });
  it("时间明确使用上海时区", () => {
    expect(displayDate("2026-11-02T00:00:00Z")).toContain("08:00:00");
    expect(displayDate("bad")).toBe("—");
  });
  it("过期保留值但标识过期", () => {
    const reading: MetricReading = {
      metricId: "m",
      siteId: "s",
      value: 0,
      quality: "good",
      observedAt: "2026-11-02T00:00:00Z",
      receivedAt: null,
    };
    expect(readingStatus(reading, 10, Date.parse("2026-11-02T00:01:00Z"))).toBe(
      "过期",
    );
    expect(displayValue(reading.value)).toBe("0");
  });
  it("Modbus没有采集时间时按接收时间显示过期，非法读数显式标记", () => {
    const reading: MetricReading = {
      metricId: "soil-temp",
      siteId: "s",
      value: 23.4,
      quality: "good",
      observedAt: null,
      receivedAt: "2026-11-04T00:00:00Z",
    };
    expect(readingStatus(reading, 90, Date.parse("2026-11-04T00:02:00Z"))).toBe(
      "过期",
    );
    expect(
      readingStatus({ ...reading, value: null, quality: "invalid" }, 90),
    ).toBe("无效");
  });
});
describe("控制边界与执行状态", () => {
  it("未登录、只读、禁用账号、能力未确认均不能写入", () => {
    expect(canControl(null, capabilities, actuator, "start")).toBe(false);
    expect(
      canControl({ ...user, role: "viewer" }, capabilities, actuator, "start"),
    ).toBe(false);
    expect(
      canControl({ ...user, enabled: false }, capabilities, actuator, "start"),
    ).toBe(false);
    expect(canControl(user, undefined, actuator, "start")).toBe(false);
    expect(canControl(user, capabilities, actuator, "invented")).toBe(false);
    expect(canControl(user, capabilities, actuator, "start")).toBe(true);
  });
  it("受理不是执行、成功必须有回读、超时结果未知", () => {
    const receipt: CommandReceipt = {
      commandId: "c",
      siteId: "s",
      status: "accepted",
      acceptedAt: "",
      updatedAt: "",
      readbackAt: null,
      result: null,
    };
    expect(commandLabel(receipt)).toContain("已受理");
    expect(commandLabel({ ...receipt, status: "succeeded" })).toContain(
      "缺少回读",
    );
    expect(
      commandLabel({
        ...receipt,
        status: "succeeded",
        readbackAt: "2026-11-02T00:00:00Z",
      }),
    ).toBe("已执行 · 已回读");
    expect(commandLabel(receipt, true)).toBe("结果未知");
    expect(commandLabel({ ...receipt, status: "rejected" })).toBe("执行被拒绝");
  });
});
