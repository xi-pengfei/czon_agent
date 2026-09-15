import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { RefreshCw, Trash2, Upload } from "lucide-react";
import { api, formatTime } from "../../api";
import { EmptyTable, PageHeader, Toggle } from "./AdminParts";

type SkillRecord = {
  name: string;
  description: string;
  path: string;
  size: number;
  modified_at: string;
  enabled: boolean;
};

export function SkillsPage() {
  const [skills, setSkills] = useState<SkillRecord[]>([]);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    const data = await api<{ skills: SkillRecord[] }>("/api/admin/skills", { cache: "no-store" });
    setSkills(data.skills);
  };

  useEffect(() => { void load().catch((error) => setNotice((error as Error).message)); }, []);

  async function rescan() {
    setBusy("rescan");
    try {
      const data = await api<{ skills: SkillRecord[] }>("/api/admin/skills/rescan", { method: "POST" });
      setSkills(data.skills); setNotice("Skills 目录已重新扫描");
    } catch (error) { setNotice((error as Error).message); }
    finally { setBusy(""); }
  }

  async function toggle(skill: SkillRecord, enabled: boolean) {
    setBusy(skill.name);
    try {
      await api(`/api/admin/skills/${encodeURIComponent(skill.name)}`, { method: "PUT", body: JSON.stringify({ enabled }) });
      setSkills((items) => items.map((item) => item.name === skill.name ? { ...item, enabled } : item));
      setNotice(`${skill.name} 已${enabled ? "启用" : "停用"}`);
    } catch (error) { setNotice((error as Error).message); }
    finally { setBusy(""); }
  }

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy("upload");
    const body = new FormData(); body.append("file", file);
    try {
      const result = await api<{ name: string; action: "installed" | "updated" }>("/api/admin/skills/upload", { method: "POST", body });
      setNotice(`${result.name} ${result.action === "updated" ? "已更新" : "已上传"}`); await load();
    } catch (error) { setNotice((error as Error).message); }
    finally { setBusy(""); }
  }

  async function remove(skill: SkillRecord) {
    if (skill.enabled || !window.confirm(`确定永久删除 ${skill.name} 吗？此操作不能撤销。`)) return;
    setBusy(skill.name);
    try {
      await api(`/api/admin/skills/${encodeURIComponent(skill.name)}`, { method: "DELETE" });
      setNotice(`${skill.name} 已删除`); await load();
    } catch (error) { setNotice((error as Error).message); }
    finally { setBusy(""); }
  }

  return <main className="admin-content">
    <PageHeader title="技能管理" description="管理服务器上的企业专属 Skills" action={<div className="page-actions">
      <button className="secondary-button compact" disabled={!!busy} onClick={() => void rescan()}><RefreshCw className={busy === "rescan" ? "spin" : ""} size={15} />重新扫描</button>
      <button className="primary-button compact" disabled={!!busy} onClick={() => inputRef.current?.click()}><Upload size={15} />上传 ZIP</button>
      <input ref={inputRef} className="visually-hidden" type="file" accept=".zip,application/zip" onChange={(event) => void upload(event)} />
    </div>} />
    <div className="table-toolbar"><span>共 {skills.length} 个 Skill</span><span>服务器 Skills 目录</span></div>
    <div className="data-table"><table><thead><tr><th>Skill</th><th>目录</th><th>大小</th><th>更新时间</th><th>状态</th><th>操作</th></tr></thead><tbody>{skills.map((skill) => <tr key={skill.name}>
      <td><div className="skill-admin-name"><strong>{skill.name}</strong><small>{skill.description}</small></div></td>
      <td className="skill-path" title={skill.path}>{skill.path}</td>
      <td>{formatBytes(skill.size)}</td><td>{formatTime(skill.modified_at)}</td>
      <td><Toggle checked={skill.enabled} onChange={(value) => void toggle(skill, value)} label={skill.enabled ? "启用" : "停用"} /></td>
      <td><button className="text-button danger" disabled={skill.enabled || busy === skill.name} title={skill.enabled ? "请先停用再删除" : "删除 Skill"} onClick={() => void remove(skill)}><Trash2 size={14} />删除</button></td>
    </tr>)}</tbody></table>{!skills.length && <EmptyTable text="没有发现有效的 Skill" />}</div>
    {notice && <button className="toast" onClick={() => setNotice("")}>{notice}</button>}
  </main>;
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
