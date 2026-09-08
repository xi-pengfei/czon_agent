import { Check, ChevronDown, CircleAlert, LoaderCircle, ShieldAlert } from "lucide-react";
import type { ToolStep } from "../types";

type Props = { steps: ToolStep[]; onConfirm: (id: string) => void; runElapsedSeconds?: number; completed?: boolean; durationMs?: number };

function confirmation(step: ToolStep) {
  const result = step.result as { meta?: { confirmation?: { id?: string; reason?: string } }; error?: { type?: string } } | undefined;
  return result?.meta?.confirmation;
}

function failed(step: ToolStep) {
  const result = step.result as { ok?: boolean; error?: unknown } | undefined;
  return Boolean(result?.error || result?.ok === false);
}

export function ToolTimeline({ steps, onConfirm, runElapsedSeconds, completed = false, durationMs }: Props) {
  if (!steps.length) return null;
  const hasConfirmation = steps.some((step) => Boolean(confirmation(step)?.id));
  const hasFailure = steps.some((step) => failed(step) && !confirmation(step));
  const events = steps.map((step, index) => {
        const confirm = confirmation(step);
        const isRunning = !step.result;
        const isFailed = failed(step) && !confirm;
        return (
          <details className={`tool-event ${isFailed ? "is-error" : ""} ${confirm ? "is-confirm" : ""}`} open={isRunning || Boolean(confirm?.id)} key={`${step.id || step.name}-${index}`}>
            <summary>
              <span className="tool-state">
                {isRunning ? <LoaderCircle className="spin" size={14} /> : confirm ? <ShieldAlert size={14} /> : isFailed ? <CircleAlert size={14} /> : <Check size={14} />}
              </span>
              <span className="tool-title">
                {step.name || "工具"}
                {step.duration_ms !== undefined
                  ? <small>{formatDuration(step.duration_ms)}</small>
                  : isRunning && runElapsedSeconds !== undefined
                    ? <small>运行中 · {formatElapsed(runElapsedSeconds)}</small>
                    : null}
              </span>
              <span className="tool-args">{step.args ? JSON.stringify(step.args) : ""}</span>
              <ChevronDown className="tool-chevron" size={15} />
            </summary>
            <pre>{step.progress || JSON.stringify(step.result || {}, null, 2)}</pre>
            {confirm?.id && <button className="warning-button" onClick={(event) => { event.preventDefault(); onConfirm(confirm.id!); }}>确认执行</button>}
          </details>
        );
      });
  if (!completed) return <div className="tool-timeline">{events}</div>;
  return <details className={`tool-run ${hasFailure ? "is-error" : ""}`} open={hasConfirmation || undefined}>
    <summary>
      <span className="tool-state">{hasFailure ? <CircleAlert size={14} /> : <Check size={14} />}</span>
      <span><strong>执行记录</strong><small>{steps.length} 个步骤{durationMs !== undefined ? ` · ${formatDuration(durationMs)}` : ""}</small></span>
      <ChevronDown className="tool-chevron" size={15} />
    </summary>
    <div className="tool-timeline">{events}</div>
  </details>;
}

function formatElapsed(seconds: number) {
  if (seconds < 60) return `${seconds} 秒`;
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

function formatDuration(milliseconds: number) {
  if (milliseconds < 1000) return `${milliseconds} ms`;
  return `${(milliseconds / 1000).toFixed(milliseconds < 10000 ? 1 : 0)} s`;
}
