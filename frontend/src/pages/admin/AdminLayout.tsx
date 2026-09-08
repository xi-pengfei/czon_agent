import { NavLink, Outlet } from "react-router-dom";
import type { Identity } from "../../types";
import { Brand } from "../../components/Brand";

const navigation = [
  { to: "/admin/users", label: "用户管理" },
  { to: "/admin/departments", label: "组织架构" },
  { to: "/admin/roles", label: "角色权限" },
  { to: "/admin/models", label: "模型配置" },
  { to: "/admin/logs", label: "日志中心" },
];

export function AdminLayout({ identity }: { identity: Identity }) {
  return (
    <div className="admin-app">
      <aside className="admin-sidebar">
        <div className="admin-brand"><Brand /></div>
        <nav>{navigation.map((item) => <NavLink to={item.to} key={item.to}>{item.label}</NavLink>)}</nav>
        <a className="back-link" href="/">返回智能体</a>
      </aside>
      <section className="admin-workspace">
        <header className="admin-topbar"><div><strong>系统管理</strong><span>配置仅对管理员开放</span></div><div className="admin-account">{identity.username}<span>{identity.role}</span></div></header>
        <Outlet />
      </section>
    </div>
  );
}
