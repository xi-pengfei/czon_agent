import { LanguagePicker } from "./LanguagePicker";
import { t } from "../i18n";
import { useState, type FormEvent } from "react";
import { ArrowRight } from "lucide-react";
import { api, setCsrfToken } from "../api";
import type { Identity } from "../types";
import { AssistantAvatar } from "./AssistantAvatar";
import { Brand } from "./Brand";

type Props = {
  identity: Identity | null;
  setupRequired: boolean;
  setupCode: string | null;
  onAuthenticated: (identity: Identity | null) => void;
};

export function AuthView({ identity, setupRequired, setupCode, onAuthenticated }: Props) {
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
      setError(exception instanceof Error ? exception.message : t("登录失败"));
    } finally { setBusy(false); }
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true); setError("");
    try {
      const user = await api<Identity>("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ old_password: form.get("old_password"), new_password: form.get("new_password") }),
      });
      setCsrfToken(user.csrf_token);
      onAuthenticated(user);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : t("密码修改失败"));
    } finally { setBusy(false); }
  }

  async function initialize(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") || "");
    const confirmation = String(form.get("password_confirmation") || "");
    if (password !== confirmation) {
      setError(t("两次输入的密码不一致"));
      return;
    }
    setBusy(true); setError("");
    try {
      const user = await api<Identity>("/api/setup/admin", {
        method: "POST",
        body: JSON.stringify({ password, setup_code: setupCode || form.get("setup_code") }),
      });
      setCsrfToken(user.csrf_token);
      onAuthenticated(user);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : t("初始化失败"));
    } finally { setBusy(false); }
  }

  return (
    <main className="auth-page">
      <section className="auth-shell">
        <div className="auth-story">
          <Brand />
          <div className="auth-pillars"><span>{t("私有化部署")}</span><span>{t("企业专属技能")}</span><span>{t("分级权限管理")}</span><span>{t("数据内部闭环")}</span></div>
          <div className="auth-main">
            <div className="auth-copy">
              <h1><strong>{t("数据不出门")}</strong><br /><span>{t("专注自己业务")}</span><strong>{t("的企业级 AI 智能体")}</strong></h1>
              <p>{t("将企业内部的订单、财务、客服、审批等业务流程变成专属技能。私有化部署，按岗位授权使用，让 AI 真正参与企业经营。")}</p>
            </div>
          </div>
          <div className="auth-partner"><span>{t("企业级 AI 智能体合作伙伴")}</span><a href="http://www.czon.cn" target="_blank" rel="noreferrer">{t("陕西知远驭盛科技有限公司")}</a></div>
        </div>
        <section className="auth-card"><LanguagePicker />
          <div className="auth-heading">
            <div className="auth-icon"><AssistantAvatar /></div>
            <div>
              <h2>{setupRequired ? t("设置管理员密码") : changing ? t("设置新密码") : t("企业登录")}</h2>
              {setupRequired && <p>{t("管理员账号为 admin")}</p>}
              {changing && <p>{t("首次登录需要更新临时密码")}</p>}
              {!setupRequired && !changing && <p>{t("登录账号，继续你的工作")}</p>}
            </div>
          </div>
          <form className="auth-form" onSubmit={setupRequired ? initialize : changing ? changePassword : login}>
            {setupRequired && <label>{t("管理员账号")}<input value="admin" disabled /></label>}
            {setupRequired && !setupCode && <label>{t("安装码")}<input name="setup_code" minLength={12} maxLength={12} autoComplete="one-time-code" required /><small>{t("在服务器运行 .venv/bin/python main.py setup-code 查看")}</small></label>}
            {!setupRequired && !changing && <label>{t("账号")}<input name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} placeholder={t("输入你的账号")} required /></label>}
            {changing && <label>{t("临时密码")}<input name="old_password" type="password" autoComplete="current-password" required /></label>}
            <label>{changing ? t("新密码") : t("密码")}<input name={changing ? "new_password" : "password"} type="password" minLength={setupRequired || changing ? 6 : undefined} autoComplete={setupRequired || changing ? "new-password" : "current-password"} placeholder={changing || setupRequired ? t("设置至少 6 位密码") : t("输入密码")} required /></label>
            {setupRequired && <label>{t("确认密码")}<input name="password_confirmation" type="password" minLength={6} autoComplete="new-password" required /></label>}
            {error && <div className="form-error" role="alert">{error}</div>}
            <button className="primary-button" disabled={busy}>{busy ? t("请稍候") : setupRequired ? t("设置并进入系统") : changing ? t("更新并进入系统") : t("登录")}<ArrowRight size={16} /></button>
          </form>
        </section>
      </section>
    </main>
  );
}
