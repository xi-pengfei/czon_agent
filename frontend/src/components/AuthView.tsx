import { useState, type FormEvent } from "react";
import { ArrowRight } from "lucide-react";
import { api, setCsrfToken } from "../api";
import type { Identity } from "../types";
import { AssistantAvatar } from "./AssistantAvatar";
import { Brand } from "./Brand";

type Props = {
  identity: Identity | null;
  onAuthenticated: (identity: Identity | null) => void;
};

export function AuthView({ identity, onAuthenticated }: Props) {
  const changing = Boolean(identity?.must_change_password);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true); setError("");
    try {
      const user = await api<Identity>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: form.get("username"), password: form.get("password") }),
      });
      setCsrfToken(user.csrf_token);
      onAuthenticated(user);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "登录失败");
    } finally { setBusy(false); }
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true); setError("");
    try {
      await api("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ old_password: form.get("old_password"), new_password: form.get("new_password") }),
      });
      setCsrfToken("");
      onAuthenticated(null);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "密码修改失败");
    } finally { setBusy(false); }
  }

  return (
    <main className="auth-page">
      <section className="auth-shell">
        <div className="auth-story">
          <Brand />
          <div className="auth-pillars"><span>私有化部署</span><span>企业专属技能</span><span>分级权限管理</span><span>数据内部闭环</span></div>
          <div className="auth-main">
            <div className="auth-copy">
              <h1><strong>数据不出门</strong><br /><span>专注自己业务</span><strong>的企业级 AI 智能体</strong></h1>
              <p>将企业内部的订单、财务、客服、审批等业务流程变成专属技能。私有化部署，按岗位授权使用，让 AI 真正参与企业经营。</p>
            </div>
          </div>
          <div className="auth-partner"><span>企业级 AI 智能体合作伙伴</span><a href="http://www.czon.cn" target="_blank" rel="noreferrer">陕西知远驭盛科技有限公司</a></div>
        </div>
        <section className="auth-card">
          <div className="auth-heading">
            <div className="auth-icon"><AssistantAvatar /></div>
            <div><h2>{changing ? "设置新密码" : "企业登录"}</h2>{changing && <p>首次登录需要更新临时密码</p>}</div>
          </div>
          <form className="auth-form" onSubmit={changing ? changePassword : login}>
            {!changing && <label>账号<input name="username" autoComplete="username" autoFocus required /></label>}
            {changing && <label>临时密码<input name="old_password" type="password" autoComplete="current-password" autoFocus required /></label>}
            <label>{changing ? "新密码" : "密码"}<input name={changing ? "new_password" : "password"} type="password" minLength={changing ? 6 : undefined} autoComplete={changing ? "new-password" : "current-password"} required /></label>
            {error && <div className="form-error">{error}</div>}
            <button className="primary-button" disabled={busy}>{busy ? "请稍候" : changing ? "更新并重新登录" : "登录"}<ArrowRight size={16} /></button>
          </form>
        </section>
      </section>
    </main>
  );
}
