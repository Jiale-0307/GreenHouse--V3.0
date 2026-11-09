import { afterEach, describe, expect, it, vi } from "vitest";
import { RealtimeClient } from "./ws";
class Socket {
  static instances: Socket[] = [];
  onopen?: () => void;
  onmessage?: (e: { data: string }) => void;
  onclose?: (event: { code: number }) => void;
  onerror?: () => void;
  send = vi.fn();
  constructor(public url: string) {
    Socket.instances.push(this);
  }
  close() {
    this.onclose?.({ code: 1000 });
  }
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  Socket.instances = [];
});
describe("实时连接", () => {
  it("订阅本站、忽略其他站，断线重连后刷新且关闭时清理定时器", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", Socket);
    const onEvent = vi.fn();
    const onReconnect = vi.fn();
    const state = vi.fn();
    const client = new RealtimeClient("ws://local/ws");
    client.connect("s", onEvent, state, onReconnect);
    const first = Socket.instances[0];
    first.onopen?.();
    expect(JSON.parse(first.send.mock.calls[0][0]).siteId).toBe("s");
    first.onmessage?.({
      data: JSON.stringify({
        type: "snapshot.updated",
        siteId: "other",
        sequence: 1,
        payload: {},
        emittedAt: "2026-11-02T00:00:00Z",
      }),
    });
    expect(onEvent).not.toHaveBeenCalled();
    first.onmessage?.({
      data: JSON.stringify({
        type: "snapshot.updated",
        siteId: "s",
        sequence: 1,
        payload: {},
        emittedAt: "2026-11-02T00:00:00Z",
      }),
    });
    expect(onEvent).toHaveBeenCalledOnce();
    first.close();
    await vi.advanceTimersByTimeAsync(1001);
    const second = Socket.instances[1];
    second.onopen?.();
    expect(onReconnect).toHaveBeenCalledOnce();
    client.close();
    await vi.advanceTimersByTimeAsync(20000);
    expect(Socket.instances).toHaveLength(2);
  });
});

it("会话失效立即清理身份并停止重连", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", Socket);
  const events = new EventTarget();
  vi.stubGlobal("window", events);
  const expired = vi.fn();
  events.addEventListener("auth:expired", expired);
  const client = new RealtimeClient("ws://local/ws");
  client.connect("s", vi.fn(), vi.fn(), vi.fn());
  Socket.instances[0].onclose?.({ code: 4401 });
  await vi.advanceTimersByTimeAsync(20000);
  expect(expired).toHaveBeenCalledOnce();
  expect(Socket.instances).toHaveLength(1);
  client.close();
});
