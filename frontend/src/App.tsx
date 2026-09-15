import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, AUTH_EXPIRED_EVENT, setCsrfToken } from "./api";
import { AuthView } from "./components/AuthView";
import { ChatPage } from "./pages/ChatPage";
import { AdminLayout } from "./pages/admin/AdminLayout";
import { UsersPage } from "./pages/admin/UsersPage";
import { RolesPage } from "./pages/admin/RolesPage";
import { ModelsPage } from "./pages/admin/ModelsPage";
import { LogsPage } from "./pages/admin/LogsPage";
import { DepartmentsPage } from "./pages/admin/DepartmentsPage";
import { SkillsPage } from "./pages/admin/SkillsPage";
import type { Identity } from "./types";

export default function App() {
  const location = useLocation();
  const [identity, setIdentity] = useState<Identity | null | undefined>(undefined);
  const [setupRequired, setSetupRequired] = useState<boolean | undefined>(undefined);
  const [setupCode, setSetupCode] = useState<string | null>(null);
  const [modelRequired, setModelRequired] = useState<boolean | undefined>(false);

  useEffect(() => {
    const handleAuthExpired = () => setIdentity(null);
    window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
    api<Identity>("/api/me", { cache: "no-store" })
      .then((value) => {
        setCsrfToken(value.csrf_token);
        setIdentity(value);
        setSetupRequired(false);
      })
      .catch(async () => {
        setIdentity(null);
        try {
          const status = await api<{ required: boolean; setup_code?: string }>("/api/setup/status", { cache: "no-store" });
          setSetupRequired(status.required);
          setSetupCode(status.setup_code || null);
        } catch {
          setSetupRequired(false);
        }
      });
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
  }, []);

  useEffect(() => {
    if (!identity || identity.must_change_password || !identity.is_admin) {
      setModelRequired(false);
      return;
    }
    setModelRequired(undefined);
    api<{ model_required: boolean }>("/api/setup/status", { cache: "no-store" })
      .then((status) => setModelRequired(status.model_required))
      .catch(() => setModelRequired(false));
  }, [identity]);

  if (identity === undefined || setupRequired === undefined || modelRequired === undefined) return <div className="boot-screen"><span className="spinner" /></div>;
  if (!identity || identity.must_change_password) {
    return <AuthView
      identity={identity}
      setupRequired={setupRequired}
      setupCode={setupCode}
      onAuthenticated={(value) => { setIdentity(value); if (value) setSetupRequired(false); }}
    />;
  }
  if (identity.is_admin && modelRequired && location.pathname !== "/admin/models") {
    return <Navigate to="/admin/models" replace />;
  }

  return (
    <Routes>
      <Route path="/" element={<ChatPage identity={identity} onLogout={() => setIdentity(null)} />} />
      {(identity.is_admin || identity.manage_skills) && (
        <Route path="/admin" element={<AdminLayout identity={identity} />}>
          <Route index element={<Navigate to={identity.is_admin ? "users" : "skills"} replace />} />
          {identity.is_admin && <Route path="users" element={<UsersPage />} />}
          {identity.is_admin && <Route path="departments" element={<DepartmentsPage />} />}
          {identity.is_admin && <Route path="roles" element={<RolesPage />} />}
          {identity.is_admin && <Route path="models" element={<ModelsPage onConfigured={() => setModelRequired(false)} />} />}
          <Route path="skills" element={<SkillsPage />} />
          {identity.is_admin && <Route path="logs" element={<LogsPage />} />}
        </Route>
      )}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
