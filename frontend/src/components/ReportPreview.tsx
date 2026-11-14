import { t } from "../i18n";
import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import type { Artifact } from "../types";



export function ReportPreview({ file }: { file: Artifact }) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const frame = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(240);
  useEffect(() => {
    const controller = new AbortController();
    setReady(false); setError("");
    async function load() {
      try {
        const response = await fetch(`/api/artifacts/${encodeURIComponent(file.id)}/preview`, { method: "HEAD", signal: controller.signal, credentials: "same-origin", cache: "no-store" });
        if (!response.ok) throw new Error(response.status === 404 ? t("报表已删除或当前账号无权查看") : t("报表加载失败，请重试或下载查看"));
        if (!response.headers.get("content-type")?.includes("text/html")) throw new Error(t("返回的内容不是 HTML 报表"));
        if (!controller.signal.aborted) setReady(true);
      } catch (err) {
        if (!controller.signal.aborted) setError((err as Error).message);
      }
    }
    void load();
    return () => controller.abort();
  }, [file.id, attempt]);
  useEffect(() => {
    function resize(event: MessageEvent) {
      if (event.source !== frame.current?.contentWindow || event.data?.type !== "czon-report-height") return;
      const next = event.data.height;
      if (typeof next === "number" && Number.isFinite(next) && next > 0 && next <= 10000000) setHeight(Math.ceil(next));
    }
    window.addEventListener("message", resize);
    return () => window.removeEventListener("message", resize);
  }, []);
  return <section className="report-preview" aria-label={t("客户经营分析报表")}>
    {error ? <div className="report-preview-status" role="alert">{error}<button onClick={() => setAttempt(attempt + 1)}><RefreshCw size={14} />{t("重试")}</button></div>
      : ready ? <iframe ref={frame} style={{ height }} scrolling="no" title={t("客户经营分析可视化报表")} src={`/api/artifacts/${encodeURIComponent(file.id)}/preview`} sandbox="allow-scripts allow-downloads" referrerPolicy="no-referrer" />
        : <div className="report-preview-status" role="status">{t("正在加载报表…")}</div>}
  </section>;
}
