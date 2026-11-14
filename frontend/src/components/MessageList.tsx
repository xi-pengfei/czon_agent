import { WelcomeTitle } from "./WelcomeTitle";
import { WaitingHint } from "./WaitingHint";
import type { Run } from "../hooks/useRuns";
import { streamFade } from "./streamFade";
import { useEffect, useRef, useState } from "react";
import { Copy, Download, FileText, FolderOpen } from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../types";
import { ToolTimeline } from "./ToolTimeline";
import { AssistantAvatar, replyExpression } from "./AssistantAvatar";
import { useLiveText } from "../hooks/useLiveText";
import { ReportPreview } from "./ReportPreview";

type Props = {
  messages: ChatMessage[];
  userName?: string;
  scrollRequest?: number;
  waitingRun?: Run; narrated?: boolean;
  onConfirm: (messageId: string, confirmationId: string) => void;
  runElapsedSeconds?: number;
};

export function MessageList({ messages, onConfirm, runElapsedSeconds, waitingRun, narrated, scrollRequest, userName = "你" }: Props) {
  const [motion, setMotion] = useState(true);
  const end = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  useEffect(() => { follow.current = true; end.current?.scrollIntoView({ block: "end" }); }, [scrollRequest]);
  useEffect(() => {
    if (follow.current) end.current?.scrollIntoView({ block: "end" });
  }, [messages]);
  useEffect(() => {
    const column = end.current?.parentElement;
    if (!column) return;
    const observer = new ResizeObserver(() => { if (follow.current) end.current?.scrollIntoView({ block: "end" }); });
    observer.observe(column);
    return () => observer.disconnect();
  }, []);


  return (
    <main className={`message-scroll ${motion ? "" : "motion-paused"}`} onScroll={event => { const el = event.currentTarget; follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100; }}>
      <div className="message-column">
        {messages.length === 0 && (
          <EmptyState />
        )}
        {messages.map((message) => message.role === "user" ? (
          <article className="message user-message" key={message.id}>
            <div className="user-message-name">{userName}</div>
            <div className="user-content">{message.content}
              {Boolean(message.attachments?.length) && <div className="message-files">{message.attachments!.map((file) => <span key={file.path}><FileText size={13} />{file.name}</span>)}</div>}
              {message.directory && <div className="message-files"><span><FolderOpen size={13} />{message.directory.name} · {message.directory.total_files} 个文件（仅清单）</span></div>}
            </div>
          </article>
        ) : (
          <article className="message assistant-message" key={message.id}>
            <button className="assistant-glyph" aria-label={motion ? "暂停回复动效" : "开启回复动效"} onClick={() => setMotion(value => !value)}><AssistantAvatar animated={motion} state={message.state === "error" || message.state === "stopped" || message.progress === "需要确认才能继续" ? "attention" : message.state === "running" ? message.steps?.some(step => !step.result) ? "focused" : "working" : replyExpression(message.content)} /></button>
            <div className="assistant-content">
              <div className="assistant-label">AI智能体</div>

              <ToolTimeline
                steps={message.steps || []}
                onConfirm={(id) => onConfirm(message.id, id)}
                runElapsedSeconds={message.state === "running" ? runElapsedSeconds : undefined}
                completed={message.state !== "running"}
                outcome={message.state}
                durationMs={message.metrics?.duration_ms}
              />
              {message.content && <LiveAnswer text={message.content} streaming={message.state === "running"} motion={motion} />}
              {message.id === `assistant-${waitingRun?.id}` && <WaitingHint run={waitingRun} narrated={narrated} />}
              {message.artifacts?.filter(file => file.mime === "text/html" && file.name === "report.html").map(file => <ReportPreview key={file.id} file={file} />)}
              {Boolean(message.artifacts?.length) && <div className="artifact-list">{message.artifacts!.filter(file => !message.artifacts?.some(item => item.mime === "text/html" && item.name === "report.html") || !["report.html", "report.json", "customers.csv"].includes(file.name)).map((file) => (
                <a className="artifact-row" href={file.download_url} key={file.id} download>
                  <FileText size={17} />
                  <span><strong>{file.name}</strong><small>{formatBytes(file.size)}</small></span>
                  <Download size={16} />
                </a>
              ))}</div>}

              {message.state === "stopped" && !message.content.includes("任务已停止") && <div className="message-note">任务已停止</div>}
              {message.state === "error" && !message.content && <div className="message-error">任务执行失败</div>}
              {message.state === "done" && <MessageMeta message={message} />}
            </div>
          </article>
        ))}
        <div ref={end} />
      </div>
    </main>
  );
}

function MessageMeta({ message }: { message: ChatMessage }) {
  const metrics = message.metrics;
  const tokens = (metrics?.input_tokens || 0) + (metrics?.output_tokens || 0);
  return <div className="message-meta">
    {metrics?.duration_ms !== undefined && <span>{formatDuration(metrics.duration_ms)}</span>}
    {tokens > 0 && <span>{(metrics?.input_tokens || 0).toLocaleString()} in · {(metrics?.output_tokens || 0).toLocaleString()} out</span>}
    {message.content && <button title="复制回答" onClick={() => void navigator.clipboard.writeText(message.content)}><Copy size={12} />复制</button>}
  </div>;
}

function EmptyState() {
  const [animate, setAnimate] = useState(true);
  return <section className="empty-state"><button className="welcome-avatar" aria-label={animate ? "暂停头像表情" : "播放头像表情"} title={animate ? "暂停头像表情" : "播放头像表情"} onClick={() => setAnimate(value => !value)}><AssistantAvatar ambient animated={animate} /></button><WelcomeTitle /></section>;
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function formatDuration(milliseconds: number) {
  if (milliseconds < 1000) return `${milliseconds} ms`;
  const seconds = milliseconds / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}

function LiveAnswer({ text, streaming, motion }: { text: string; streaming: boolean; motion: boolean }) {
  const visible = useLiveText(text, streaming, motion);
  return <div className={`answer-prose ${streaming ? "is-streaming" : ""}`}><ReactMarkdown components={{ table: ({ children }) => <div className="markdown-table-scroll" role="region" aria-label="数据表格，可横向滚动" tabIndex={0}><table>{children}</table></div> }} remarkPlugins={[remarkGfm]} rehypePlugins={streaming && motion ? [rehypeSanitize, streamFade] : [rehypeSanitize]}>{visible}</ReactMarkdown></div>;
}
