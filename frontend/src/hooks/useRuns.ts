import { useEffect, useState } from "react";
import { api } from "../api";
import type { Attachment, Artifact, LocalDirectory, RunMetrics, ToolStep } from "../types";

export type Run = {
  id: string; session_id: string; text: string; provider: string;
  status: "queued" | "running" | "completed" | "stopped" | "failed" | "interrupted";
  created_at: string; started_at?: string; finished_at?: string;
  reply: string; progress: string; error?: string; steps: ToolStep[];
  attachments?: Attachment[]; directory?: LocalDirectory; artifacts: Artifact[]; metrics?: RunMetrics;
};
export type RunEvent = { seq: number; run_id: string; event: string; data: Record<string, unknown> };
export const isActive = (run: Run) => run.status === "queued" || run.status === "running";

export function reduceRun(run: Run, event: RunEvent): Run {
  const { data, event: name } = event;
  if (name === "agent_start") return { ...run, status: "running", started_at: new Date().toISOString(), progress: "正在处理你的请求" };
  if (name === "assistant_delta") return { ...run, reply: run.reply + String(data.text || "") };
  if (["tool_start", "tool_progress", "tool_result", "confirmation_required"].includes(name)) {
    const incoming = data as unknown as ToolStep;
    const steps = [...run.steps];
    const index = incoming.id ? steps.findIndex(step => step.id === incoming.id) : -1;
    const previous = index >= 0 ? steps[index] : {} as ToolStep;
    const step = name === "tool_progress" ? { ...previous, ...incoming, progress: `${previous.progress || ""}${incoming.text || ""}`.slice(-30000) } : { ...previous, ...incoming };
    if (index < 0) steps.push(step); else steps[index] = step;
    return { ...run, steps: steps.slice(-100), progress: name === "confirmation_required" ? "需要确认才能继续" : name === "tool_start" ? "正在执行业务操作" : "正在整理执行结果" };
  }
  if (name === "agent_done") return { ...run, status: "completed", reply: String(data.reply || ""), artifacts: data.artifacts as Artifact[] || [], metrics: data.metrics as RunMetrics, progress: "处理完成" };
  if (name === "run_stopping") return { ...run, progress: "正在停止，等待当前操作结束" };
  if (["agent_stopped", "agent_timeout", "agent_error", "agent_interrupted"].includes(name)) return { ...run, status: name === "agent_stopped" ? "stopped" : name === "agent_interrupted" ? "interrupted" : "failed", error: String(data.error || data.message || "任务未完成") };
  return run;
}

export function useRuns(username: string) {
  const [runs, setRuns] = useState<Record<string, Run>>({});
  const [connected, setConnected] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let disposed = false;
    let source: EventSource | undefined;
    let retry: ReturnType<typeof setTimeout>;
    let flush: ReturnType<typeof setTimeout> | undefined;
    let pending: RunEvent[] = [];
    let cursor = 0;
    const apply = () => {
      flush = undefined;
      const batch = pending; pending = [];
      setRuns(previous => {
        const next = { ...previous };
        for (const event of batch) {
          if (event.event === "run_created") next[event.run_id] = event.data as unknown as Run;
          else if (event.event === "session_deleted") {
            for (const [id, run] of Object.entries(next)) if (run.session_id === event.data.session_id) delete next[id];
          } else if (next[event.run_id]) next[event.run_id] = reduceRun(next[event.run_id], event);
        }
        return next;
      });
    };
    const start = async () => {
      try {
        const snapshot = await api<{ runs: Run[]; cursor: number }>("/api/runs", { cache: "no-store" });
        if (disposed) return;
        setRuns(Object.fromEntries(snapshot.runs.map(run => [run.id, run])));
        cursor = snapshot.cursor;
        source = new EventSource(`/api/events?after=${cursor}`);
        source.onopen = () => setConnected(true);
        source.onerror = () => setConnected(false); // EventSource reconnects with Last-Event-ID.
        source.addEventListener("auth_expired", () => { source?.close(); void api("/api/me"); });
        source.addEventListener("run_event", message => {
          const event = JSON.parse((message as MessageEvent).data) as RunEvent;
          if (event.seq <= cursor) return;
          cursor = event.seq;
          pending.push(event);
          if (!flush) flush = setTimeout(apply, 60);
          if (event.event === "run_created" || event.event.startsWith("agent_") && event.event !== "agent_start" || event.event === "session_deleted") setRevision(value => value + 1);
        });
      } catch {
        if (!disposed) { setConnected(false); retry = setTimeout(start, 2000); }
      }
    };
    void start();
    return () => { disposed = true; source?.close(); clearTimeout(retry); clearTimeout(flush); };
  }, [username]);
  return { runs, connected, revision };
}
