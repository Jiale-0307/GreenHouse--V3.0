import type {
  Alarm,
  Camera,
  Capabilities,
  ChatMessage,
  ChatSession,
  CommandReceipt,
  ControlCommand,
  MetricDefinition,
  OperationLog,
  Page,
  Parameter,
  Session,
  Site,
  Snapshot,
  TrendSeries,
  User,
  Role,
  SiteConfiguration,
  Diagnostics,
  TerminalSession,
  PlcMonitoring,
  SiteMode,
} from "./types";
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code = "REQUEST_FAILED",
    public details?: unknown,
  ) {
    super(message);
  }
}
export type RequestOptions = { signal?: AbortSignal };
export class ApiClient {
  private csrfToken: string | null = null;
  constructor(
    private readonly baseUrl = import.meta.env.VITE_API_BASE_URL || "/api/v1",
    // 浏览器原生 fetch 需绑定全局对象，不能以 ApiClient 作为 this 调用。
    private readonly fetcher: typeof fetch = globalThis.fetch.bind(globalThis),
  ) {}
  setCsrfToken(token: string | null) {
    this.csrfToken = token;
  }
  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const timeout = new AbortController();
    const abort = () => timeout.abort(init.signal?.reason);
    init.signal?.addEventListener("abort", abort, { once: true });
    if (init.signal?.aborted) abort();
    const timer = setTimeout(
      () =>
        timeout.abort(
          new DOMException("请求超时，写入结果可能未知", "TimeoutError"),
        ),
      12000,
    );
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body) headers.set("Content-Type", "application/json");
    if (init.method && init.method !== "GET" && this.csrfToken)
      headers.set("X-CSRF-Token", this.csrfToken);
    try {
      const response = await this.fetcher(
        `${this.baseUrl.replace(/\/$/, "")}${path}`,
        {
          ...init,
          headers,
          credentials: "include",
          cache: "no-store",
          signal: timeout.signal,
        },
      );
      if (response.status === 401 && typeof window !== "undefined")
        window.dispatchEvent(new Event("auth:expired"));
      if (response.status === 204) return undefined as T;
      const body = await response.json().catch(() => null);
      if (!response.ok)
        throw new ApiError(
          response.status,
          body?.message || "请求失败",
          body?.code,
          body?.details,
        );
      return body as T;
    } finally {
      clearTimeout(timer);
      init.signal?.removeEventListener("abort", abort);
    }
  }
  private site(id: string) {
    return `/sites/${encodeURIComponent(id)}`;
  }
  session(o: RequestOptions = {}) {
    return this.request<Session>("/auth/session", o);
  }
  login(username: string, password: string) {
    return this.request<Session>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  }
  logout() {
    return this.request<void>("/auth/logout", { method: "POST" });
  }
  terminalSessions(o: RequestOptions = {}) {
    return this.request<TerminalSession[]>("/auth/sessions", o);
  }
  revokeSession(id: string) {
    return this.request<void>(`/auth/sessions/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
  }
  monitoring(id: string, o: RequestOptions = {}) {
    return this.request<PlcMonitoring>(`${this.site(id)}/monitoring`, o);
  }
  setSiteMode(
    id: string,
    mode: SiteMode,
    expectedVersion: string,
    key: string,
  ) {
    return this.request<CommandReceipt>(`${this.site(id)}/mode`, {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ mode, expectedVersion }),
    });
  }
  sites(o: RequestOptions = {}) {
    return this.request<Site[]>("/sites", o);
  }
  snapshot(id: string, o: RequestOptions = {}) {
    return this.request<Snapshot>(`${this.site(id)}/snapshot`, o);
  }
  metricDefinitions(id: string, o: RequestOptions = {}) {
    return this.request<MetricDefinition[]>(`${this.site(id)}/metrics`, o);
  }
  capabilities(id: string, o: RequestOptions = {}) {
    return this.request<Capabilities>(`${this.site(id)}/capabilities`, o);
  }
  trend(
    id: string,
    metricIds: string[],
    from: string,
    to: string,
    aggregation: string,
    o: RequestOptions = {},
  ) {
    const q = new URLSearchParams({
      metricIds: metricIds.join(","),
      from,
      to,
      aggregation,
    });
    return this.request<TrendSeries[]>(`${this.site(id)}/trends?${q}`, o);
  }
  actuators(id: string, o: RequestOptions = {}) {
    return this.request<Snapshot["actuators"]>(`${this.site(id)}/actuators`, o);
  }
  cameras(id: string, o: RequestOptions = {}) {
    return this.request<Camera[]>(`${this.site(id)}/cameras`, o);
  }
  alarms(id: string, filters: Record<string, string>, o: RequestOptions = {}) {
    return this.request<Page<Alarm>>(
      `${this.site(id)}/alarms?${new URLSearchParams(filters)}`,
      o,
    );
  }
  acknowledge(id: string, alarmId: string) {
    return this.request<Alarm>(
      `${this.site(id)}/alarms/${encodeURIComponent(alarmId)}/acknowledge`,
      { method: "POST" },
    );
  }
  logs(id: string, filters: Record<string, string>, o: RequestOptions = {}) {
    return this.request<Page<OperationLog>>(
      `${this.site(id)}/logs?${new URLSearchParams(filters)}`,
      o,
    );
  }
  // 写请求不自动重试；幂等键使用户重查同一请求时不会重复驱动设备。
  sendCommand(siteId: string, command: ControlCommand, idempotencyKey: string) {
    return this.request<CommandReceipt>(`${this.site(siteId)}/commands`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(command),
    });
  }
  command(siteId: string, commandId: string, o: RequestOptions = {}) {
    return this.request<CommandReceipt>(
      `${this.site(siteId)}/commands/${encodeURIComponent(commandId)}`,
      o,
    );
  }
  parameters(id: string, o: RequestOptions = {}) {
    return this.request<Parameter[]>(`${this.site(id)}/parameters`, o);
  }
  updateParameter(
    siteId: string,
    parameter: Parameter,
    value: number,
    idempotencyKey: string,
  ) {
    return this.request<CommandReceipt>(
      `${this.site(siteId)}/parameters/${encodeURIComponent(parameter.id)}`,
      {
        method: "PATCH",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({ value, expectedVersion: parameter.version }),
      },
    );
  }
  users(o: RequestOptions = {}) {
    return this.request<User[]>("/users", o);
  }
  createUser(username: string, password: string, role: Role) {
    return this.request<User>("/users", {
      method: "POST",
      body: JSON.stringify({ username, password, role }),
    });
  }
  updateUser(id: string, role: Role, enabled: boolean) {
    return this.request<User>(`/users/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify({ role, enabled }),
    });
  }
  diagnostics(o: RequestOptions = {}) {
    return this.request<Diagnostics>("/diagnostics", o);
  }
  configureSite(id: string, configuration: SiteConfiguration) {
    return this.request<{ updated: boolean }>(
      `${this.site(id)}/configuration`,
      {
        method: "PUT",
        body: JSON.stringify(configuration),
      },
    );
  }
  chats(id: string, o: RequestOptions = {}) {
    return this.request<ChatSession[]>(`${this.site(id)}/ai/sessions`, o);
  }
  createChat(id: string) {
    return this.request<ChatSession>(`${this.site(id)}/ai/sessions`, {
      method: "POST",
    });
  }
  messages(id: string, sessionId: string, o: RequestOptions = {}) {
    return this.request<ChatMessage[]>(
      `${this.site(id)}/ai/sessions/${encodeURIComponent(sessionId)}/messages`,
      o,
    );
  }
  sendMessage(
    id: string,
    sessionId: string,
    content: string,
    includeContext: boolean,
  ) {
    return this.request<{ messageId: string; userMessage: ChatMessage }>(
      `${this.site(id)}/ai/sessions/${encodeURIComponent(sessionId)}/messages`,
      { method: "POST", body: JSON.stringify({ content, includeContext }) },
    );
  }
}
export const api = new ApiClient();
