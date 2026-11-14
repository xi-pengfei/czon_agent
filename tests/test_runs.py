"""Concurrency and delivery guarantees without any external models or business tools."""
import json
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from fastapi.testclient import TestClient
from adapters.server import create_app
from core.auth_store import AuthStore, DEFAULT_ROLES
from core.agent import AgentStopped
from core.runs import RunManager


def wait_for(predicate, seconds=3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('condition timed out')


class RunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.started = {}
        self.releases = {}
        self.workspaces = {}
        self.calls = []
        outer = self

        class Agent:
            last_usage = {}
            def __init__(self, workspace):
                self.workspace = Path(workspace)
            def run(self, text, stop_event, on_delta=None, **kwargs):
                release = outer.releases.setdefault(text, threading.Event())
                outer.workspaces[text] = self.workspace
                outer.started.setdefault(text, threading.Event()).set()
                outer.calls.append(text)
                if on_delta:
                    on_delta('第一句话。')
                while not release.wait(.01):
                    if stop_event.is_set():
                        raise AgentStopped()
                (self.workspace / 'result.txt').write_text(text)
                return text, []

        self.auth = AuthStore(self.root / 'db.sqlite')
        self.auth.seed_roles(DEFAULT_ROLES)
        self.auth.create_user('alice', 'Password12345', 'standard', must_change=False)
        self.auth.create_user('bob', 'Password12345', 'standard', must_change=False)
        self.app = create_app(lambda p, o, w: Agent(w), self.auth, project_root=self.root,
                              workspace_dir=self.root / 'workspace', session_db_path=self.root / 'db.sqlite')
        self.client = TestClient(self.app)
        result = self.client.post('/api/auth/login', json={'username': 'alice', 'password': 'Password12345'})
        self.headers = {'X-CSRF-Token': result.json()['csrf_token']}

    def tearDown(self):
        for event in self.releases.values():
            event.set()
        for rid, (_, _, stop) in list(self.app.state.runs.pending.items()):
            run = self.app.state.runs.get(rid)
            self.app.state.runs.stop(rid, run['owner'], run['session_id'])
        self.app.state.runs.close()
        self.temp.cleanup()

    def submit(self, text, sid=None, rid=None):
        payload = {'text': text, 'provider': 'qwen', 'session_id': sid or uuid.uuid4().hex, 'run_id': rid or uuid.uuid4().hex}
        response = self.client.post('/api/runs', headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json(), payload

    def test_three_parallel_runs_and_fourth_waits(self):
        submitted = [self.submit(f'parallel-{i}')[0] for i in range(4)]
        wait_for(lambda: len(self.calls) == 3)
        self.assertEqual(len(self.app.state.runs.running), 3)
        self.assertEqual(self.app.state.runs.get(submitted[3]['id'])['status'], 'queued')
        # A different account also shares the global three-worker limit.
        bob = TestClient(self.app)
        login = bob.post('/api/auth/login', json={'username': 'bob', 'password': 'Password12345'})
        response = bob.post('/api/runs', headers={'X-CSRF-Token': login.json()['csrf_token']},
                            json={'text': 'bob-queued', 'provider': 'qwen', 'session_id': uuid.uuid4().hex, 'run_id': uuid.uuid4().hex})
        self.assertEqual(response.json()['status'], 'queued')
        self.releases['parallel-0'].set()
        wait_for(lambda: 'parallel-3' in self.calls)
        self.assertEqual(len(self.app.state.runs.running), 3)
        self.assertNotIn('bob-queued', self.calls)
        self.releases['parallel-1'].set()
        wait_for(lambda: 'bob-queued' in self.calls)
        self.assertLessEqual(len(self.app.state.runs.running), 3)

    def test_parallel_sessions_queue_and_workspace_artifacts(self):
        a, _ = self.submit('first')
        b, _ = self.submit('second')
        c, _ = self.submit('third', a['session_id'])
        wait_for(lambda: len(self.calls) == 2)
        self.assertEqual(self.app.state.runs.get(c['id'])['status'], 'queued')
        self.assertNotEqual(self.workspaces['first'], self.workspaces['second'])
        self.releases['first'].set()
        wait_for(lambda: 'third' in self.calls)
        self.assertEqual(self.workspaces['first'], self.workspaces['third'])
        for event in self.releases.values(): event.set()
        wait_for(lambda: all(self.app.state.runs.get(r['id'])['status'] == 'completed' for r in [a, b, c]))
        for run, expected in [(a, b'first'), (b, b'second'), (c, b'third')]:
            detail = self.app.state.runs.get(run['id'])
            self.assertEqual(self.client.get(detail['artifacts'][0]['download_url']).content, expected)

    def test_idempotency_and_foreign_account(self):
        a, payload = self.submit('once')
        response = self.client.post('/api/runs', headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 200)
        wait_for(lambda: len(self.calls) == 1)
        self.assertEqual(self.client.post('/api/runs', headers=self.headers, json={**payload, 'text': 'changed'}).status_code, 409)
        bob = TestClient(self.app)
        login = bob.post('/api/auth/login', json={'username': 'bob', 'password': 'Password12345'})
        self.assertEqual(bob.get('/api/runs').json()['runs'], [])
        self.assertEqual(bob.get('/api/runs/' + a['id']).status_code, 404)
        self.assertEqual(bob.get('/api/runs/' + a['id'] + '/events').status_code, 404)
        self.assertEqual(bob.post('/api/chat/stop', headers={'X-CSRF-Token': login.json()['csrf_token']}, json={'run_id': a['id'], 'session_id': a['session_id']}).status_code, 404)
        self.assertEqual(self.app.state.runs.events('bob'), [])

    def test_replay_is_independent_and_stop_only_one_run(self):
        a, _ = self.submit('alpha')
        b, _ = self.submit('beta')
        wait_for(lambda: len(self.calls) == 2)
        self.client.post('/api/chat/stop', headers=self.headers, json={'run_id': a['id'], 'session_id': a['session_id']})
        wait_for(lambda: self.app.state.runs.get(a['id'])['status'] == 'stopped')
        self.assertEqual(self.app.state.runs.get(b['id'])['status'], 'running')
        events = self.app.state.runs.events('alice', run_id=a['id'])
        self.assertEqual(events, self.app.state.runs.events('alice', run_id=a['id']))
        after = events[1]['seq']
        remaining = self.client.get(f"/api/runs/{a['id']}/events", headers={'Last-Event-ID': str(after)}).text
        self.assertNotIn(f"id: {after}\n", remaining)
        self.assertIn('agent_stopped', remaining)
        self.assertEqual(self.client.delete('/api/sessions/' + b['session_id'], headers=self.headers).status_code, 409)

    def test_new_connection_restores_active_run_and_queue_cancel(self):
        a, _ = self.submit('running')
        b, _ = self.submit('queued', a['session_id'])
        wait_for(lambda: 'running' in self.calls)
        snapshot = self.client.get('/api/runs').json()
        self.assertEqual({r['id'] for r in snapshot['runs']}, {a['id'], b['id']})
        self.assertGreater(snapshot['cursor'], 0)
        self.assertIn(a['session_id'], [s['id'] for s in self.client.get('/api/sessions').json()['sessions']])
        self.client.post('/api/chat/stop', headers=self.headers, json={'run_id': b['id'], 'session_id': b['session_id']})
        self.assertEqual(self.app.state.runs.get(b['id'])['status'], 'stopped')
        self.assertNotIn('queued', self.calls)

    def test_submission_does_not_require_subscriber(self):
        a, _ = self.submit('background')
        wait_for(lambda: 'background' in self.calls)
        # No SSE connection has ever been opened.
        self.releases['background'].set()
        wait_for(lambda: self.app.state.runs.get(a['id'])['status'] == 'completed')
        history = self.client.get('/api/sessions/' + a['session_id']).json()['messages']
        self.assertEqual(history[-1]['run_id'], a['id'])
        self.assertEqual(history[-1]['content'], 'background')

    def test_sse_disconnect_does_not_stop_worker(self):
        import socket
        import requests
        import uvicorn
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(self.app, log_level='critical', lifespan='off', timeout_graceful_shutdown=1))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        wait_for(lambda: server.started)
        session = requests.Session()
        try:
            base = f'http://127.0.0.1:{port}'
            login = session.post(base + '/api/auth/login', json={'username': 'alice', 'password': 'Password12345'}, timeout=3).json()
            headers = {'X-CSRF-Token': login['csrf_token']}
            rid, sid = uuid.uuid4().hex, uuid.uuid4().hex
            response = session.post(base + '/api/chat/stream', headers=headers, json={'text': 'disconnect', 'provider': 'qwen', 'run_id': rid, 'session_id': sid}, stream=True, timeout=3)
            lines = response.iter_lines(chunk_size=1)
            for line in lines:
                if b'agent_start' in line:
                    break
            response.close()
            self.assertEqual(self.app.state.runs.get(rid)['status'], 'running')
            # agent_start is published before Agent.run creates its test latch.
            wait_for(lambda: 'disconnect' in self.releases)
            self.releases['disconnect'].set()
            wait_for(lambda: self.app.state.runs.get(rid)['status'] == 'completed')
            replay = session.get(base + f'/api/runs/{rid}/events', timeout=3)
            self.assertIn('agent_done', replay.text)
        finally:
            session.close()
            server.should_exit = True
            thread.join(3)
            sock.close()

    def test_speech_api_uses_auth_csrf_and_provider_adapter(self):
        from unittest.mock import patch
        audio = self.root / 'test.mp3'
        audio.write_bytes(b'test-audio')
        with patch.dict('os.environ', {'CZON_SPEECH_API_KEY': 'test-only'}), \
             patch('core.speech.SpeechService.transcribe', return_value='查询生产进度') as asr, \
             patch('core.speech.SpeechService.synthesize', return_value=audio) as tts:
            response = self.client.post('/api/speech/asr', headers=self.headers, files={'file': ('a.webm', b'test-recording', 'audio/webm')})
            self.assertEqual(response.json()['text'], '查询生产进度')
            self.assertRegex(response.headers['X-Speech-Request-ID'], r'^[0-9a-f]{12}$')
            self.assertIn('speech;dur=', response.headers['Server-Timing'])
            asr.assert_called_once_with('recording.webm', b'test-recording')
            self.assertEqual(self.client.post('/api/speech/asr', headers=self.headers, files={'file': ('a.exe', b'bad')}).status_code, 415)
            self.assertEqual(self.client.post('/api/speech/tts', json={'text': '你好'}).status_code, 403)
            response = self.client.post('/api/speech/tts', headers=self.headers, json={'text': '你好'})
            self.assertEqual(response.content, b'test-audio')
            tts.assert_called_once_with('alice', '你好')

    def test_speech_is_optional_and_authenticated(self):
        self.assertEqual(TestClient(self.app).get('/api/speech/capabilities').status_code, 401)
        from unittest.mock import patch
        with patch.dict('os.environ', {'CZON_SPEECH_API_KEY': ''}):
            self.assertEqual(self.client.get('/api/speech/capabilities').json()['asr'], False)
            self.assertEqual(self.client.post('/api/speech/asr', headers=self.headers, files={'file': ('a.webm', b'data')}).status_code, 503)


class RecoveryTests(unittest.TestCase):
    def test_restart_marks_unknown_never_reexecutes(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = RunManager(Path(temp) / 'runs.db')
            run = {'id': 'a', 'owner': 'alice', 'session_id': 's', 'status': 'running', 'steps': []}
            with manager.connect() as db:
                db.execute('INSERT INTO agent_runs VALUES(?,?,?,?,?)', ('a', 'alice', 's', 'f', json.dumps(run)))
            manager.close()
            recovered = RunManager(Path(temp) / 'runs.db')
            self.assertEqual(recovered.get('a')['status'], 'interrupted')
            self.assertEqual(recovered.running, {})
            self.assertEqual(recovered.events('alice')[-1]['event'], 'agent_interrupted')
            recovered.close()
