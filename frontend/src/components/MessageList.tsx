import { useEffect, useRef, useState } from "react";
import { Copy, Download, FileText, FolderOpen } from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../types";
import { ToolTimeline } from "./ToolTimeline";
import { AssistantAvatar } from "./AssistantAvatar";

type Props = {
  messages: ChatMessage[];
  onConfirm: (messageId: string, confirmationId: string) => void;
  runElapsedSeconds?: number;
};

export function MessageList({ messages, onConfirm, runElapsedSeconds }: Props) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  return (
    <main className="message-scroll">
      <div className="message-column">
        {messages.length === 0 && (
          <EmptyState />
        )}
        {messages.map((message) => message.role === "user" ? (
          <article className="message user-message" key={message.id}>
            <div className="user-content">{message.content}
              {Boolean(message.attachments?.length) && <div className="message-files">{message.attachments!.map((file) => <span key={file.path}><FileText size={13} />{file.name}</span>)}</div>}
              {message.directory && <div className="message-files"><span><FolderOpen size={13} />{message.directory.name} · {message.directory.total_files} 个文件（仅清单）</span></div>}
            </div>
          </article>
        ) : (
          <article className="message assistant-message" key={message.id}>
            <div className="assistant-glyph"><AssistantAvatar /></div>
            <div className="assistant-content">
              <div className="assistant-label">czon Agent</div>
              <ToolTimeline
                steps={message.steps || []}
                onConfirm={(id) => onConfirm(message.id, id)}
                runElapsedSeconds={message.state === "running" ? runElapsedSeconds : undefined}
                completed={message.state === "done"}
                durationMs={message.metrics?.duration_ms}
              />
              {message.content && <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>{message.content}</ReactMarkdown>}
              {Boolean(message.artifacts?.length) && <div className="artifact-list">{message.artifacts!.map((file) => (
                <a className="artifact-row" href={file.download_url} key={file.id} download>
                  <FileText size={17} />
                  <span><strong>{file.name}</strong><small>{formatBytes(file.size)}</small></span>
                  <Download size={16} />
                </a>
              ))}</div>}
              {message.state === "running" && !message.content && <div className="thinking"><span /><span /><span /></div>}
              {message.state === "stopped" && <div className="message-note">任务已停止</div>}
              {message.state === "error" && <div className="message-error">{message.content || "任务执行失败"}</div>}
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
  const prompt = "输入任务，或键入 / 选择一个 Skill";
  const [text, setText] = useState("");
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setText(prompt);
      return;
    }
    let index = 0;
    const timer = window.setInterval(() => {
      index += 1;
      setText(prompt.slice(0, index));
      if (index >= prompt.length) window.clearInterval(timer);
    }, 72);
    return () => window.clearInterval(timer);
  }, []);
  return <section className="empty-state"><h1>开始一项工作</h1><p className="matrix-type">{text}</p></section>;
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
