import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "./client";
const ok = (data: unknown) =>
  new Response(JSON.stringify(data), { status: 200 });
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
describe("SDK 请求契约", () => {
  it("默认 fetch 保留浏览器全局接收者，避免页面请求 Illegal invocation", async () => {
    // 注入的普通 mock 不限制 this；这里模拟浏览器原生 fetch 的接收者约束。
    const nativeLikeFetch = vi.fn(function (this: unknown) {
      if (this !== globalThis) throw new TypeError("Illegal invocation");
      return Promise.resolve(ok({ user: { username: "admin" } }));
    });
    vi.stubGlobal("fetch", nativeLikeFetch);
    const api = new ApiClient("/api/v1");
    await expect(api.session()).resolves.toMatchObject({
      user: { username: "admin" },
    });
    expect(nativeLikeFetch).toHaveBeenCalledTimes(1);
  });
  it("使用 Cookie 和 CSRF，写请求只发一次并保留幂等键", async () => {
    const fetcher = vi.fn().mockResolvedValue(ok({ commandId: "c" }));
    const api = new ApiClient("/api/v1", fetcher);
    api.setCsrfToken("test-csrf");
    await api.sendCommand(
      "s",
      {
        actuatorId: "a",
        action: "start",
        parameters: {},
        expectedVersion: "v1",
      },
      "test-request",
    );
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [, options] = fetcher.mock.calls[0];
    expect(options.credentials).toBe("include");
    expect(options.headers.get("Idempotency-Key")).toBe("test-request");
    expect(options.headers.get("X-CSRF-Token")).toBe("test-csrf");
  });
  it("后端403以结构化错误返回，不重试", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: "FORBIDDEN", message: "未授权" }), {
        status: 403,
      }),
    );
    const api = new ApiClient("/api", fetcher);
    await expect(
      api.sendCommand(
        "s",
        {
          actuatorId: "a",
          action: "start",
          parameters: {},
          expectedVersion: "v",
        },
        "k",
      ),
    ).rejects.toMatchObject({ status: 403, code: "FORBIDDEN" });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("查询取消传播到 fetch", async () => {
    const fetcher = vi.fn(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () =>
            reject(new DOMException("cancelled", "AbortError")),
          );
        }),
    );
    const api = new ApiClient("/api", fetcher as typeof fetch);
    const cancel = new AbortController();
    const request = api.snapshot("s", { signal: cancel.signal });
    cancel.abort();
    await expect(request).rejects.toMatchObject({ name: "AbortError" });
  });
  it("请求超时不自动重发写操作", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () =>
            reject(init.signal?.reason),
          );
        }),
    );
    const api = new ApiClient("/api", fetcher as typeof fetch);
    const promise = api.sendCommand(
      "s",
      {
        actuatorId: "a",
        action: "start",
        parameters: {},
        expectedVersion: "v",
      },
      "k",
    );
    const expectation = expect(promise).rejects.toMatchObject({
      name: "TimeoutError",
    });
    await vi.advanceTimersByTimeAsync(12001);
    await expectation;
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("401保留错误语义", async () => {
    const api = new ApiClient(
      "/api",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ message: "过期" }), { status: 401 }),
        ),
    );
    await expect(api.session()).rejects.toBeInstanceOf(ApiError);
  });
});
