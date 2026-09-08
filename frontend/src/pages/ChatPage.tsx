import { useCallback, useEffect, useRef, useState } from "react";
import { Menu, PanelLeftOpen } from "lucide-react";
import { api, apiResponse, randomId, setCsrfToken } from "../api";
import { Composer } from "../components/Composer";
import { MessageList } from "../components/MessageList";
import { Sidebar } from "../components/Sidebar";
import type { Artifact, Attachment, ChatMessage, Identity, LocalDirectory, Provider, RunMetrics, Session, Skill, ToolStep } from "../types";

type Props = { identity: Identity; onLogout: () => void };
type ActiveRun = { id: string; controller: AbortController };

export function ChatPage({ identity, onLogout }: Props) {
  const storageKey = `czon_agent_session_id:${identity.username}`;
  const [sessionId, setSessionId] = useState(() => sessionStorage.getItem(storageKey) || randomId());
  const [sessions, setSessions] = useState<Session[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [provider, setProvider] = useState(() => localStorage.getItem("czon_agent_provider") || "");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [directory, setDirectory] = useState<LocalDirectory | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth > 760);
  const [notice, setNotice] = useState("");
  const activeRun = useRef<ActiveRun | null>(null);
  const [running, setRunning] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (!running) return;
    const startedAt = Date.now();
    setElapsedSeconds(0);
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  const rememberSession = useCallback((id: string) => {
    setSessionId(id); sessionStorage.setItem(storageKey, id);
  }, [storageKey]);

  const loadSessions = useCallback(async (restore = false) => {
    const data = await api<{ sessions: Session[] }>("/api/sessions", { cache: "no-store" });
    setSessions(data.sessions);
    if (!restore) return;
    const saved = sessionStorage.getItem(storageKey);
    const current = data.sessions.find((item) => item.id === saved);
    if (current) {
      const detail = await api<{ title: string; messages: Array<{ role: "user" | "assistant"; content: string; artifacts?: Artifact[]; duration_ms?: number; input_tokens?: number; output_tokens?: number }> }>(`/api/sessions/${current.id}`, { cache: "no-store" });
      rememberSession(current.id);
      setMessages(detail.messages.map((message, index) => ({ id: `history-${index}`, role: message.role, content: message.content, artifacts: message.artifacts, metrics: message.role === "assistant" ? { duration_ms: message.duration_ms, input_tokens: message.input_tokens, output_tokens: message.output_tokens } : undefined, state: "done" })));
    } else {
      const id = randomId(); rememberSession(id); setMessages([]);
    }
  }, [rememberSession, storageKey]);

  useEffect(() => {
    void Promise.all([
      api<Provider[]>("/api/providers", { cache: "no-store" }).then((items) => {
        setProviders(items);
        const available = items.filter((item) => item.configured);
        const selected = available.some((item) => item.name === provider) ? provider : available[0]?.name || "";
        setProvider(selected);
      }),
      api<{ skills: Skill[] }>("/api/skills", { cache: "no-store" }).then((data) => setSkills(data.skills)),
      loadSessions(true),
    ]).catch((error) => setNotice(error instanceof Error ? error.message : "加载失败"));
  }, []); // Identity is fixed for the mounted page.

  async function openSession(id: string) {
    if (running) return setNotice("请先停止当前任务");
    try {
      const detail = await api<{ title: string; messages: Array<{ role: "user" | "assistant"; content: string; artifacts?: Artifact[]; duration_ms?: number; input_tokens?: number; output_tokens?: number }> }>(`/api/sessions/${id}`, { cache: "no-store" });
      rememberSession(id); setAttachments([]); setDirectory(null);
      setMessages(detail.messages.map((message, index) => ({ id: `history-${index}`, role: message.role, content: message.content, artifacts: message.artifacts, metrics: message.role === "assistant" ? { duration_ms: message.duration_ms, input_tokens: message.input_tokens, output_tokens: message.output_tokens } : undefined, state: "done" })));
      if (window.innerWidth <= 760) setSidebarOpen(false);
    } catch (error) { setNotice(error instanceof Error ? error.message : "会话加载失败"); }
  }

  async function newChat() {
    if (activeRun.current) await stopRun();
    rememberSession(randomId()); setMessages([]); setAttachments([]); setDirectory(null);
    if (window.innerWidth <= 760) setSidebarOpen(false);
  }

  async function deleteSession(id: string) {
    if (running || !window.confirm("确定删除这个会话吗？")) return;
    try {
      await api(`/api/sessions/${id}`, { method: "DELETE" });
      if (id === sessionId) await newChat();
      await loadSessions();
    } catch (error) { setNotice(error instanceof Error ? error.message : "删除失败"); }
  }

  async function logout() {
    try { await api("/api/auth/logout", { method: "POST" }); } catch { /* Session may already be expired. */ }
    setCsrfToken(""); onLogout();
  }

  function updateAssistant(id: string, updater: (message: ChatMessage) => ChatMessage) {
    setMessages((items) => items.map((item) => item.id === id ? updater(item) : item));
  }

  function mergeStep(steps: ToolStep[], incoming: ToolStep) {
    const index = incoming.id ? steps.findIndex((item) => item.id === incoming.id) : -1;
    if (index < 0) return [...steps, incoming];
    const next = [...steps]; next[index] = { ...incoming, progress: incoming.progress || steps[index].progress }; return next;
  }

  async function sendMessage(text: string, skill: Skill | null) {
    const messageId = `assistant-${Date.now()}`;
    const files = [...attachments];
    const selectedDirectory = directory;
    setAttachments([]); setDirectory(null);
    setMessages((items) => [...items,
      { id: `user-${Date.now()}`, role: "user", content: text, attachments: files, directory: selectedDirectory || undefined, state: "done" },
      { id: messageId, role: "assistant", content: "", steps: [], state: "running" },
    ]);
    const run = { id: randomId(), controller: new AbortController() };
    activeRun.current = run; setRunning(true);
    try {
      const response = await apiResponse("/api/chat/stream", {
        method: "POST",
        body: JSON.stringify({ text, attachments: files, directory: selectedDirectory, provider, session_id: sessionId, run_id: run.id, skill: skill?.name || null }),
        signal: run.controller.signal,
      });
      if (!response.ok || !response.body) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `请求失败 (${response.status})`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let pendingText = "";
      let finished = false;
      let frame = 0;
      const flushText = () => {
        if (!pendingText) return;
        const delta = pendingText; pendingText = "";
        updateAssistant(messageId, (message) => ({ ...message, content: message.content + delta }));
      };
      const scheduleText = () => {
        if (frame) return;
        frame = requestAnimationFrame(() => { frame = 0; flushText(); });
      };
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n"); buffer = chunks.pop() || "";
        for (const chunk of chunks) {
          const parsed = parseEvent(chunk); if (!parsed) continue;
          if (parsed.name === "assistant_delta") { pendingText += String(parsed.data.text || ""); scheduleText(); continue; }
          if (parsed.name === "keepalive") {
            const seconds = Number(parsed.data.elapsed_seconds);
            if (Number.isFinite(seconds)) setElapsedSeconds(Math.max(0, Math.floor(seconds)));
            continue;
          }
          flushText();
          if (["tool_start", "tool_progress", "tool_result", "confirmation_required"].includes(parsed.name)) {
            const step = parsed.data as ToolStep;
            if (parsed.name === "tool_start") {
              updateAssistant(messageId, (message) => ({ ...message, steps: mergeStep(message.steps || [], step) }));
            } else if (parsed.name === "tool_progress") {
              updateAssistant(messageId, (message) => {
                const steps = [...(message.steps || [])];
                const index = steps.findIndex((item) => item.id === step.id);
                if (index >= 0) steps[index] = { ...steps[index], progress: `${step.text || ""}${steps[index].progress || ""}`.slice(0, 30000) } as ToolStep;
                else steps.push({ ...step, progress: String(step.text || "") });
                return { ...message, steps };
              });
            } else updateAssistant(messageId, (message) => ({ ...message, steps: mergeStep(message.steps || [], step) }));
          } else if (parsed.name === "agent_done") {
            finished = true;
            const finalReply = String(parsed.data.reply || "");
            const artifacts = Array.isArray(parsed.data.artifacts) ? parsed.data.artifacts as Artifact[] : [];
            const metrics = (parsed.data.metrics || {}) as RunMetrics;
            updateAssistant(messageId, (message) => ({ ...message, content: finalReply || message.content, artifacts, metrics, state: "done" }));
          } else if (parsed.name === "agent_stopped" || parsed.name === "agent_timeout") {
            finished = true;
            updateAssistant(messageId, (message) => ({ ...message, state: "stopped" }));
          } else if (parsed.name === "agent_error") {
            finished = true;
            updateAssistant(messageId, (message) => ({ ...message, content: String(parsed.data.error || "任务执行失败"), state: "error" }));
          }
        }
      }
      flushText();
      if (!finished) throw new Error("流式连接意外结束，请重试");
      await loadSessions();
    } catch (error) {
      if ((error as Error).name !== "AbortError") updateAssistant(messageId, (message) => ({ ...message, content: (error as Error).message, state: "error" }));
    } finally {
      activeRun.current = null; setRunning(false);
    }
  }

  async function stopRun() {
    const run = activeRun.current; if (!run) return;
    try {
      await api("/api/chat/stop", { method: "POST", body: JSON.stringify({ session_id: sessionId, run_id: run.id }) });
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "停止失败"); run.controller.abort();
    }
  }

  async function confirmTool(messageId: string, confirmationId: string) {
    try {
      const data = await api<{ step: ToolStep }>("/api/tool/confirm", { method: "POST", body: JSON.stringify({ confirmation_id: confirmationId }) });
      updateAssistant(messageId, (message) => {
        const remaining = (message.steps || []).filter((step) => {
          const result = step.result as { meta?: { confirmation?: { id?: string } } } | undefined;
          return result?.meta?.confirmation?.id !== confirmationId;
        });
        const result = data.step.result as { ok?: boolean } | undefined;
        return {
          ...message,
          content: result?.ok === false ? "已确认执行，但工具执行失败，请展开上方记录查看原因。" : "已确认并执行，结果见上方执行记录。",
          steps: [...remaining, data.step],
        };
      });
    } catch (error) { setNotice(error instanceof Error ? error.message : "确认失败"); }
  }

  function chooseProvider(value: string) { setProvider(value); localStorage.setItem("czon_agent_provider", value); }

  return (
    <div className="chat-app">
      <Sidebar identity={identity} sessions={sessions} activeId={sessionId} open={sidebarOpen} onClose={() => setSidebarOpen(false)} onNew={newChat} onOpen={openSession} onDelete={deleteSession} onLogout={logout} />
      <section className="chat-workspace">
        <header className="chat-header">
          <button className="icon-button" title={sidebarOpen ? "收起侧栏" : "打开侧栏"} onClick={() => setSidebarOpen(!sidebarOpen)}>{sidebarOpen ? <Menu size={18} /> : <PanelLeftOpen size={18} />}</button>
          <div className="header-copy">
            <div className="header-title">
              <span className="header-product"><strong>数据不出门</strong>{" "}<strong className="header-focus">专注自己业务</strong><strong>的企业级 AI 智能体</strong></span>
              <span className={`header-status ${running ? "is-running" : ""}`}>· {running ? `正在执行 ${formatElapsed(elapsedSeconds)}` : "就绪"}</span>
            </div>
          </div>
        </header>
        <MessageList messages={messages} onConfirm={confirmTool} runElapsedSeconds={running ? elapsedSeconds : undefined} />
        <Composer providers={providers} provider={provider} onProvider={chooseProvider} skills={skills} attachments={attachments} onAttachments={setAttachments} directory={directory} onDirectory={setDirectory} running={running} onSend={sendMessage} onStop={stopRun} onNotice={setNotice} />
      </section>
      {notice && <button className="toast" onClick={() => setNotice("")}>{notice}</button>}
    </div>
  );
}

function formatElapsed(seconds: number) {
  if (seconds < 60) return `${seconds} 秒`;
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

function parseEvent(chunk: string): { name: string; data: Record<string, unknown> } | null {
  let name = "message";
  const lines: string[] = [];
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    if (line.startsWith("data:")) lines.push(line.slice(5).trimStart());
  }
  if (!lines.length) return null;
  try { return { name, data: JSON.parse(lines.join("\n")) }; } catch { return null; }
}
