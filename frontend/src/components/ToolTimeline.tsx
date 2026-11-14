import { t } from "../i18n";
import { ShieldAlert } from "lucide-react";
import type { ToolStep } from "../types";

type Props = { steps: ToolStep[]; onConfirm: (id: string) => void; runElapsedSeconds?: number; completed?: boolean; durationMs?: number; outcome?: string };
export function ToolTimeline({ steps, onConfirm, runElapsedSeconds, completed = false }: Props) {
  const confirmations = steps.flatMap(step => {
    const result = step.result as { meta?: { confirmation?: { id?: string; reason?: string } } } | undefined;
    const confirmation = result?.meta?.confirmation;
    return confirmation?.id ? [{ step, confirmation }] : [];
  });
  const pending = [...steps].reverse().find(step => !step.result);
  const status = confirmations.length ? t("需要你确认这项操作") : pending
    ? ({ activate_skill: t("正在了解业务规则"), read: t("正在阅读相关资料"), write: t("正在整理成果"), bash: t("正在处理业务数据") } as Record<string, string>)[pending.name] || "正在处理请求"
    : t("正在组织回复");
  if (completed && !confirmations.length) return null;
  return <section className="process-summary" aria-label={t("处理进度")}>
    {!completed && <div className="process-status"><span className="waiting-sheen" role="status">{status}</span>{runElapsedSeconds !== undefined && <small>{t("已处理")} {runElapsedSeconds < 60 ? t("{{value0}} 秒", { value0: runElapsedSeconds }) : t("{{value0}} 分 {{value1}} 秒", { value0: Math.floor(runElapsedSeconds / 60), value1: runElapsedSeconds % 60 })}</small>}</div>}
    {confirmations.map(({ step, confirmation }) => <section className="operation-confirmation" key={confirmation.id}>
      <strong><ShieldAlert size={16} />{t("这项操作需要你确认")}</strong>
      <p>{confirmation.reason || "请核对操作内容后再继续。"}</p>
      <details><summary>{t("核对操作内容")}</summary><pre>{JSON.stringify(step.args || {}, null, 2)}</pre></details>
      <button className="warning-button" onClick={() => onConfirm(confirmation.id!)}>{t("确认执行")}</button>
    </section>)}
  </section>;
}
