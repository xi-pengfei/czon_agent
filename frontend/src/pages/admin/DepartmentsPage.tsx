import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Pencil, Plus } from "lucide-react";
import { api, randomId } from "../../api";
import { Modal } from "../../components/Modal";
import type { DepartmentRecord } from "../../types";
import { EmptyTable, PageHeader, Toggle } from "./AdminParts";

type Draft = DepartmentRecord;

export function DepartmentsPage() {
  const [departments, setDepartments] = useState<DepartmentRecord[]>([]);
  const [editing, setEditing] = useState<Draft | null>(null);
  const [notice, setNotice] = useState("");
  const load = () => api<{ departments: DepartmentRecord[] }>("/api/admin/departments").then((data) => setDepartments(data.departments));
  useEffect(() => { void load(); }, []);
  const rows = useMemo(() => flattenTree(departments), [departments]);

  async function save(event: FormEvent) {
    event.preventDefault(); if (!editing) return;
    try {
      const payload = { id: editing.id, name: editing.name, parent_id: editing.parent_id, monthly_token_quota_million: editing.monthly_token_quota_million, active: editing.active };
      await api(`/api/admin/departments/${editing.id}`, { method: "PUT", body: JSON.stringify(payload) });
      setEditing(null); setNotice("部门已保存"); await load();
    } catch (error) { setNotice((error as Error).message); }
  }

  function create(parentId: string | null = "root") {
    setEditing({ id: randomId(), name: "", parent_id: parentId, monthly_token_quota_million: null, active: true, user_count: 0, created_at: "" });
  }

  return <main className="admin-content">
    <PageHeader title="组织架构" description="维护树形部门和部门默认 Token 额度" action={<button className="primary-button compact" onClick={() => create()}><Plus size={16} />新建部门</button>} />
    <div className="data-table"><table><thead><tr><th>部门</th><th>上级部门</th><th>直属用户</th><th>每月额度</th><th>状态</th><th>操作</th></tr></thead><tbody>{rows.map(({ item, depth }) => <tr key={item.id}>
      <td><strong className="department-name" style={{ paddingLeft: `${depth * 18}px` }}>{depth > 0 && <span>└</span>}{item.name}</strong></td>
      <td>{departments.find((parent) => parent.id === item.parent_id)?.name || "-"}</td><td>{item.user_count}</td><td>{item.monthly_token_quota_million == null ? "不限" : `${item.monthly_token_quota_million} M`}</td>
      <td>{item.active ? <span className="status success">启用</span> : <span className="status">停用</span>}</td>
      <td><button className="text-button" onClick={() => setEditing({ ...item })}><Pencil size={14} />编辑</button>{item.id !== "root" && <button className="text-button" onClick={() => create(item.id)}><Plus size={14} />下级部门</button>}</td>
    </tr>)}</tbody></table>{!rows.length && <EmptyTable text="暂无部门" />}</div>
    {editing && <Modal title={departments.some((item) => item.id === editing.id) ? `编辑 ${editing.name}` : "新建部门"} onClose={() => setEditing(null)}><form className="modal-form" onSubmit={save}>
      <label>部门名称<input value={editing.name} onChange={(event) => setEditing({ ...editing, name: event.target.value })} required /></label>
      <label>上级部门<select value={editing.parent_id || ""} disabled={editing.id === "root"} onChange={(event) => setEditing({ ...editing, parent_id: event.target.value || null })}><option value="">无上级</option>{departments.filter((item) => item.id !== editing.id && item.active).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
      <label>每月 Token 额度（百万）<input type="number" min="0" step="0.1" value={editing.monthly_token_quota_million ?? ""} placeholder="留空表示不限" onChange={(event) => setEditing({ ...editing, monthly_token_quota_million: event.target.value === "" ? null : Number(event.target.value) })} /></label>
      <Toggle checked={editing.active} onChange={(active) => setEditing({ ...editing, active })} label={editing.active ? "部门启用" : "部门停用"} />
      <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setEditing(null)}>取消</button><button className="primary-button">保存部门</button></div>
    </form></Modal>}
    {notice && <button className="toast" onClick={() => setNotice("")}>{notice}</button>}
  </main>;
}

function flattenTree(items: DepartmentRecord[]) {
  const result: Array<{ item: DepartmentRecord; depth: number }> = [];
  const visit = (parent: string | null, depth: number) => items.filter((item) => item.parent_id === parent).forEach((item) => { result.push({ item, depth }); visit(item.id, depth + 1); });
  visit(null, 0);
  return result;
}
