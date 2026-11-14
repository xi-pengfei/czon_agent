"""Native bearer sessions must preserve existing WebUI access rules."""
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from adapters.server import create_app
from core.auth_store import AuthStore, DEFAULT_ROLES


class MobileAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db = Path(self.tmp.name) / 'test.db'
        self.auth = AuthStore(db)
        self.auth.seed_roles(DEFAULT_ROLES)
        self.auth.create_user('mobile', 'Password123', 'standard', must_change=False)
        self.client = TestClient(create_app(lambda *args: None, workspace_dir=self.tmp.name,
            project_root=Path(__file__).resolve().parents[1], session_db_path=db, auth_store=self.auth))

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def login(self, path='/api/auth/mobile/login'):
        r = self.client.post(path, json={'username': 'mobile', 'password': 'Password123'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers['cache-control'], 'no-store')
        self.client.cookies.clear()
        return r.json()

    def test_bearer_requires_csrf_and_is_revoked_on_logout(self):
        auth = self.login()
        headers = {'Authorization': 'Bearer ' + auth['session_token']}
        self.assertEqual(self.client.get('/api/me', headers=headers).status_code, 200)
        self.assertEqual(self.client.post('/api/auth/logout', headers=headers).status_code, 403)
        headers['X-CSRF-Token'] = auth['csrf_token']
        self.assertEqual(self.client.get('/api/admin/users', headers=headers).status_code, 403)
        self.assertEqual(self.client.post('/api/auth/logout', headers=headers).status_code, 200)
        self.assertEqual(self.client.get('/api/me', headers=headers).status_code, 401)

    def test_web_login_does_not_expose_token(self):
        self.assertNotIn('session_token', self.login('/api/auth/login'))

    def test_disabled_user_cannot_use_native_session(self):
        auth = self.login()
        self.auth.update_user('mobile', 'standard', False, 'test')
        self.assertEqual(self.client.get('/api/runs', headers={'Authorization': 'Bearer ' + auth['session_token']}).status_code, 401)

    def test_password_rotation_returns_new_native_token(self):
        auth = self.login()
        headers = {'Authorization': 'Bearer ' + auth['session_token'], 'X-CSRF-Token': auth['csrf_token']}
        r = self.client.post('/api/auth/change-password', headers=headers,
                             json={'old_password': 'Password123', 'new_password': 'NewPassword123'})
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.json()['session_token'], auth['session_token'])
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/me', headers=headers).status_code, 401)
        self.assertEqual(self.client.get('/api/me', headers={'Authorization': 'Bearer ' + r.json()['session_token']}).status_code, 200)

    def test_initial_password_and_foreign_session_are_protected(self):
        self.auth.create_user('initial', 'Password123', 'standard', must_change=True)
        r = self.client.post('/api/auth/mobile/login', json={'username':'initial','password':'Password123'})
        self.client.cookies.clear()
        headers = {'Authorization': 'Bearer ' + r.json()['session_token']}
        self.assertEqual(self.client.get('/api/me', headers=headers).status_code, 200)
        self.assertEqual(self.client.get('/api/runs', headers=headers).status_code, 403)
        auth = self.login()
        headers = {'Authorization': 'Bearer ' + auth['session_token']}
        self.assertEqual(self.client.get('/api/sessions/' + 'a' * 32, headers=headers).status_code, 404)

    def test_invalid_bearer_does_not_fall_back_to_browser_cookie(self):
        self.client.post('/api/auth/login', json={'username':'mobile','password':'Password123'})
        self.assertEqual(self.client.get('/api/me', headers={'Authorization':'Bearer invalid'}).status_code, 401)
        self.assertEqual(self.client.get('/api/me').status_code, 200)
