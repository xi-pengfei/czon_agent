import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api, formatTime } from "../../api";
import type { AuditRecord, RuntimeLog } from "../../types";
import { EmptyTable, PageHeader, SearchBox } from "./AdminParts";

export function LogsPage() {
  const [view, setView] = useState<"audit" | "runtime">("audit");
  const [audit, setAudit] = useState<AuditRecord[]>([]);
  const [runtime, setRuntime] = useState<RuntimeLog[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  async function load() {
    setLoading(true);
    try {
      const [auditData, runtimeData] = await Promise.all([api<{ audit: AuditRecord[] }>("/api/admin/audit"), api<{ logs: RuntimeLog[] }>("/api/admin/logs")]);
      setAudit(auditData.audit); setRuntime(runtimeData.logs);
    } finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  const audits = useMemo(() => audit.filter((item) => `${item.actor} ${item.action} ${item.target}`.toLowerCase().includes(search.toLowerCase())), [audit, search]);
  const logs = useMemo(() => runtime.filter((item) => `${item.level} ${item.message}`.toLowerCase().includes(search.toLowerCase())), [runtime, search]);

  return <main className="admin-content">
    <PageHeader title="日志中心" description="查看管理员操作和系统运行状态" action={<button className="secondary-button compact" disabled={loading} onClick={load}><RefreshCw className={loading ? "spin" : ""} size={15} />刷新</button>} />
    <div className="subnav"><button className={view === "audit" ? "is-active" : ""} onClick={() => setView("audit")}>操作审计</button><button className={view === "runtime" ? "is-active" : ""} onClick={() => setView("runtime")}>运行日志</button></div>
    <div className="table-toolbar"><SearchBox value={search} onChange={setSearch} placeholder="筛选日志" /><span>{view === "audit" ? audits.length : logs.length} 条记录</span></div>
    {view === "audit" ? <div className="data-table"><table><thead><tr><th>时间</th><th>操作者</th><th>动作</th><th>对象</th></tr></thead><tbody>{audits.map((item, index) => <tr key={`${item.created_at}-${index}`}><td>{formatTime(item.created_at)}</td><td>{item.actor}</td><td><code>{item.action}</code></td><td>{item.target}</td></tr>)}</tbody></table>{!audits.length && <EmptyTable text="暂无审计记录" />}</div>
      : <div className="data-table log-table"><table><thead><tr><th>时间</th><th>级别</th><th>内容</th></tr></thead><tbody>{logs.map((item, index) => <tr key={`${item.timestamp}-${index}`}><td>{item.timestamp}</td><td><span className={`log-level ${item.level.toLowerCase()}`}>{item.level}</span></td><td className="log-message">{item.message}</td></tr>)}</tbody></table>{!logs.length && <EmptyTable text="暂无运行日志" />}</div>}
  </main>;
}
