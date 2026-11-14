"""Run the delivery/isolation contract with native auth instead of browser cookies."""
from tests import test_runs


class NativeRunTests(test_runs.RunTests):
    def setUp(self):
        super().setUp()
        response = self.client.post('/api/auth/mobile/login', json={
            'username': 'alice', 'password': 'Password12345',
        })
        self.client.cookies.clear()
        self.client.headers['Authorization'] = 'Bearer ' + response.json()['session_token']
        self.headers = {'X-CSRF-Token': response.json()['csrf_token']}
