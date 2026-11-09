import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ControlDialog, submissionError } from "./CommandFlow";
import {
  api,
  ApiError,
  type Actuator,
  type Capabilities,
  type CommandReceipt,
  type User,
} from "../sdk";
const state = vi.hoisted(() => ({
  user: {
    id: "u",
    username: "u",
    displayName: "operator",
    enabled: true,
    role: "operator",
  } as User | null,
  capabilities: { data: { controlEnabled: true } as Capabilities },
  siteId: "s",
}));
vi.mock("../data/Platform", () => ({ usePlatform: () => state }));
vi.mock("./UI", () => ({
  Modal: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
const actuator: Actuator = {
  id: "fan",
  siteId: "s",
  name: "风扇",
  kind: "switch",
  state: false,
  mode: "manual",
  version: "v1",
  actions: [{ id: "start", label: "开启", enabled: true }],
  modeWritable: false,
};
afterEach(() => {
  vi.restoreAllMocks();
  state.user = {
    id: "u",
    username: "u",
    displayName: "operator",
    enabled: true,
    role: "operator",
  };
});
describe("控制确认组件", () => {
  it("打开确认窗不发动作，连续点击只提交一次，保留受理状态", async () => {
    let resolve!: (r: CommandReceipt) => void;
    const send = vi.spyOn(api, "sendCommand").mockImplementation(
      () =>
        new Promise((r) => {
          resolve = r;
        }),
    );
    const submitted = vi.fn();
    const close = vi.fn();
    let tree!: ReactTestRenderer;
    await act(async () => {
      tree = create(
        <ControlDialog
          actuator={actuator}
          intent={{
            actuatorId: "fan",
            action: "start",
            parameters: {},
            reason: "test-only",
          }}
          onClose={close}
          onSubmitted={submitted}
        />,
      );
    });
    expect(send).not.toHaveBeenCalled();
    const confirm = tree.root
      .findAllByType("button")
      .find((button) => button.children.includes("确认提交"))!;
    await act(async () => {
      confirm.props.onClick();
      confirm.props.onClick();
    });
    expect(send).toHaveBeenCalledTimes(1);
    expect(submitted).not.toHaveBeenCalled();
    await act(async () =>
      resolve({
        commandId: "c",
        siteId: "s",
        status: "accepted",
        acceptedAt: "",
        updatedAt: "",
        readbackAt: null,
        result: null,
      }),
    );
    expect(submitted.mock.calls[0][0].receipt.status).toBe("accepted");
    expect(close).toHaveBeenCalledOnce();
    tree.unmount();
  });
  it("只读角色无法从确认窗绕过权限", async () => {
    state.user = { ...state.user!, role: "viewer" };
    const send = vi.spyOn(api, "sendCommand");
    let tree!: ReactTestRenderer;
    await act(async () => {
      tree = create(
        <ControlDialog
          actuator={actuator}
          intent={{
            actuatorId: "fan",
            action: "start",
            parameters: {},
            reason: "",
          }}
          onClose={vi.fn()}
          onSubmitted={vi.fn()}
        />,
      );
    });
    const confirm = tree.root
      .findAllByType("button")
      .find((button) => button.children.includes("确认提交"))!;
    expect(confirm.props.disabled).toBe(true);
    await act(async () => confirm.props.onClick());
    expect(send).not.toHaveBeenCalled();
    tree.unmount();
  });
  it("网络失败结果未知，明确4xx才视为拒绝", () => {
    expect(submissionError(new TypeError("network"), "k").rejected).toBe(false);
    expect(submissionError(new ApiError(403, "forbidden"), "k").rejected).toBe(
      true,
    );
    expect(submissionError(new ApiError(503, "offline"), "k").rejected).toBe(
      false,
    );
  });
});
