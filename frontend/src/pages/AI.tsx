import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Plus, Send, Sparkles } from "lucide-react";
import { api, type ChatMessage, type ServerEvent } from "../sdk";
import { usePlatform, useResource, resourceError } from "../data/Platform";
import { EmptyState } from "../components/EmptyState";
import { QueryNotice, Toolbar } from "../components/UI";
export function AI() {
  const p = usePlatform();
  const [selected, setSelected] = useState("");
  const sessions = useResource(["ai-sessions", p.siteId], (signal) =>
    api.chats(p.siteId, { signal }),
  );
  const create = useMutation({
    mutationFn: () => api.createChat(p.siteId),
    onSuccess: (session) => {
      setSelected(session.id);
      sessions.refetch();
    },
  });
  const canChat = !!p.user?.enabled && p.capabilities.data?.aiEnabled === true;
  const sessionId = sessions.data?.some((s) => s.id === selected)
    ? selected
    : sessions.data?.[0]?.id || "";
  return (
    <div className="page">
      <Toolbar title="AI 助手" kicker="INTELLIGENCE / ASSISTANT">
        <span className="toolbar-note">建议先确认，动作有回读</span>
      </Toolbar>
      <div className="ai-layout">
        <aside className="panel ai-sessions">
          <div className="panel-title">
            <h3>工作会话</h3>
            <button
              aria-label="新建会话"
              className="icon-button"
              disabled={!canChat || create.isPending}
              onClick={() => create.mutate()}
            >
              <Plus size={15} />
            </button>
          </div>
          <QueryNotice
            error={sessions.error || create.error}
            loading={sessions.isPending}
          />
          {sessions.data?.length ? (
            sessions.data.map((s) => (
              <button
                key={s.id}
                className={`session-row ${s.id === sessionId ? "active" : ""}`}
                onClick={() => setSelected(s.id)}
              >
                {s.title}
              </button>
            ))
          ) : (
            <EmptyState detail="暂无会话" />
          )}
        </aside>
        <Chat
          key={`${p.siteId}:${sessionId}`}
          sessionId={sessionId}
          canChat={canChat}
        />
      </div>
    </div>
  );
}
function Chat({ sessionId, canChat }: { sessionId: string; canChat: boolean }) {
  const p = usePlatform();
  const cache = useQueryClient();
  const navigate = useNavigate();
  const query = useResource(
    ["messages", p.siteId, sessionId],
    (signal) => api.messages(p.siteId, sessionId, { signal }),
    !!sessionId,
  );
  const [overlay, setOverlay] = useState<Record<string, ChatMessage>>({});
  const [text, setText] = useState("");
  const [context, setContext] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);
  const messages = new Map((query.data || []).map((m) => [m.id, m]));
  Object.values(overlay).forEach((m) => messages.set(m.id, m));
  useEffect(() => {
    const handler = (event: Event) => {
      const e = (event as CustomEvent<ServerEvent>).detail;
      const payload = e.payload as {
        sessionId?: string;
        messageId?: string;
        delta?: string;
        message?: ChatMessage;
        code?: string;
        error?: string;
      };
      if (e.siteId !== p.siteId || payload.sessionId !== sessionId) return;
      if (
        e.type === "ai.delta" &&
        payload.messageId &&
        typeof payload.delta === "string"
      ) {
        const id = payload.messageId;
        const delta = payload.delta;
        setOverlay((previous) => ({
          ...previous,
          [id]: {
            ...(previous[id] || {
              id,
              sessionId,
              role: "assistant",
              content: "",
              createdAt: e.emittedAt,
              controlIntent: null,
            }),
            content: (previous[id]?.content || "") + delta,
          },
        }));
      }
      if (e.type === "ai.completed" && payload.message) {
        const message = payload.message;
        setOverlay((previous) => ({ ...previous, [message.id]: message }));
        setStreaming(false);
        lock.current = false;
        cache.invalidateQueries({
          queryKey: ["messages", p.siteId, sessionId],
        });
      }
      if (e.type === "ai.error") {
        setError(payload.error || "助手处理失败，请重试");
        setStreaming(false);
        lock.current = false;
      }
    };
    window.addEventListener("platform:event", handler);
    return () => window.removeEventListener("platform:event", handler);
  }, [p.siteId, sessionId, cache]);
  useEffect(() => {
    if (!streaming) return;
    const timeout = setTimeout(() => {
      setStreaming(false);
      lock.current = false;
      setError("消息流已中断或等待超时，请刷新会话确认处理结果。");
      query.refetch();
    }, 90000);
    return () => clearTimeout(timeout);
  }, [streaming]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest" });
  }, [overlay]);
  const send = async () => {
    if (
      lock.current ||
      !text.trim() ||
      !sessionId ||
      !canChat ||
      p.connection !== "connected"
    )
      return;
    lock.current = true;
    setStreaming(true);
    setError("");
    try {
      const result = await api.sendMessage(
        p.siteId,
        sessionId,
        text.trim(),
        context,
      );
      setText("");
      setOverlay((previous) => ({
        ...previous,
        [result.userMessage.id]: result.userMessage,
      }));
    } catch (error) {
      setError(resourceError(error as Error));
      lock.current = false;
      setStreaming(false);
    }
  };
  return (
    <section className="panel chat">
      <div className="chat-header">
        <Sparkles size={18} />
        <div>
          <b>农业智能助手</b>
          <small>
            {canChat
              ? p.connection === "connected"
                ? "服务可用"
                : "等待实时连接"
              : "尚未配置或未登录"}
          </small>
        </div>
      </div>
      <QueryNotice
        error={query.error}
        loading={!!sessionId && query.isPending}
      />
      <div className="chat-messages">
        {messages.size ? (
          [...messages.values()]
            .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
            .map((m) => (
              <div className={`message ${m.role}`} key={m.id}>
                <span>
                  {m.role === "user"
                    ? "你"
                    : m.role === "assistant"
                      ? "AI"
                      : "系统"}
                </span>
                <div>
                  <p>{m.content || "暂无内容"}</p>
                  {m.controlIntent && (
                    <div className="intent-card">
                      <b>待确认操作建议</b>
                      <p>{m.controlIntent.reason}</p>
                      <small>
                        {m.controlIntent.actuatorId} · {m.controlIntent.action}
                      </small>
                      <button
                        className="secondary-button"
                        disabled={
                          !p.user ||
                          p.user.role === "viewer" ||
                          !p.capabilities.data?.controlEnabled
                        }
                        onClick={() =>
                          navigate("/control", {
                            state: {
                              siteId: p.siteId,
                              intent: m.controlIntent,
                            },
                          })
                        }
                      >
                        前往设备控制确认
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))
        ) : (
          <div className="assistant-welcome">
            <div className="ai-promo-icon">
              <Sparkles size={25} />
            </div>
            <h3>从数据出发，理解生长</h3>
            <EmptyState detail="模型与会话未接入时不生成回复" />
          </div>
        )}
        {streaming && (
          <p className="muted" role="status">
            正在等待助手…
          </p>
        )}
        <div ref={bottom} />
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <label className="context-toggle">
        <input
          type="checkbox"
          checked={context}
          onChange={(e) => setContext(e.target.checked)}
        />
        附带当前环境数据上下文
      </label>
      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <input
          aria-label="聊天内容"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="描述问题，获取分析与建议…"
          disabled={!sessionId || !canChat}
        />
        <button
          aria-label="发送消息"
          disabled={
            !text.trim() ||
            !sessionId ||
            !canChat ||
            streaming ||
            p.connection !== "connected"
          }
        >
          <Send size={16} />
        </button>
      </form>
      <small className="chat-disclaimer">
        AI 建议需要核实。任何设备动作都必须经过权限检查与二次确认。
      </small>
    </section>
  );
}
