import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { api, RealtimeClient, type ServerEvent, type Snapshot } from "../sdk";
import { PlatformProvider, usePlatform } from "./Platform";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("一轮18条实时推送直接更新读数，不重复拉取API与历史；断线重连重新同步", async () => {
  const events = new EventTarget();
  vi.stubGlobal("window", events);
  vi.stubGlobal("location", { protocol: "http:", host: "local" });
  let onEvent!: (event: ServerEvent) => void;
  let reconnect!: () => void;
  vi.spyOn(RealtimeClient.prototype, "connect").mockImplementation(
    (_site, event, state, again) => {
      onEvent = event;
      reconnect = again;
      state("connected");
    },
  );
  vi.spyOn(RealtimeClient.prototype, "close").mockImplementation(() => {});
  const site = {
    id: "default-site",
    name: "棚",
    status: "unknown" as const,
    lastSeenAt: null,
  };
  const empty: Snapshot = {
    site,
    metrics: [],
    actuators: [],
    receivedAt: null,
    summary: { openAlarms: 0, onlineDevices: null, totalDevices: null },
  };
  vi.spyOn(api, "session").mockResolvedValue({
    user: {
      id: "u",
      username: "admin",
      displayName: "admin",
      role: "admin",
      enabled: true,
    },
    csrfToken: "test",
  });
  vi.spyOn(api, "sites").mockResolvedValue([site]);
  const snapshot = vi.spyOn(api, "snapshot").mockResolvedValue(empty);
  const definitions = vi.spyOn(api, "metricDefinitions").mockResolvedValue([]);
  vi.spyOn(api, "capabilities").mockResolvedValue({
    controlEnabled: false,
    parametersWritable: false,
    aiEnabled: false,
    alarmAcknowledge: true,
    historyRanges: [],
    aggregations: [],
    staleAfterSeconds: 90,
    commandTimeoutSeconds: 30,
  });
  vi.spyOn(api, "cameras").mockResolvedValue([]);
  const history = vi.spyOn(api, "trend");
  const cache = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  let latest!: ReturnType<typeof usePlatform>;
  function Probe() {
    latest = usePlatform();
    return <span>{latest.readings[0]?.value}</span>;
  }
  let tree!: ReactTestRenderer;
  await act(async () => {
    tree = create(
      <QueryClientProvider client={cache}>
        <PlatformProvider>
          <Probe />
        </PlatformProvider>
      </QueryClientProvider>,
    );
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 10));
  });
  const before = snapshot.mock.calls.length;
  await act(async () => {
    for (let index = 1; index <= 18; index++)
      onEvent({
        type: "snapshot.updated",
        siteId: "default-site",
        sequence: index,
        emittedAt: "2026-11-04T23:00:00+08:00",
        payload: {
          ...empty,
          metrics: [
            {
              metricId: "soil-temp",
              siteId: "default-site",
              value: index,
              quality: "good",
              observedAt: null,
              receivedAt: "2026-11-04T23:00:00+08:00",
            },
          ],
        },
      });
    await new Promise((resolve) => setTimeout(resolve, 10));
  });
  expect(latest.readings[0].value).toBe(18);
  expect(snapshot).toHaveBeenCalledTimes(before);
  expect(definitions).toHaveBeenCalledTimes(1);
  expect(history).not.toHaveBeenCalled();
  await act(async () => {
    reconnect();
    await new Promise((resolve) => setTimeout(resolve, 10));
  });
  expect(snapshot.mock.calls.length).toBeGreaterThan(before);
  await act(async () => {
    events.dispatchEvent(new Event("auth:expired"));
    await new Promise((resolve) => setTimeout(resolve, 10));
  });
  expect(latest.user).toBeNull();
  expect(latest.readings).toEqual([]);
  expect(cache.getQueryData(["snapshot", "default-site"])).toBeUndefined();
  expect(RealtimeClient.prototype.close).toHaveBeenCalled();
  await act(async () => tree.unmount());
  cache.clear();
});

it("未建立会话时不加载业务数据或连接WebSocket", async () => {
  vi.stubGlobal("window", new EventTarget());
  vi.stubGlobal("location", { protocol: "http:", host: "local" });
  let resolveSession!: (value: Awaited<ReturnType<typeof api.session>>) => void;
  vi.spyOn(api, "session").mockImplementation(
    () =>
      new Promise((resolve) => {
        resolveSession = resolve;
      }),
  );
  const sites = vi.spyOn(api, "sites");
  const snapshot = vi.spyOn(api, "snapshot");
  const connect = vi.spyOn(RealtimeClient.prototype, "connect");
  const cache = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  let tree!: ReactTestRenderer;
  await act(async () => {
    tree = create(
      <QueryClientProvider client={cache}>
        <PlatformProvider>
          <span>等待身份</span>
        </PlatformProvider>
      </QueryClientProvider>,
    );
  });
  expect(resolveSession).toBeDefined();
  expect(sites).not.toHaveBeenCalled();
  expect(snapshot).not.toHaveBeenCalled();
  expect(connect).not.toHaveBeenCalled();
  await act(async () => tree.unmount());
  cache.clear();
});
