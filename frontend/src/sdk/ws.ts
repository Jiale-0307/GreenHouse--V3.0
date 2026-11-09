import type { ServerEvent } from "./types";
export type RealtimeState = "connected" | "disconnected" | "connecting";
export class RealtimeClient {
  private socket: WebSocket | null = null;
  private retry = 0;
  private closed = true;
  private timer: ReturnType<typeof setTimeout> | undefined;
  constructor(private readonly url: string) {}
  connect(
    siteId: string,
    onEvent: (event: ServerEvent) => void,
    onState: (state: RealtimeState) => void,
    onReconnect: () => void,
  ) {
    this.closed = false;
    let connectedBefore = false;
    const open = () => {
      if (this.closed) return;
      onState("connecting");
      try {
        this.socket = new WebSocket(this.url);
      } catch {
        schedule();
        return;
      }
      this.socket.onopen = () => {
        this.retry = 0;
        onState("connected");
        this.socket?.send(
          JSON.stringify({
            type: "subscribe",
            siteId,
            topics: [
              "snapshot.updated",
              "alarm.updated",
              "command.updated",
              "ai.delta",
              "ai.completed",
              "ai.error",
            ],
          }),
        );
        if (connectedBefore) onReconnect();
        connectedBefore = true;
      };
      this.socket.onmessage = (e) => {
        try {
          const event: ServerEvent = JSON.parse(e.data);
          if (
            event.siteId === siteId &&
            typeof event.type === "string" &&
            Number.isFinite(event.sequence) &&
            event.payload !== null &&
            typeof event.payload === "object"
          )
            onEvent(event);
        } catch {
          /* 非 JSON / 非本站事件不能污染实时状态。 */
        }
      };
      this.socket.onclose = (event) => {
        if (event.code === 4401) {
          this.closed = true;
          onState("disconnected");
          window.dispatchEvent(new Event("auth:expired"));
        } else schedule();
      };
      this.socket.onerror = () => this.socket?.close();
    };
    const schedule = () => {
      onState("disconnected");
      if (!this.closed)
        this.timer = setTimeout(
          open,
          Math.min(1000 * 2 ** this.retry++, 15000),
        );
    };
    open();
  }
  close() {
    this.closed = true;
    clearTimeout(this.timer);
    if (this.socket) {
      this.socket.onclose = null;
      this.socket.close();
    }
  }
}
