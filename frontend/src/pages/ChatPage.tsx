import { LanguagePicker } from "../components/LanguagePicker";
import { useTranslation } from "react-i18next";
import { t } from "../i18n";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Menu, PanelLeftOpen, Settings, Plus, Monitor, Volume2, VolumeX } from "lucide-react";
import { Link } from "react-router-dom";
import { api, randomId, setCsrfToken } from "../api";
import { useNarration } from "../hooks/useNarration";
import { Composer } from "../components/Composer";
import { MessageList } from "../components/MessageList";
import { Sidebar } from "../components/Sidebar";
import { useRuns, isActive } from "../hooks/useRuns";
import type { Run } from "../hooks/useRuns";
import type { Attachment, ChatMessage, Identity, LocalDirectory, Provider, Session, Skill, ToolStep } from "../types";

type Props = { identity: Identity; onLogout: () => void; display?: boolean };
type HistoryMessage = ChatMessage & { run_id?: string; duration_ms?: number; input_tokens?: number; output_tokens?: number };

export function ChatPage({ identity, onLogout, display = false }: Props) {
  const { i18n } = useTranslation();
  const storageKey = `czon_agent_session_id:${identity.username}`;
  const [sessionId, setSessionId] = useState(() => sessionStorage.getItem(storageKey) || randomId());
  const currentSession = useRef(sessionId); currentSession.current = sessionId;
  const [sessions, setSessions] = useState<Session[]>([]);
  const [historyRuns, setHistoryRuns] = useState<Run[]>([]);
  const [history, setHistory] = useState<HistoryMessage[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [provider, setProvider] = useState(() => localStorage.getItem("czon_agent_provider") || "");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [directory, setDirectory] = useState<LocalDirectory | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth > 760);
  const [notice, setNotice] = useState("");
  const [speaking, setSpeaking] = useState(false);
  const wasDisplay = useRef(display);
  const displayedRun = useRef<string | undefined>(undefined);
  const requests = useRef(new Map<string, { signature: string; id: string }>());
  const [submitting, setSubmitting] = useState(false);
  const [scrollRequest, setScrollRequest] = useState(0);
  const { runs, connected, revision } = useRuns(identity.username);
  const orderedRuns = useMemo(() => Object.values(runs).sort((a, b) => a.created_at.localeCompare(b.created_at)), [runs]);
  const selected = orderedRuns.filter(run => run.session_id === sessionId);
  const selectedCache = useRef<Run[]>([]);
  if (selected.length !== selectedCache.current.length || selected.some((run, index) => run !== selectedCache.current[index])) selectedCache.current = selected;
  const sessionRuns = useMemo(() => [...new Map([...historyRuns, ...selectedCache.current].filter(run => run.session_id === sessionId).map(run => [run.id, run])).values()].sort((a, b) => a.created_at.localeCompare(b.created_at)), [historyRuns, selectedCache.current, sessionId]);
  const active = sessionRuns.find(isActive);
  const narration = useNarration(sessionRuns[sessionRuns.length - 1], speaking,
    text => { setNotice(text); setSpeaking(false); },
    () => {});
  const running = Boolean(active);
  const activeSessions = new Set(orderedRuns.filter(isActive).map(run => run.session_id));
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [confirmed, setConfirmed] = useState<Record<string, ToolStep>>({});

  const rememberSession = useCallback((id: string) => {
    setSessionId(id); sessionStorage.setItem(storageKey, id);
  }, [storageKey]);
  useEffect(() => { document.title = display ? t("任务大屏 · czon Agent") : t("工作台 · czon Agent"); }, [display, i18n.resolvedLanguage]);
  useEffect(() => {
    const viewport = window.visualViewport;
    const resize = () => {
      // Safari's layout viewport does not shrink when the software keyboard opens.
      if (!viewport || viewport.scale !== 1) return;
      document.documentElement.style.setProperty("--chat-height", `${viewport.height}px`);
    };
    resize(); viewport?.addEventListener("resize", resize);
    return () => { viewport?.removeEventListener("resize", resize); document.documentElement.style.removeProperty("--chat-height"); };
  }, []);
  useEffect(() => { sessionStorage.setItem(storageKey, sessionId); }, [storageKey, sessionId]);
  const loadSessions = useCallback(async () => {
    const data = await api<{ sessions: Session[] }>("/api/sessions", { cache: "no-store" });
    setSessions(data.sessions);
  }, []);
  useEffect(() => { void loadSessions().catch(() => setNotice(t("会话列表暂时无法更新"))); }, [loadSessions, revision]);
  useEffect(() => {
    let cancelled = false;
    setHistory([]); setHistoryRuns([]);
    api<{ messages: HistoryMessage[]; runs: Run[] }>(`/api/sessions/${sessionId}`, { cache: "no-store" })
      .then(data => { if (!cancelled) { setHistory(data.messages); setHistoryRuns(data.runs || []); } }).catch(() => {});
    return () => { cancelled = true; };
  }, [sessionId]);
  useEffect(() => {
    void Promise.all([
      api<Provider[]>("/api/providers").then(items => { setProviders(items); setProvider(previous => items.some(item => item.name === previous && item.configured) ? previous : items.find(item => item.configured)?.name || ""); }),
      api<{ skills: Skill[] }>("/api/skills").then(data => setSkills(data.skills)),
    ]).catch(error => setNotice(String(error)));
  }, []);
  useEffect(() => {
    if (!active) { setElapsedSeconds(0); return; }
    const tick = () => setElapsedSeconds(Math.max(0, Math.floor((Date.now() - Date.parse(active.started_at || active.created_at)) / 1000)));
    tick(); const timer = setInterval(tick, 1000); return () => clearInterval(timer);
  }, [active?.id, active?.started_at]);
  useEffect(() => {
    const latest = orderedRuns[orderedRuns.length - 1];
    if (display && !wasDisplay.current) {
      // Entering display mode must not replace the task currently being heard.
      displayedRun.current = latest?.id;
    } else if (display && latest && latest.id !== displayedRun.current) {
      rememberSession(latest.session_id); displayedRun.current = latest.id;
    }
    wasDisplay.current = display;
  }, [display, orderedRuns, rememberSession]);

  const messages: ChatMessage[] = useMemo(() => {
    const byRun = new Map(sessionRuns.map(run => [run.id, run]));
    const covered = new Set(history.map(message => message.run_id).filter(Boolean));
    const result: ChatMessage[] = history.map(message => ({ ...message, id: `history-${message.id}`, state: "done", steps: message.role === "assistant" && message.run_id ? byRun.get(message.run_id)?.steps : undefined, metrics: message.role === "assistant" ? { duration_ms: message.duration_ms, input_tokens: message.input_tokens, output_tokens: message.output_tokens } : undefined }));
    for (const run of sessionRuns) {
      if (covered.has(run.id)) continue;
      result.push({ id: `user-${run.id}`, role: "user", content: run.text, attachments: run.attachments, directory: run.directory });
      result.push({ id: `assistant-${run.id}`, role: "assistant", content: run.reply + (run.error ? `\n\n${run.error}` : ""), steps: run.steps, progress: run.progress, artifacts: run.artifacts, metrics: run.metrics, state: isActive(run) ? "running" : run.status === "completed" ? "done" : run.status === "stopped" ? "stopped" : "error" });
    }
    return result.map(message => ({ ...message, steps: message.steps?.map(step => {
      const id = (step.result as { meta?: { confirmation?: { id?: string } } })?.meta?.confirmation?.id;
      return id && confirmed[id] ? confirmed[id] : step;
    }) }));
  }, [history, sessionRuns, confirmed]);

  function openSession(id: string) { rememberSession(id); setAttachments([]); setDirectory(null); if (window.innerWidth <= 760) setSidebarOpen(false); }
  function newChat() { openSession(randomId()); }
  async function deleteSession(id: string) {
    if (!window.confirm(t("确定删除这个会话吗？"))) return;
    try { await api(`/api/sessions/${id}`, { method: "DELETE" }); if (id === sessionId) newChat(); await loadSessions(); }
    catch (error) { setNotice((error as Error).message); }
  }
  async function logout() {
    try { await api("/api/auth/logout", { method: "POST" }); } catch { /* Keep local logout available. */ }
    setCsrfToken(""); onLogout();
  }
  async function sendMessage(text: string, skill: Skill | null) {
    if (submitting) return false;
    setSubmitting(true);
    setScrollRequest(value => value + 1);
    // Reacquire audio in the send gesture after keyboard dictation releases the microphone.
    if (speaking) void narration.unlock().catch(error => setNotice((error as Error).message));
    const signature = JSON.stringify({ text, attachments, directory, provider, skill: skill?.name || null });
    const previous = requests.current.get(sessionId);
    const requestId = previous?.signature === signature ? previous.id : randomId();
    requests.current.set(sessionId, { signature, id: requestId });
    const request = { text, attachments, directory, provider, session_id: sessionId, run_id: requestId, skill: skill?.name || null };
    try {
      await api<Run>("/api/runs", { method: "POST", body: JSON.stringify(request) });
      requests.current.delete(request.session_id);
      if (currentSession.current === request.session_id) { setAttachments([]); setDirectory(null); }
      void loadSessions(); return true;
    } catch (error) { setNotice(t("提交未确认，请先查看任务列表，避免重复执行业务。{{value0}}", { value0: (error as Error).message })); return false; }
    finally { setSubmitting(false); }
  }
  async function stopRun() {
    if (!active) return;
    try { await api("/api/chat/stop", { method: "POST", body: JSON.stringify({ session_id: active.session_id, run_id: active.id }) }); }
    catch (error) { setNotice((error as Error).message); }
  }
  async function confirmTool(_messageId: string, confirmationId: string) {
    try {
      const data = await api<{ step: ToolStep }>("/api/tool/confirm", { method: "POST", body: JSON.stringify({ confirmation_id: confirmationId }) });
      setConfirmed(previous => ({ ...previous, [confirmationId]: data.step }));
    } catch (error) { setNotice((error as Error).message); }
  }

  function chooseProvider(value: string) { setProvider(value); localStorage.setItem("czon_agent_provider", value); }
  async function toggleNarration() {
    if (speaking) { setSpeaking(false); return; }
    try { await narration.unlock(); setSpeaking(true); }
    catch { setNotice(t("设备未能开启声音，请再点击一次播报按钮")); }
  }

  return (
    <div className={`chat-app ${display ? "display-mode" : ""}`}>
      {!display && <Sidebar identity={identity} sessions={sessions} runningIds={activeSessions} activeId={sessionId} open={sidebarOpen} onClose={() => setSidebarOpen(false)} onNew={newChat} onOpen={openSession} onDelete={deleteSession} onLogout={logout} />}
      <section className="chat-workspace">
        <header className="chat-header">
          {!display && <button className="icon-button" aria-label={t("切换会话侧栏")} title={sidebarOpen ? t("收起侧栏") : t("打开侧栏")} onClick={() => setSidebarOpen(!sidebarOpen)}>{sidebarOpen ? <Menu size={18} /> : <PanelLeftOpen size={18} />}</button>}
          <div className="header-copy">
            <div className="header-title">
              <strong className="workspace-title">{display ? t("任务大屏") : t("AI智能体")}</strong>
              {(!connected || running) && <span className={`header-status ${running ? "is-running" : ""}`}>{!connected ? t("正在重连") : t("执行中 · {{value0}}", { value0: formatElapsed(elapsedSeconds) })}</span>}
            </div>
          </div>
          <div className="header-actions">
            {!display && <button className="icon-button" aria-label={t("新任务")} title={t("新任务")} onClick={newChat}><Plus size={20} /></button>}
            <Link className="icon-button display-link" to={display ? "/" : "/display"} aria-label={display ? t("返回工作台") : t("打开大屏模式")} title={display ? t("返回工作台") : t("大屏模式")}><Monitor size={19} /></Link>
            <button className={`icon-button narration-toggle ${speaking ? "is-active" : ""}`} title={speaking ? t("关闭本机播报") : t("开启本机播报")} aria-label={speaking ? t("关闭本机播报") : t("开启本机播报")} onClick={() => void toggleNarration()} aria-pressed={speaking}>{speaking ? <Volume2 size={19} /> : <VolumeX size={19} />}</button>
            <LanguagePicker />
          </div>
        </header>
        <MessageList key={`messages-${sessionId}`} messages={messages} userName={identity.username} scrollRequest={scrollRequest} waitingRun={active} narrated={speaking} onConfirm={confirmTool} runElapsedSeconds={running ? elapsedSeconds : undefined} />
        {!providers.some((item) => item.configured) && <div className="no-model-banner">
          <span>{identity.is_admin ? t("尚未配置模型，完成配置后即可开始对话。") : t("系统尚未配置模型，请联系管理员。")}</span>
          {identity.is_admin && <a href="/admin/models"><Settings size={14} />{t("配置模型")}</a>}
        </div>}
        {!display && <Composer key={`composer-${sessionId}`} providers={providers} provider={provider} onProvider={chooseProvider} skills={skills} attachments={attachments} onAttachments={setAttachments} directory={directory} onDirectory={setDirectory} running={running} onSend={sendMessage} onStop={stopRun} onNotice={setNotice} />}
      </section>
      {notice && <button className="toast" aria-live="polite" onClick={() => setNotice("")}>{notice}</button>}
    </div>
  );
}

function formatElapsed(seconds: number) {
  if (seconds < 60) return t("{{value0}} 秒", { value0: seconds });
  return t("{{value0}} 分 {{value1}} 秒", { value0: Math.floor(seconds / 60), value1: seconds % 60 });
}
