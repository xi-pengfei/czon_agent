import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { api, setCsrfToken } from "./api";
import { AuthView } from "./components/AuthView";
import { ChatPage } from "./pages/ChatPage";
import { AdminLayout } from "./pages/admin/AdminLayout";
import { UsersPage } from "./pages/admin/UsersPage";
import { RolesPage } from "./pages/admin/RolesPage";
import { ModelsPage } from "./pages/admin/ModelsPage";
import { LogsPage } from "./pages/admin/LogsPage";
import { DepartmentsPage } from "./pages/admin/DepartmentsPage";
import type { Identity } from "./types";

export default function App() {
  const [identity, setIdentity] = useState<Identity | null | undefined>(undefined);

  useEffect(() => {
    api<Identity>("/api/me", { cache: "no-store" })
      .then((value) => {
        setCsrfToken(value.csrf_token);
        setIdentity(value);
      })
      .catch(() => setIdentity(null));
  }, []);

  if (identity === undefined) return <div className="boot-screen"><span className="spinner" /></div>;
  if (!identity || identity.must_change_password) {
    return <AuthView identity={identity} onAuthenticated={setIdentity} />;
  }

  return (
    <Routes>
      <Route path="/" element={<ChatPage identity={identity} onLogout={() => setIdentity(null)} />} />
      {identity.is_admin && (
        <Route path="/admin" element={<AdminLayout identity={identity} />}>
          <Route index element={<Navigate to="users" replace />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="departments" element={<DepartmentsPage />} />
          <Route path="roles" element={<RolesPage />} />
          <Route path="models" element={<ModelsPage />} />
          <Route path="logs" element={<LogsPage />} />
        </Route>
      )}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
