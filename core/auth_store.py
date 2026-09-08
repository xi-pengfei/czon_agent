"""Application users, roles, login sessions, and audit records."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_ROLES = {
    "administrator": {"skills": "*", "tools": "*", "models": "*", "is_admin": True},
    "standard": {"skills": "*", "tools": "*", "models": "*", "is_admin": False},
}
SESSION_IDLE_MINUTES = 30


def _now():
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, n, r, p, salt, expected = encoded.split("$")
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


class AuthStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._cipher = Fernet(self._load_or_create_key())
        self._lock = threading.Lock()
        self._initialize()

    def _load_or_create_key(self) -> bytes:
        key_path = self.db_path.with_suffix(".key")
        try:
            return key_path.read_bytes().strip()
        except FileNotFoundError:
            key = Fernet.generate_key()
            try:
                descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as output:
                    output.write(key)
                return key
            except FileExistsError:
                return key_path.read_bytes().strip()

    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS app_roles (
                    name TEXT PRIMARY KEY, skills TEXT NOT NULL, tools TEXT NOT NULL,
                    models TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS app_departments (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    parent_id TEXT REFERENCES app_departments(id),
                    monthly_token_quota_million REAL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS app_users (
                    username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
                    role TEXT NOT NULL REFERENCES app_roles(name), active INTEGER NOT NULL DEFAULT 1,
                    department_id TEXT REFERENCES app_departments(id),
                    monthly_token_quota_million REAL,
                    must_change_password INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL, last_login_at TEXT
                );
                CREATE TABLE IF NOT EXISTS app_login_sessions (
                    token_hash TEXT PRIMARY KEY, username TEXT NOT NULL REFERENCES app_users(username) ON DELETE CASCADE,
                    csrf_token TEXT NOT NULL, created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL, expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS app_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL,
                    action TEXT NOT NULL, target TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS app_models (
                    name TEXT PRIMARY KEY, display_name TEXT NOT NULL, base_url TEXT NOT NULL,
                    model TEXT NOT NULL, api_key_ciphertext TEXT NOT NULL DEFAULT '',
                    supports_vision INTEGER NOT NULL DEFAULT 0,
                    supports_tools INTEGER NOT NULL DEFAULT 1,
                    supports_streaming INTEGER NOT NULL DEFAULT 1,
                    enabled INTEGER NOT NULL DEFAULT 1
                );
            """)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(app_models)")}
            if "api_key_ciphertext" not in columns:
                connection.execute("ALTER TABLE app_models ADD COLUMN api_key_ciphertext TEXT NOT NULL DEFAULT ''")
            if "supports_tools" not in columns:
                connection.execute("ALTER TABLE app_models ADD COLUMN supports_tools INTEGER NOT NULL DEFAULT 1")
            if "supports_streaming" not in columns:
                connection.execute("ALTER TABLE app_models ADD COLUMN supports_streaming INTEGER NOT NULL DEFAULT 1")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(app_models)")}
            if "api_key_env" in columns:
                connection.executescript("""
                    DROP TABLE IF EXISTS app_models_without_env;
                    CREATE TABLE app_models_without_env (
                        name TEXT PRIMARY KEY, display_name TEXT NOT NULL, base_url TEXT NOT NULL,
                        model TEXT NOT NULL, api_key_ciphertext TEXT NOT NULL DEFAULT '',
                        supports_vision INTEGER NOT NULL DEFAULT 0,
                        supports_tools INTEGER NOT NULL DEFAULT 1,
                        supports_streaming INTEGER NOT NULL DEFAULT 1,
                        enabled INTEGER NOT NULL DEFAULT 1
                    );
                    INSERT INTO app_models_without_env
                        (name,display_name,base_url,model,api_key_ciphertext,supports_vision,
                         supports_tools,supports_streaming,enabled)
                    SELECT name,display_name,base_url,model,api_key_ciphertext,supports_vision,
                           supports_tools,supports_streaming,enabled FROM app_models;
                    DROP TABLE app_models;
                    ALTER TABLE app_models_without_env RENAME TO app_models;
                """)
            session_columns = {row[1] for row in connection.execute("PRAGMA table_info(app_login_sessions)")}
            session_policy_migrated = False
            if "created_at" not in session_columns:
                connection.execute("ALTER TABLE app_login_sessions ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
                session_policy_migrated = True
            if "last_seen_at" not in session_columns:
                connection.execute("ALTER TABLE app_login_sessions ADD COLUMN last_seen_at TEXT NOT NULL DEFAULT ''")
                session_policy_migrated = True
            timestamp = _now().isoformat()
            if session_policy_migrated:
                connection.execute("DELETE FROM app_login_sessions")
            user_columns = {row[1] for row in connection.execute("PRAGMA table_info(app_users)")}
            if "department_id" not in user_columns:
                connection.execute("ALTER TABLE app_users ADD COLUMN department_id TEXT")
            if "monthly_token_quota_million" not in user_columns:
                connection.execute("ALTER TABLE app_users ADD COLUMN monthly_token_quota_million REAL")
            connection.execute(
                """INSERT OR IGNORE INTO app_departments
                   (id,name,parent_id,monthly_token_quota_million,active,created_at)
                   VALUES('root','总公司',NULL,NULL,1,?)""",
                (timestamp,),
            )
            connection.execute("UPDATE app_users SET department_id='root' WHERE department_id IS NULL")

    def seed_roles(self, roles: dict):
        with self._lock, self._connect() as connection:
            for name, cfg in roles.items():
                connection.execute(
                    "INSERT OR IGNORE INTO app_roles(name, skills, tools, models, is_admin) VALUES(?,?,?,?,?)",
                    (name, json.dumps(cfg.get("skills", "*")), json.dumps(cfg.get("tools", "*")),
                     json.dumps(cfg.get("models", "*")), int(bool(cfg.get("is_admin")))),
                )

    def seed_models(self, models: dict):
        with self._lock, self._connect() as connection:
            for name, cfg in models.items():
                connection.execute(
                    """INSERT OR IGNORE INTO app_models
                       (name,display_name,base_url,model,supports_vision,enabled)
                       VALUES(?,?,?,?,?,1)""",
                    (name, cfg.get("display_name", name), cfg["base_url"], cfg["model"],
                     int(cfg.get("supports_vision", False))),
                )

    def has_users(self) -> bool:
        with self._connect() as connection:
            return connection.execute("SELECT 1 FROM app_users LIMIT 1").fetchone() is not None

    def create_user(
        self, username: str, password: str, role: str, must_change=True, actor="system",
        department_id: str | None = "root", monthly_token_quota_million: float | None = None,
    ):
        timestamp = _now().isoformat(timespec="seconds")
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO app_users
                   (username,password_hash,role,department_id,monthly_token_quota_million,must_change_password,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (username, hash_password(password), role, department_id, monthly_token_quota_million,
                 int(must_change), timestamp),
            )
            connection.execute(
                "INSERT INTO app_audit_log(actor,action,target,created_at) VALUES(?,?,?,?)",
                (actor, "create_user", username, timestamp),
            )

    def authenticate(self, username: str, password: str):
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT username,password_hash,role,active,must_change_password FROM app_users WHERE username=?",
                (username,),
            ).fetchone()
            if not row or not row["active"] or not verify_password(password, row["password_hash"]):
                return None
            connection.execute("UPDATE app_users SET last_login_at=? WHERE username=?", (_now().isoformat(), username))
        return dict(row)

    def create_session(self, username: str, hours=8):
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        now = _now()
        expires = (now + timedelta(hours=hours)).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM app_login_sessions WHERE expires_at < ?", (now.isoformat(),))
            connection.execute(
                """INSERT INTO app_login_sessions
                   (token_hash,username,csrf_token,created_at,last_seen_at,expires_at)
                   VALUES(?,?,?,?,?,?)""",
                (hashlib.sha256(token.encode()).hexdigest(), username, csrf,
                 now.isoformat(), now.isoformat(), expires),
            )
        return token, csrf

    def get_session(self, token: str):
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._lock, self._connect() as connection:
            row = connection.execute("""
                SELECT u.username,u.role,u.must_change_password,r.is_admin,s.csrf_token,
                       s.last_seen_at,s.expires_at
                FROM app_login_sessions s JOIN app_users u ON u.username=s.username
                JOIN app_roles r ON r.name=u.role
                WHERE s.token_hash=? AND u.active=1
            """, (token_hash,)).fetchone()
            if not row:
                return None
            now = _now()
            idle_deadline = datetime.fromisoformat(row["last_seen_at"]) + timedelta(minutes=SESSION_IDLE_MINUTES)
            if datetime.fromisoformat(row["expires_at"]) <= now or idle_deadline <= now:
                connection.execute("DELETE FROM app_login_sessions WHERE token_hash=?", (token_hash,))
                return None
            connection.execute(
                "UPDATE app_login_sessions SET last_seen_at=? WHERE token_hash=?",
                (now.isoformat(), token_hash),
            )
            return dict(row)

    def delete_session(self, token: str):
        if not token:
            return
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM app_login_sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def change_password(self, username: str, old_password: str, new_password: str):
        if not self.authenticate(username, old_password):
            return False
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE app_users SET password_hash=?,must_change_password=0 WHERE username=?",
                (hash_password(new_password), username),
            )
            connection.execute("DELETE FROM app_login_sessions WHERE username=?", (username,))
        return True

    def get_access(self, username: str):
        with self._connect() as connection:
            row = connection.execute("""
                SELECT u.role,r.skills,r.tools,r.models,r.is_admin FROM app_users u
                JOIN app_roles r ON r.name=u.role WHERE u.username=? AND u.active=1
            """, (username,)).fetchone()
        if not row:
            return None
        result = dict(row)
        for field in ("skills", "tools", "models"):
            result[field] = json.loads(result[field])
        return result

    def list_users(self):
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT u.username,u.role,u.active,u.department_id,u.monthly_token_quota_million,
                          u.must_change_password,u.created_at,u.last_login_at,d.name AS department_name,
                          d.monthly_token_quota_million AS department_token_quota_million
                   FROM app_users u LEFT JOIN app_departments d ON d.id=u.department_id
                   ORDER BY u.username"""
            ).fetchall()
            usage = {}
            try:
                month_start = _now().strftime("%Y-%m-01T00:00:00+00:00")
                usage = {
                    row["owner"]: int(row["tokens"] or 0)
                    for row in connection.execute(
                        """SELECT s.owner, SUM(COALESCE(m.input_tokens,0)+COALESCE(m.output_tokens,0)) AS tokens
                           FROM chat_messages m JOIN chat_sessions s ON s.id=m.session_id
                           WHERE m.role='assistant' AND m.created_at>=? GROUP BY s.owner""",
                        (month_start,),
                    )
                }
            except sqlite3.OperationalError:
                pass
        result = []
        for row in rows:
            item = dict(row)
            item["usage_tokens"] = usage.get(item["username"], 0)
            department_quota = item.pop("department_token_quota_million")
            item["effective_token_quota_million"] = (
                item["monthly_token_quota_million"]
                if item["monthly_token_quota_million"] is not None
                else department_quota
            )
            result.append(item)
        return result

    def update_user(
        self, username: str, role: str, active: bool, actor: str,
        department_id: str | None = None, monthly_token_quota_million: float | None = None,
    ):
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """UPDATE app_users SET role=?,active=?,department_id=?,monthly_token_quota_million=?
                   WHERE username=?""",
                (role, int(active), department_id, monthly_token_quota_million, username),
            )
            if not cursor.rowcount:
                return False
            if not active:
                connection.execute("DELETE FROM app_login_sessions WHERE username=?", (username,))
            self._audit(connection, actor, "update_user", username)
        return True

    def list_departments(self):
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT d.id,d.name,d.parent_id,d.monthly_token_quota_million,d.active,d.created_at,
                          COUNT(u.username) AS user_count
                   FROM app_departments d LEFT JOIN app_users u ON u.department_id=d.id
                   GROUP BY d.id ORDER BY d.created_at,d.name"""
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_department(self, item: dict, actor: str):
        department_id = item["id"]
        parent_id = item.get("parent_id")
        if parent_id == department_id:
            raise ValueError("部门不能属于自身")
        with self._lock, self._connect() as connection:
            if parent_id and not connection.execute("SELECT 1 FROM app_departments WHERE id=?", (parent_id,)).fetchone():
                raise ValueError("上级部门不存在")
            current = parent_id
            while current:
                if current == department_id:
                    raise ValueError("部门层级不能形成循环")
                row = connection.execute("SELECT parent_id FROM app_departments WHERE id=?", (current,)).fetchone()
                current = row["parent_id"] if row else None
            connection.execute(
                """INSERT INTO app_departments(id,name,parent_id,monthly_token_quota_million,active,created_at)
                   VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                   parent_id=excluded.parent_id,monthly_token_quota_million=excluded.monthly_token_quota_million,
                   active=excluded.active""",
                (department_id, item["name"], parent_id, item.get("monthly_token_quota_million"),
                 int(item.get("active", True)), _now().isoformat(timespec="seconds")),
            )
            self._audit(connection, actor, "upsert_department", department_id)

    def reset_password(self, username: str, password: str, actor: str):
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE app_users SET password_hash=?,must_change_password=1 WHERE username=?",
                (hash_password(password), username),
            )
            if not cursor.rowcount:
                return False
            connection.execute("DELETE FROM app_login_sessions WHERE username=?", (username,))
            self._audit(connection, actor, "reset_password", username)
        return True

    def list_roles(self):
        with self._connect() as connection:
            rows = connection.execute("SELECT name,skills,tools,models,is_admin FROM app_roles ORDER BY name").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            for field in ("skills", "tools", "models"):
                item[field] = json.loads(item[field])
            result.append(item)
        return result

    def upsert_role(self, name: str, skills, tools, models, is_admin: bool, actor: str):
        with self._lock, self._connect() as connection:
            connection.execute("""INSERT INTO app_roles(name,skills,tools,models,is_admin) VALUES(?,?,?,?,?)
                ON CONFLICT(name) DO UPDATE SET skills=excluded.skills,tools=excluded.tools,
                models=excluded.models,is_admin=excluded.is_admin""",
                (name, json.dumps(skills), json.dumps(tools), json.dumps(models), int(is_admin)))
            self._audit(connection, actor, "upsert_role", name)

    def list_models(self, include_disabled=False):
        sql = """SELECT name,display_name,base_url,model,api_key_ciphertext,
                 supports_vision,supports_tools,supports_streaming,enabled FROM app_models"""
        if not include_disabled:
            sql += " WHERE enabled=1"
        with self._connect() as connection:
            rows = connection.execute(sql + " ORDER BY name").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            ciphertext = item.pop("api_key_ciphertext", "")
            item["api_key_configured"] = bool(ciphertext)
            result.append(item)
        return result

    def get_model_api_key(self, name: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT api_key_ciphertext FROM app_models WHERE name=? AND enabled=1", (name,)
            ).fetchone()
        if not row:
            return ""
        if row["api_key_ciphertext"]:
            try:
                return self._cipher.decrypt(row["api_key_ciphertext"].encode()).decode()
            except (InvalidToken, UnicodeDecodeError):
                return ""
        return ""

    def upsert_model(self, item: dict, actor: str):
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT api_key_ciphertext FROM app_models WHERE name=?", (item["name"],)
            ).fetchone()
            ciphertext = existing["api_key_ciphertext"] if existing else ""
            if item.get("api_key"):
                ciphertext = self._cipher.encrypt(item["api_key"].encode()).decode()
            connection.execute("""INSERT INTO app_models(name,display_name,base_url,model,api_key_ciphertext,supports_vision,supports_tools,supports_streaming,enabled)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET display_name=excluded.display_name,
                base_url=excluded.base_url,model=excluded.model,
                api_key_ciphertext=excluded.api_key_ciphertext,supports_vision=excluded.supports_vision,
                supports_tools=excluded.supports_tools,supports_streaming=excluded.supports_streaming,enabled=excluded.enabled""",
                (item["name"], item["display_name"], item["base_url"], item["model"], ciphertext,
                 int(item["supports_vision"]), int(item.get("supports_tools", True)),
                 int(item.get("supports_streaming", True)), int(item["enabled"])))
            self._audit(connection, actor, "upsert_model", item["name"])

    def list_audit(self, limit=200):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT actor,action,target,created_at FROM app_audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def record_audit(self, actor: str, action: str, target: str):
        with self._lock, self._connect() as connection:
            self._audit(connection, actor, action, target)

    @staticmethod
    def _audit(connection, actor, action, target):
        connection.execute(
            "INSERT INTO app_audit_log(actor,action,target,created_at) VALUES(?,?,?,?)",
            (actor, action, target, _now().isoformat(timespec="seconds")),
        )
