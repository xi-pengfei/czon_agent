import tempfile
import unittest
import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from adapters.server import create_app
from core.auth_store import AuthStore, DEFAULT_ROLES
from core.session_store import SessionStore


class DummyAgent:
    def run(self, text, **kwargs):
        return "ok", []


class ProbeResponse:
    def __init__(self, payload=None, lines=None):
        self.payload = payload or {}
        self.lines = lines or []

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload

    def iter_lines(self):
        return iter(self.lines)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ProbeClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, *args, **kwargs):
        return ProbeResponse({"data": [{"id": "qwen3:8b"}]})

    def post(self, *args, json=None, **kwargs):
        if json and json.get("tools"):
            return ProbeResponse({"choices": [{"message": {"tool_calls": [{"function": {"name": "czon_probe", "arguments": "{}"}}]}}]})
        return ProbeResponse({"choices": [{"message": {"content": "OK"}}]})

    def stream(self, *args, **kwargs):
        return ProbeResponse(lines=['data: {"choices":[{"delta":{"content":"OK"}}]}', "data: [DONE]"])


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "app.db"
        self.store = AuthStore(self.db)
        self.store.seed_roles(DEFAULT_ROLES)
        self.store.create_user("admin", "StrongPassword123", "administrator", must_change=False)
        app = create_app(
            lambda provider, owner: DummyAgent(),
            workspace_dir=self.temp.name,
            project_root=Path(__file__).resolve().parents[1],
            session_db_path=self.db,
            auth_store=self.store,
        )
        self.client = TestClient(app)

    def tearDown(self):
        self.temp.cleanup()

    def login(self):
        return self.client.post("/api/auth/login", json={"username": "admin", "password": "StrongPassword123"})

    def test_api_requires_login(self):
        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_login_sets_secure_cookie_properties_and_returns_csrf(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=strict", response.headers["set-cookie"])
        self.assertNotIn("Max-Age", response.headers["set-cookie"])
        csrf = response.json()["csrf_token"]
        self.assertTrue(response.json()["is_admin"])
        me = self.client.get("/api/me")
        self.assertEqual(me.json()["username"], "admin")
        self.assertEqual(me.json()["csrf_token"], csrf)

    def test_session_expires_after_idle_timeout(self):
        response = self.login()
        token = response.cookies.get("czon_agent_session")
        stale = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "UPDATE app_login_sessions SET last_seen_at=? WHERE token_hash=?",
                (stale, hashlib.sha256(token.encode()).hexdigest()),
            )
        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_mutation_requires_csrf(self):
        csrf = self.login().json()["csrf_token"]
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 403)
        self.assertEqual(
            self.client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code,
            200,
        )

    def test_initial_password_must_be_changed(self):
        self.store.create_user("new_admin", "InitialPassword123", "administrator", must_change=True)
        client = TestClient(self.client.app)
        login = client.post("/api/auth/login", json={"username": "new_admin", "password": "InitialPassword123"})
        csrf = login.json()["csrf_token"]
        self.assertEqual(client.get("/api/sessions").status_code, 403)
        self.assertEqual(client.get("/download/result.txt").status_code, 403)
        changed = client.post(
            "/api/auth/change-password",
            headers={"X-CSRF-Token": csrf},
            json={"old_password": "InitialPassword123", "new_password": "ChangedPassword456"},
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(client.get("/api/me").status_code, 401)

    def test_six_character_password_without_composition_rules_is_allowed(self):
        csrf = self.login().json()["csrf_token"]
        created = self.client.post(
            "/api/admin/users",
            headers={"X-CSRF-Token": csrf},
            json={"username": "simple_user", "password": "123456", "role": "standard"},
        )
        self.assertEqual(created.status_code, 200)

    def test_admin_can_manage_users_roles_and_models(self):
        csrf = self.login().json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}
        role = {
            "name": "finance", "skills": ["invoice-ocr"],
            "tools": ["read", "activate_skill"], "models": ["qwen"], "is_admin": False,
        }
        self.assertEqual(self.client.put("/api/admin/roles/finance", headers=headers, json=role).status_code, 200)
        chinese_role = {
            "name": "运营主管", "skills": ["pledgebox-dianxiaomi-export"],
            "tools": "*", "models": ["deepseek", "kimi"], "is_admin": False,
        }
        self.assertEqual(
            self.client.put("/api/admin/roles/运营主管", headers=headers, json=chinese_role).status_code,
            200,
        )
        created = self.client.post("/api/admin/users", headers=headers, json={
            "username": "finance_01", "password": "FinancePassword123", "role": "finance",
        })
        self.assertEqual(created.status_code, 200)
        model = {
            "name": "internal", "display_name": "Internal", "base_url": "http://llm.internal/v1",
            "model": "chat", "api_key": "test-private-model-key",
            "supports_vision": False, "enabled": True,
        }
        self.assertEqual(self.client.put("/api/admin/models/internal", headers=headers, json=model).status_code, 200)
        disabled_model = {**model, "api_key": None, "enabled": False}
        self.assertEqual(
            self.client.put("/api/admin/models/internal", headers=headers, json=disabled_model).status_code,
            200,
        )
        self.assertTrue(any(item["username"] == "finance_01" for item in self.client.get("/api/admin/users").json()["users"]))
        models_response = self.client.get("/api/admin/models")
        self.assertNotIn("test-private-model-key", models_response.text)
        self.assertNotIn("api_key_env", models_response.text)
        saved_model = next(item for item in models_response.json()["models"] if item["name"] == "internal")
        self.assertTrue(saved_model["api_key_configured"])
        self.assertFalse(saved_model["enabled"])
        self.assertGreaterEqual(len(self.client.get("/api/admin/audit").json()["audit"]), 3)
        self.assertEqual(self.client.get("/api/admin/logs").status_code, 200)

        invalid = {**disabled_model, "api_key_configured": True}
        invalid_response = self.client.put("/api/admin/models/internal", headers=headers, json=invalid)
        self.assertEqual(invalid_response.status_code, 422)
        self.assertEqual(invalid_response.json()["detail"], "API Key 配置状态是只读字段，不应提交")

        user = TestClient(self.client.app)
        user.post("/api/auth/login", json={"username": "finance_01", "password": "FinancePassword123"})
        self.assertEqual(user.get("/api/admin/users").status_code, 403)

    def test_model_probe_checks_chat_streaming_and_tools(self):
        csrf = self.login().json()["csrf_token"]
        with patch("adapters.server.httpx.Client", ProbeClient):
            response = self.client.post(
                "/api/admin/models/probe",
                headers={"X-CSRF-Token": csrf},
                json={
                    "base_url": "http://127.0.0.1:11434/v1",
                    "model": "qwen3:8b",
                    "api_key": "ollama",
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["models"], ["qwen3:8b"])
        self.assertTrue(payload["ok"])
        self.assertTrue(all(payload["checks"][key]["ok"] for key in ("models", "chat", "streaming", "tools")))

    def test_model_probe_lists_models_before_one_is_selected(self):
        csrf = self.login().json()["csrf_token"]
        with patch("adapters.server.httpx.Client", ProbeClient):
            response = self.client.post(
                "/api/admin/models/probe",
                headers={"X-CSRF-Token": csrf},
                json={"base_url": "http://127.0.0.1:11434/v1", "api_key": "ollama"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["checks"]["models"]["ok"])
        self.assertIsNone(response.json()["checks"]["chat"]["ok"])

    def test_admin_can_manage_department_tree_and_million_token_quotas(self):
        csrf = self.login().json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}
        department = {
            "id": "sales", "name": "销售部", "parent_id": "root",
            "monthly_token_quota_million": 2.5, "active": True,
        }
        self.assertEqual(self.client.put("/api/admin/departments/sales", headers=headers, json=department).status_code, 200)
        frontend_payload = {
            "id": "strategy", "name": "战略客户部", "parent_id": "root",
            "monthly_token_quota_million": None, "active": True,
        }
        response = self.client.put("/api/admin/departments/strategy", headers=headers, json=frontend_payload)
        self.assertEqual(response.status_code, 200, response.text)
        created = self.client.post("/api/admin/users", headers=headers, json={
            "username": "sales_user", "password": "123456", "role": "standard",
            "department_id": "sales", "monthly_token_quota_million": None,
        })
        self.assertEqual(created.status_code, 200)
        user = next(item for item in self.client.get("/api/admin/users").json()["users"] if item["username"] == "sales_user")
        self.assertEqual(user["department_name"], "销售部")
        self.assertEqual(user["effective_token_quota_million"], 2.5)
        self.assertEqual(self.client.put(
            "/api/admin/users/sales_user", headers=headers,
            json={"role": "standard", "active": True},
        ).status_code, 200)
        user = next(item for item in self.client.get("/api/admin/users").json()["users"] if item["username"] == "sales_user")
        self.assertEqual(user["department_id"], "sales")

        sessions = SessionStore(self.db)
        sessions.append_exchange("7" * 32, "sales_user", "hello", "done", "usage", metrics={"input_tokens": 700_000, "output_tokens": 300_000})
        user = next(item for item in self.client.get("/api/admin/users").json()["users"] if item["username"] == "sales_user")
        self.assertEqual(user["usage_tokens"], 1_000_000)

        department["parent_id"] = "sales"
        self.assertEqual(self.client.put("/api/admin/departments/sales", headers=headers, json=department).status_code, 400)


if __name__ == "__main__":
    unittest.main()
