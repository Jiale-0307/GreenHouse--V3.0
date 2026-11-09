import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  RealtimeClient,
  type MetricReading,
  type ServerEvent,
  type Snapshot,
  type Site,
} from "../sdk";
import { metricCatalog } from "./catalog";
import { ApiError } from "../sdk/client";

export function useResource<T>(
  key: readonly unknown[],
  query: (signal: AbortSignal) => Promise<T>,
  enabled = true,
  refetchInterval?: number,
) {
  return useQuery({
    queryKey: key,
    queryFn: ({ signal }) => query(signal),
    retry: false,
    enabled,
    staleTime: 15000,
    refetchInterval,
  });
}
function usePlatformState() {
  const cache = useQueryClient();
  const [siteId, setSiteId] = useState("default-site");
  const [connection, setConnection] = useState<
    "connected" | "disconnected" | "connecting"
  >("disconnected");
  const [authExpired, setAuthExpired] = useState(false);
  const session = useResource(
    ["session"],
    (signal) => api.session({ signal }),
    !authExpired,
    30000,
  );
  const user = authExpired ? null : session.data?.user || null;
  const sites = useResource(
    ["sites"],
    (signal) => api.sites({ signal }),
    !!user,
  );
  const snapshot = useResource(
    ["snapshot", siteId],
    (signal) => api.snapshot(siteId, { signal }),
    !!user,
  );
  const capabilities = useResource(
    ["capabilities", siteId],
    (signal) => api.capabilities(siteId, { signal }),
    !!user,
  );
  const definitions = useResource(
    ["metrics", siteId],
    (signal) => api.metricDefinitions(siteId, { signal }),
    !!user,
  );
  const cameras = useResource(
    ["cameras", siteId],
    (signal) => api.cameras(siteId, { signal }),
    !!user,
  );
  useEffect(() => {
    api.setCsrfToken(authExpired ? null : session.data?.csrfToken || null);
  }, [session.data, authExpired]);
  useEffect(() => {
    const expired = () => {
      api.setCsrfToken(null);
      setAuthExpired(true);
      void cache.cancelQueries({
        predicate: (q) => q.queryKey[0] !== "session",
      });
      cache.removeQueries({ predicate: (q) => q.queryKey[0] !== "session" });
      setRetained({ siteId, readings: [] });
    };
    window.addEventListener("auth:expired", expired);
    return () => window.removeEventListener("auth:expired", expired);
  }, [cache, siteId]);
  useEffect(() => {
    if (sites.data?.length && !sites.data.some((s) => s.id === siteId))
      setSiteId(sites.data[0].id);
  }, [sites.data, siteId]);
  useEffect(() => {
    if (!user) {
      setConnection("disconnected");
      return;
    }
    const configured = import.meta.env.VITE_WS_URL;
    const url =
      configured ||
      `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws`;
    const ws = new RealtimeClient(url);
    let active = true;
    let sequence: number | null = null;
    const refresh = () => {
      cache.invalidateQueries({
        predicate: (q) => q.queryKey.includes(siteId),
      });
    };
    ws.connect(
      siteId,
      (event) => {
        if (!active) return;
        // 乱序事件丢弃，跳号或重连统一拉快照，避免局部更新留下失真的设备状态。
        if (sequence !== null && event.sequence <= sequence) return;
        if (sequence !== null && event.sequence !== sequence + 1) refresh();
        sequence = event.sequence;
        if (event.type === "snapshot.updated") {
          if (snapshotOf(event.payload) && event.payload.site.id === siteId) {
            // 遥测每项都会推完整快照；直接使用推送，避免每次回包重查历史/定义导致请求堆积。
            const data = event.payload;
            void cache.cancelQueries({ queryKey: ["snapshot", siteId] });
            cache.setQueryData(["snapshot", siteId], data);
            cache.setQueryData(["actuators", siteId], data.actuators);
            cache.setQueryData<Site[]>(["sites"], (previous) =>
              previous?.map((site) => (site.id === siteId ? data.site : site)),
            );
          } else refresh();
        }
        if (event.type === "alarm.updated") {
          cache.invalidateQueries({ queryKey: ["alarms", siteId] });
          cache.invalidateQueries({ queryKey: ["snapshot", siteId] });
        }
        if (event.type === "command.updated") {
          cache.invalidateQueries({ queryKey: ["command", siteId] });
          cache.invalidateQueries({ queryKey: ["actuators", siteId] });
          cache.invalidateQueries({ queryKey: ["snapshot", siteId] });
        }
        window.dispatchEvent(
          new CustomEvent<ServerEvent>("platform:event", { detail: event }),
        );
      },
      setConnection,
      () => {
        sequence = null;
        refresh();
      },
    );
    return () => {
      active = false;
      ws.close();
    };
  }, [user?.id, siteId, cache]);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(id);
  }, []);
  // 字段缺失时保留前次值并标为过期，而不是把缺失误当成零。
  const [retained, setRetained] = useState<{
    siteId: string;
    readings: MetricReading[];
  }>({ siteId, readings: [] });
  useEffect(() => {
    if (!user) {
      setRetained({ siteId, readings: [] });
      return;
    }
    if (!snapshot.data) return;
    setRetained((previous) => {
      const incoming = snapshot.data!.metrics;
      const merged = new Map<string, MetricReading>(
        (previous.siteId === siteId ? previous.readings : []).map((r) => [
          r.metricId,
          { ...r, quality: "stale" as const },
        ]),
      );
      incoming.forEach((r) => merged.set(r.metricId, r));
      return { siteId, readings: [...merged.values()] };
    });
  }, [snapshot.data, siteId, user?.id]);
  const readings = user && retained.siteId === siteId ? retained.readings : [];
  const catalog = (
    definitions.data?.length
      ? definitions.data
      : metricCatalog.map((m) => ({ ...m, siteId }))
  )
    .filter((m) => m.enabled)
    .sort((a, b) => a.order - b.order);
  const refresh = () => cache.invalidateQueries();
  return {
    siteId,
    setSiteId,
    sites,
    snapshot,
    capabilities,
    catalog,
    readings,
    cameras,
    connection,
    session,
    user,
    now,
    authExpired,
    setAuthExpired,
    refresh,
  };
}
const Context = createContext<ReturnType<typeof usePlatformState> | null>(null);
export function PlatformProvider({ children }: { children: ReactNode }) {
  const state = usePlatformState();
  return <Context.Provider value={state}>{children}</Context.Provider>;
}
export function usePlatform() {
  const value = useContext(Context);
  if (!value) throw new Error("PlatformProvider missing");
  return value;
}
export function resourceError(error: Error | null) {
  if (!error) return "";
  if (error instanceof ApiError)
    return error.status === 401
      ? "请登录后访问此资源"
      : error.status === 403
        ? "当前账号没有访问权限"
        : `${error.message}（${error.status}）`;
  return error.name === "AbortError" || error.name === "TimeoutError"
    ? "请求超时，请重试"
    : "服务未连接，等待后端数据";
}
export function snapshotOf(value: unknown): value is Snapshot {
  return (
    typeof value === "object" &&
    value !== null &&
    Array.isArray((value as Snapshot).metrics) &&
    Array.isArray((value as Snapshot).actuators) &&
    typeof (value as Snapshot).site?.id === "string"
  );
}
