import { useEffect, useState, type FormEvent } from "react";
import { Pencil, Plus, ShieldCheck } from "lucide-react";
import { api } from "../../api";
import { Modal } from "../../components/Modal";
import type { RoleRecord } from "../../types";
import { EmptyTable, formatList, MultiSelect, PageHeader } from "./AdminParts";

const blank: RoleRecord = { name: "", skills: "*", tools: "*", models: "*", is_admin: false };

export function RolesPage() {
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [editing, setEditing] = useState<RoleRecord | null>(null);
  const [notice, setNotice] = useState("");
  const [catalog, setCatalog] = useState<{ skills: Array<{ name: string; description: string }>; tools: string[]; models: string[] }>({ skills: [], tools: [], models: [] });
  const load = () => api<{ roles: RoleRecord[] }>("/api/admin/roles").then((data) => setRoles(data.roles));
  useEffect(() => { void Promise.all([load(), api<typeof catalog>("/api/admin/catalog").then(setCatalog)]); }, []);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!editing) return;
    const value = editing;
    try { await api(`/api/admin/roles/${encodeURIComponent(value.name)}`, { method: "PUT", body: JSON.stringify(value) }); setEditing(null); setNotice("角色已保存"); await load(); }
    catch (error) { setNotice((error as Error).message); }
  }

  return <main className="admin-content">
    <PageHeader title="角色权限" description="控制不同账号可使用的 Skills、工具和模型" action={<button className="primary-button compact" onClick={() => setEditing(blank)}><Plus size={16} />新建角色</button>} />
    <div className="data-table"><table><thead><tr><th>角色</th><th>Skills</th><th>工具</th><th>模型</th><th>类型</th><th>操作</th></tr></thead><tbody>{roles.map((role) => <tr key={role.name}>
      <td><strong>{role.name}</strong></td><td className="limited-cell">{formatList(role.skills)}</td><td className="limited-cell">{formatList(role.tools)}</td><td className="limited-cell">{formatList(role.models)}</td>
      <td>{role.is_admin ? <span className="status accent"><ShieldCheck size={13} />管理员</span> : <span className="status">普通角色</span>}</td>
      <td><button className="text-button" onClick={() => setEditing(role)}><Pencil size={14} />编辑</button></td>
    </tr>)}</tbody></table>{!roles.length && <EmptyTable text="暂无角色" />}</div>
    {editing && <Modal title={editing.name ? `编辑 ${editing.name}` : "新建角色"} onClose={() => setEditing(null)}><form className="modal-form" onSubmit={save}>
      <label>角色名称<input value={editing.name} onChange={(event) => setEditing({ ...editing, name: event.target.value })} readOnly={Boolean(roles.some((item) => item.name === editing.name))} required /></label>
      <MultiSelect label="允许的 Skills" value={editing.skills} options={catalog.skills.map((item) => ({ value: item.name, label: item.name }))} onChange={(skills) => setEditing({ ...editing, skills })} />
      <MultiSelect label="允许的工具" value={editing.tools} options={catalog.tools.map((item) => ({ value: item, label: item }))} onChange={(tools) => setEditing({ ...editing, tools })} />
      <MultiSelect label="允许的模型" value={editing.models} options={catalog.models.map((item) => ({ value: item, label: item }))} onChange={(models) => setEditing({ ...editing, models })} />
      <label className="check-field"><input type="checkbox" checked={editing.is_admin} onChange={(event) => setEditing({ ...editing, is_admin: event.target.checked })} />允许进入系统管理</label>
      <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setEditing(null)}>取消</button><button className="primary-button">保存角色</button></div>
    </form></Modal>}
    {notice && <button className="toast" onClick={() => setNotice("")}>{notice}</button>}
  </main>;
}
