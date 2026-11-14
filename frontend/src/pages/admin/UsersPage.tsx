import { t } from "../../i18n";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { KeyRound, Plus, UserRoundCog } from "lucide-react";
import { api, formatTime } from "../../api";
import { Modal } from "../../components/Modal";
import type { DepartmentRecord, RoleRecord, UserRecord } from "../../types";
import { EmptyTable, PageHeader, SearchBox, Toggle } from "./AdminParts";

export function UsersPage() {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [departments, setDepartments] = useState<DepartmentRecord[]>([]);
  const [search, setSearch] = useState("");
  const [dialog, setDialog] = useState<"create" | "reset" | null>(null);
  const [selected, setSelected] = useState<UserRecord | null>(null);
  const [notice, setNotice] = useState("");
  const filtered = useMemo(() => users.filter((user) => `${user.username} ${user.role}`.toLowerCase().includes(search.toLowerCase())), [users, search]);

  async function load() {
    const [userData, roleData, departmentData] = await Promise.all([api<{ users: UserRecord[] }>("/api/admin/users"), api<{ roles: RoleRecord[] }>("/api/admin/roles"), api<{ departments: DepartmentRecord[] }>("/api/admin/departments")]);
    setUsers(userData.users); setRoles(roleData.roles); setDepartments(departmentData.departments);
  }
  useEffect(() => { void load(); }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const quota = String(form.get("monthly_token_quota_million") || "").trim();
    const values = { username: form.get("username"), password: form.get("password"), role: form.get("role"), department_id: form.get("department_id") || null, monthly_token_quota_million: quota ? Number(quota) : null };
    try { await api("/api/admin/users", { method: "POST", body: JSON.stringify(values) }); setDialog(null); setNotice(t("用户已创建")); await load(); }
    catch (error) { setNotice((error as Error).message); }
  }

  async function update(user: UserRecord, changes: Partial<UserRecord>) {
    try { await api(`/api/admin/users/${encodeURIComponent(user.username)}`, { method: "PUT", body: JSON.stringify({ role: changes.role ?? user.role, active: changes.active ?? user.active, department_id: changes.department_id !== undefined ? changes.department_id : user.department_id || null, monthly_token_quota_million: changes.monthly_token_quota_million !== undefined ? changes.monthly_token_quota_million : user.monthly_token_quota_million ?? null }) }); await load(); }
    catch (error) { setNotice((error as Error).message); }
  }

  async function reset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected) return;
    const password = new FormData(event.currentTarget).get("password");
    try { await api(`/api/admin/users/${encodeURIComponent(selected.username)}/reset-password`, { method: "POST", body: JSON.stringify({ password }) }); setDialog(null); setNotice(t("临时密码已更新")); await load(); }
    catch (error) { setNotice((error as Error).message); }
  }

  return <main className="admin-content">
    <PageHeader title={t("用户管理")} description={t("创建账号，分配部门、角色与 Token 额度")} action={<button className="primary-button compact" onClick={() => setDialog("create")}><Plus size={16} />{t("创建用户")}</button>} />
    <div className="table-toolbar"><SearchBox value={search} onChange={setSearch} placeholder={t("搜索用户或角色")} /><span>{filtered.length}  {t("个用户")}</span></div>
    <div className="data-table"><table><thead><tr><th>{t("用户")}</th><th>{t("部门")}</th><th>{t("角色")}</th><th>{t("本月用量 / 额度")}</th><th>{t("状态")}</th><th>{t("首次改密")}</th><th>{t("最后登录")}</th><th>{t("操作")}</th></tr></thead><tbody>{filtered.map((user) => <tr key={user.username}>
      <td><div className="identity-cell"><span>{user.username.slice(0, 1).toUpperCase()}</span><strong>{user.username}</strong></div></td>
      <td><select value={user.department_id || ""} onChange={(event) => update(user, { department_id: event.target.value || null })}><option value="">{t("未分配")}</option>{departments.filter((item) => item.active).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></td>
      <td><select value={user.role} onChange={(event) => update(user, { role: event.target.value })}>{roles.map((role) => <option key={role.name}>{role.name}</option>)}</select></td>
      <td><div className="quota-cell"><strong>{formatMillion((user.usage_tokens || 0) / 1_000_000)}</strong><span>/ {user.effective_token_quota_million == null ? t("不限") : formatMillion(user.effective_token_quota_million)}</span><input aria-label={t("用户每月 Token 额度，百万")} type="number" min="0" step="0.1" defaultValue={user.monthly_token_quota_million ?? ""} placeholder={t("继承")} onBlur={(event) => update(user, { monthly_token_quota_million: event.target.value === "" ? null : Number(event.target.value) })} /></div></td>
      <td><Toggle checked={user.active} onChange={(active) => update(user, { active })} label={user.active ? t("启用") : t("禁用")} /></td>
      <td>{user.must_change_password ? <span className="status warning">{t("待修改")}</span> : <span className="status success">{t("正常")}</span>}</td>
      <td>{formatTime(user.last_login_at)}</td>
      <td><button className="text-button" onClick={() => { setSelected(user); setDialog("reset"); }}><KeyRound size={14} />{t("重置密码")}</button></td>
    </tr>)}</tbody></table>{!filtered.length && <EmptyTable text={t("没有匹配的用户")} />}</div>
    {dialog === "create" && <Modal title={t("创建用户")} onClose={() => setDialog(null)}><form className="modal-form" onSubmit={create}><label>{t("用户名")}<input name="username" maxLength={64} placeholder={t("支持中文，例如：张三、财务小王")} required /></label><label>{t("临时密码")}<input name="password" type="password" minLength={6} required /></label><label>{t("所属部门")}<select name="department_id"><option value="">{t("未分配")}</option>{departments.filter((item) => item.active).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label>{t("角色")}<select name="role">{roles.map((role) => <option key={role.name}>{role.name}</option>)}</select></label><label>{t("每月 Token 额度（百万）")}<input name="monthly_token_quota_million" type="number" min="0" step="0.1" placeholder={t("留空则继承部门")} /></label><div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setDialog(null)}>{t("取消")}</button><button className="primary-button"><UserRoundCog size={16} />{t("创建")}</button></div></form></Modal>}
    {dialog === "reset" && selected && <Modal title={t("重置 {{value0}} 的密码", { value0: selected.username })} onClose={() => setDialog(null)}><form className="modal-form" onSubmit={reset}><p className="form-hint">{t("用户下次登录时需要修改此临时密码。")}</p><label>{t("新临时密码")}<input name="password" type="password" minLength={6} autoFocus required /></label><div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setDialog(null)}>{t("取消")}</button><button className="primary-button"><KeyRound size={16} />{t("确认重置")}</button></div></form></Modal>}
    {notice && <button className="toast" onClick={() => setNotice("")}>{notice}</button>}
  </main>;
}

function formatMillion(value: number) { return `${value.toFixed(value < 0.01 ? 3 : 2)} M`; }
