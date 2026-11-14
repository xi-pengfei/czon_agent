import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { isActive, type Run } from "../hooks/useRuns";
import { useLiveText } from "../hooks/useLiveText";

// Public progress summaries are independent of optional humorous tips and local audio.
export function WaitingHint({ run }: { run?: Run; narrated?: boolean }) {
  const [text, setText] = useState("");
  const latest = useRef(run); latest.current = run;
  const active = Boolean(run && isActive(run));
  useEffect(() => {
    setText("");
    if (!run || !active) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let lastEvidence = "";
    const signature = (value: Run) => JSON.stringify([value.reply, value.steps.slice(-5).map(step => [step.id, Boolean(step.result)])]);
    const refresh = async () => {
      const current = latest.current;
      if (!current || !isActive(current) || controller.signal.aborted) return;
      const evidence = signature(current);
      if (evidence !== lastEvidence) {
        try {
          const summary = await api<{text: string}>(`/api/runs/${current.id}/narration`, {
            method: "POST", body: JSON.stringify({kind: "activity"}), signal: controller.signal,
          });
          if (!controller.signal.aborted && latest.current && isActive(latest.current) && signature(latest.current) === evidence) {
            setText(summary.text); lastEvidence = evidence;
          }
        } catch { /* A progress editor failure must not interrupt the business task. */ }
      }
      if (!controller.signal.aborted) timer = setTimeout(refresh, 12000);
    };
    timer = setTimeout(refresh, 6000);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [run?.id, active]);
  if (!active || !text) return null;
  return <ActivityText key={text} text={text} />;
}

function ActivityText({ text }: { text: string }) {
  const visible = useLiveText(text, true);
  return <div className="activity-summary" aria-label="当前核对进度">{visible}</div>;
}
