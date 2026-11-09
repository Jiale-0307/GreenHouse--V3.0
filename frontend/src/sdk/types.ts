export type Nullable<T> = T | null;
export type Role = "admin" | "operator" | "viewer";
export type ConnectionState =
  "connected" | "disconnected" | "stale" | "unknown";
export type CommandStatus =
  "accepted" | "executing" | "succeeded" | "rejected" | "unknown";
export interface User {
  id: string;
  username: string;
  displayName: string;
  role: Role;
  enabled: boolean;
}
export interface Session {
  user: User;
  csrfToken: string;
}
export interface Site {
  id: string;
  name: string;
  status: ConnectionState;
  lastSeenAt: Nullable<string>;
}
export interface MetricDefinition {
  id: string;
  siteId: string;
  name: string;
  group: string;
  source: string;
  unit: Nullable<string>;
  order: number;
  enabled: boolean;
}
export interface MetricReading {
  metricId: string;
  siteId: string;
  value: Nullable<number>;
  quality: "good" | "stale" | "invalid" | "unknown";
  observedAt: Nullable<string>;
  receivedAt: Nullable<string>;
  evidence?: {
    status: "good" | "degraded" | "missing" | "unconfirmed";
    attemptedAt: string;
    sources: {
      address: number;
      raw: Nullable<number>;
      value: Nullable<number>;
      unit: Nullable<string>;
    }[];
  };
}
export interface ActionDefinition {
  id: string;
  label: string;
  enabled: boolean;
}
export interface Actuator {
  id: string;
  siteId: string;
  name: string;
  kind: string;
  state: Nullable<boolean | string | number>;
  mode: Nullable<"manual" | "auto">;
  version: string;
  actions: ActionDefinition[];
  modeWritable: boolean;
}
export interface Camera {
  id: string;
  siteId: string;
  name: string;
  playbackUrl: Nullable<string>;
  protocol: Nullable<"hls" | "mp4">;
  online: Nullable<boolean>;
}
export interface Alarm {
  id: string;
  siteId: string;
  level: "info" | "warning" | "critical";
  title: string;
  status: "open" | "acknowledged" | "closed";
  occurredAt: string;
  detail: Nullable<string>;
  canAcknowledge: boolean;
  source?: Nullable<string>;
  acknowledgedAt?: Nullable<string>;
  recoveredAt?: Nullable<string>;
}
export interface TerminalSession {
  id: string;
  username: string;
  userAgent: string;
  createdAt: string;
  expiresAt: string;
  current: boolean;
}
export type SiteMode = "auto" | "manual" | "stopped" | "invalid" | "unknown";
export interface PlcMonitoring {
  mode: {
    state: SiteMode;
    raw: number[] | null;
    receivedAt: string | null;
    version: string;
    writable: boolean;
    disabledReason: string;
  };
  outputs: {
    id: string;
    name: string;
    address: number;
    state: boolean | null;
    receivedAt: string | null;
  }[];
  faults: {
    id: string;
    name: string;
    address: number;
    state: "fault" | "normal" | "unknown";
    raw: number | null;
    receivedAt: string | null;
    activeAlarmId: string | null;
  }[];
  meter: {
    mappingConfirmed: boolean;
    status: "good" | "unconfirmed" | "unknown";
    rawRegisters: number[] | null;
    values: {
      metricId: string;
      name: string;
      unit: string;
      value: number | null;
    }[];
    receivedAt: string | null;
  };
}
export interface OperationLog {
  id: string;
  siteId: string;
  actor: Nullable<string>;
  action: string;
  target: string;
  status: CommandStatus;
  requestedAt: string;
  result: Nullable<string>;
}
export interface HistoryRange {
  id: string;
  label: string;
  seconds: number;
}
export interface Capabilities {
  controlEnabled: boolean;
  parametersWritable: boolean;
  aiEnabled: boolean;
  alarmAcknowledge: boolean;
  historyRanges: HistoryRange[];
  aggregations: { id: string; label: string }[];
  staleAfterSeconds: Nullable<number>;
  commandTimeoutSeconds: number;
}
export interface Snapshot {
  site: Site;
  metrics: MetricReading[];
  actuators: Actuator[];
  receivedAt: Nullable<string>;
  monitoring?: PlcMonitoring;
  summary: {
    openAlarms: Nullable<number>;
    onlineDevices: Nullable<number>;
    totalDevices: Nullable<number>;
  };
}
export interface Page<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: Nullable<number>;
}
export interface TrendPoint {
  timestamp: string;
  value: Nullable<number>;
}
export interface TrendSeries {
  metricId: string;
  points: TrendPoint[];
}
export interface ControlCommand {
  actuatorId: string;
  action: string;
  parameters: Record<string, unknown>;
  expectedVersion: string;
}
export interface CommandReceipt {
  commandId: string;
  siteId: string;
  status: CommandStatus;
  acceptedAt: string;
  updatedAt: string;
  readbackAt: Nullable<string>;
  result: Nullable<string>;
}
export interface ControlIntent {
  actuatorId: string;
  action: string;
  parameters: Record<string, unknown>;
  reason: string;
}
export interface ChatSession {
  id: string;
  siteId: string;
  title: string;
  createdAt: string;
}
export interface ChatMessage {
  id: string;
  sessionId: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: string;
  controlIntent: Nullable<ControlIntent>;
}
export interface Parameter {
  id: string;
  siteId: string;
  name: string;
  value: Nullable<number>;
  unit: Nullable<string>;
  min: Nullable<number>;
  max: Nullable<number>;
  step: Nullable<number>;
  writable: boolean;
  version: string;
}
export interface ServerEvent {
  type: string;
  siteId: string;
  sequence: number;
  emittedAt: string;
  payload: unknown;
}

// 后端调试版扩展；实体数据入口仅供服务器侧适配器使用，不放浏览器密钥。
export interface SiteConfiguration {
  controlVerified?: boolean | null;
  metrics?: { id: string; unit: string | null; enabled?: boolean }[];
  actuators?: {
    id: string;
    name: string;
    kind: string;
    actions?: ActionDefinition[];
    modeWritable?: boolean;
  }[];
  parameters?: {
    id: string;
    name: string;
    unit?: string | null;
    min?: number | null;
    max?: number | null;
    step?: number | null;
    writable?: boolean;
  }[];
  cameras?: {
    id: string;
    name: string;
    playbackUrl?: string | null;
    protocol?: "hls" | "mp4" | null;
    online?: boolean | null;
  }[];
}
export interface Diagnostics {
  database: { dialect: string; schemaVersion: number };
  mqtt: {
    enabled: boolean;
    connected: boolean;
    acceptedMessages: number;
    rejectedMessages: number;
  };
  modbusMqtt?: {
    enabled: boolean;
    connected: boolean;
    ready: boolean;
    acceptedMessages: number;
    rejectedMessages: number;
    publishedRequests: number;
    timedOutRequests: number;
    failedRequests: number;
    lastResponseAt: string | null;
    lastError: string | null;
    pendingMetricId: string | null;
  };
  ai: { configured: boolean };
  control: { gatewayConfigured: boolean; debugEnabled: boolean };
  serverTime: string;
}
