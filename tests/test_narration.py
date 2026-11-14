import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from core.narration import NarrationService, answer_window, progress_summary, spoken_source
from core.auth_store import AuthStore, DEFAULT_ROLES
from core.speech import SpeechService
from adapters.server import create_app


def sample(**changes):
    return {'id': 'a' * 32, 'owner': 'alice', 'provider': 'test', 'status': 'completed',
            'text': '核对订单', 'reply': '订单共12条，其中2条还需要核实。请不要重复提交。', 'steps': [], **changes}


class NarrationTests(unittest.TestCase):
    def test_summary_is_separate_and_excludes_raw_logs_and_reasoning(self):
        writer = Mock(return_value='查到了12条订单，有2条需要核实，先不要重复提交。')
        run = sample(reply='订单共12条，其中2条还需要核实。\n<think>内部推理</think>\n```bash\nrm -rf secret\n```\n| 单号 | 内容 |\n| private | hidden |\n请不要重复提交。')
        original = run['reply']
        result = NarrationService(writer).prepare('alice', run, 'answer')
        payload = writer.call_args.args[-1]
        for forbidden in ['内部推理', 'rm -rf', '|']:
            self.assertNotIn(forbidden, payload['公开回答片段'])
        self.assertEqual(run['reply'], original)
        self.assertEqual(result['text'], writer.return_value)
        self.assertTrue(result['done'])

    def test_table_facts_reach_editor_without_being_read_as_a_table(self):
        writer = Mock(return_value='共12条，其中2条需要核实。')
        result = NarrationService(writer).prepare('alice', sample(reply='| 合计 | 待核实 |\n| --- | --- |\n| 12 | 2 |'), 'answer')
        self.assertFalse(result['fallback'])
        self.assertIn('12', writer.call_args.args[-1]['公开回答片段'])
        self.assertNotIn('|', result['text'])

    def test_rewrite_failure_does_not_read_raw_answer(self):
        result = NarrationService(Mock(side_effect=TimeoutError())).prepare('alice', sample(reply='SECRET RAW TABLE'), 'answer')
        self.assertTrue(result['fallback']); self.assertNotIn('SECRET', result['text'])

    def test_fabricated_number_is_rejected(self):
        result = NarrationService(Mock(return_value='已成功处理999条订单。')).prepare('alice', sample(), 'answer')
        self.assertTrue(result['fallback'])

    def test_grouped_window_and_final_replacement(self):
        run = sample(status='running', reply='这是一个已经确认的业务结果。' * 60)
        source, offset, anchor, done = answer_window(run, 0, '')
        self.assertGreater(len(source), 100); self.assertGreater(offset, 300); self.assertFalse(done)
        run.update(status='completed', reply='最终结果需要核实，不能宣称成功。')
        source, offset, anchor, done = answer_window(run, offset, anchor)
        self.assertIn('不能宣称成功', source); self.assertTrue(done)
        self.assertEqual(answer_window(run, offset, anchor)[0], '')

    def test_code_fence_remains_filtered_across_windows(self):
        reply = '开始说明。\n```python\n' + 'secret = 1\n' * 100 + '```\n结果尚未确认。'
        source, offset, anchor, _ = answer_window(sample(status='running', reply=reply), 0, '')
        source2, _, _, _ = answer_window(sample(reply=reply), offset, anchor)
        self.assertNotIn('secret', source + source2)
        self.assertIn('结果尚未确认', source2)

    def test_final_long_report_is_bounded_but_keeps_conclusion(self):
        source, offset, _, done = answer_window(sample(reply='报告内容。' * 900 + '重要结论：尚未完成。'), 0, '')
        self.assertLess(len(source), 1500); self.assertIn('尚未完成', source); self.assertTrue(done)
        self.assertGreater(offset, 4000)

    def test_progress_uses_only_real_state_and_no_cloud(self):
        writer = Mock(); service = NarrationService(writer)
        result = service.prepare('alice', sample(status='running', progress='需要确认才能继续', steps=[{'progress':'secret command'}]), 'progress')
        self.assertEqual(result['stage'], 'confirmation'); self.assertNotIn('secret', result['text'])
        writer.assert_not_called()
        self.assertIn('核实', progress_summary(sample(status='failed'))[1])

    def test_same_owner_deduplicates_concurrent_rewrite_other_owner_does_not(self):
        writer = Mock(return_value='有12条订单，其中2条需要核实。')
        service = NarrationService(writer)
        with ThreadPoolExecutor(4) as pool:
            results = list(pool.map(lambda _: service.prepare('alice', sample(), 'answer'), range(4)))
        self.assertEqual(writer.call_count, 1)
        self.assertTrue(all(item['text'] == results[0]['text'] for item in results))
        service.prepare('bob', sample(), 'answer'); self.assertEqual(writer.call_count, 2)

    def test_waiting_hints_share_cache_but_refresh_after_twenty_seconds(self):
        writer = Mock(side_effect=['单据也像拼图，得对上才踏实。', '对账这件事，稳一点更省心。', '数据需要耐心。'])
        service = NarrationService(writer)
        run = sample(status='running', created_at='2026-11-14T00:00:00+00:00', reply='我先核对。',
                     steps=[{'name': 'activate_skill', 'result': {'ok': True}, 'duration_ms': 9},
                            {'name': 'bash', 'args': {'secret': 'private'}}])
        with patch('core.narration.time.time', return_value=1794614400 + 144):
            first = service.prepare('alice', run, 'progress')
            self.assertEqual(first, service.prepare('alice', run, 'progress', previous='另一个设备'))
            self.assertEqual(writer.call_count, 1)
            self.assertIn('2分24秒', first['text'])
            self.assertIn('准备工作已完成', first['text'])
            self.assertNotIn('private', str(writer.call_args))
        with patch('core.narration.time.time', return_value=1794614400 + 165):
            second = service.prepare('alice', run, 'progress')
            self.assertNotEqual(first['hint_id'], second['hint_id'])
            self.assertTrue(writer.call_args.args[-1]['最近提示'])
            service.prepare('bob', run, 'progress')
            self.assertEqual(writer.call_count, 3)

    def test_progress_cache_changes_when_tool_changes_inside_same_time_slot(self):
        service = NarrationService()
        run = sample(status='running', steps=[{'id': 'a', 'name': 'read'}])
        first = service.prepare('alice', run, 'progress')
        run['steps'] = [{'id': 'a', 'name': 'read', 'result': {'ok': True}}, {'id': 'b', 'name': 'write'}]
        second = service.prepare('alice', run, 'progress')
        self.assertIn('读取资料', first['text'])
        self.assertIn('保存文件', second['text'])
        self.assertNotIn('读取资料', second['text'])

    def test_bad_waiting_editor_falls_back_to_facts_and_completed_stays_silent(self):
        writer = Mock(return_value='已成功处理999条，马上就好。')
        service = NarrationService(writer)
        result = service.prepare('alice', sample(status='running', steps=[{'name':'bash'}]), 'progress')
        self.assertTrue(result['fallback'])
        self.assertNotIn('999', result['text'])
        self.assertIn('还没有返回结果', result['text'])
        self.assertEqual(service.prepare('alice', sample(), 'progress')['text'], '')
        self.assertEqual(writer.call_count, 1)

    def test_asr_has_separate_capacity_bounded_timeout_and_private_timing(self):
        with tempfile.TemporaryDirectory() as folder:
            service = SpeechService(Path(folder))
            service.limit.acquire(); service.limit.acquire()
            self.assertTrue(service.asr_limit.acquire(blocking=False))
            service.asr_limit.release(); service.limit.release(); service.limit.release()
            client = Mock()
            client.audio.transcriptions.create.return_value.text = 'PRIVATE recognized words'
            manager = Mock()
            manager.__enter__ = Mock(return_value=client)
            manager.__exit__ = Mock(return_value=False)
            with patch.object(service, 'client', return_value=manager) as factory, self.assertLogs('core.speech', level='INFO') as logs:
                result = service.transcribe('sample.wav', b'PRIVATE audio')
            self.assertEqual(result, 'PRIVATE recognized words')
            self.assertEqual(factory.call_args.kwargs['timeout'].read, 15)
            self.assertEqual(factory.call_args.kwargs['timeout'].connect, 3)
            self.assertIn('asr_upstream', ''.join(logs.output))
            self.assertNotIn('PRIVATE', ''.join(logs.output))

    def test_tts_style_and_cache_follow_provider_and_voice(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {}, clear=True):
            service = SpeechService(Path(folder), {'base_url':'https://api.siliconflow.cn/v1', 'tts_model':'FunAudioLLM/CosyVoice2-0.5B', 'voice':'alex'})
            client = Mock(); client.audio.speech.create.return_value.content = b'fixture'
            context = Mock(); context.__enter__ = Mock(return_value=client); context.__exit__ = Mock(return_value=False)
            with patch.object(service, 'client', return_value=context):
                first = service.synthesize('alice', '任务还需要核实。')
                self.assertIn('<|endofprompt|>', client.audio.speech.create.call_args.kwargs['input'])
                self.assertEqual(service.synthesize('alice', '任务还需要核实。'), first)
                self.assertEqual(client.audio.speech.create.call_count, 1)
                service.options['base_url'] = 'https://other.invalid/v1'
                self.assertNotEqual(service.synthesize('alice', '任务还需要核实。'), first)
                self.assertEqual(client.audio.speech.create.call_args.kwargs['input'], '任务还需要核实。')


class NarrationAuthorizationTests(unittest.TestCase):
    def test_endpoint_owner_csrf_and_model_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); auth = AuthStore(root/'test.db'); auth.seed_roles(DEFAULT_ROLES)
            auth.create_user('alice', 'TestPassword123', 'standard', must_change=False)
            auth.create_user('bob', 'TestPassword123', 'standard', must_change=False)
            writer = Mock(return_value='有12条订单，其中2条需要核实。')
            allowed = [{'name':'test','configured':True}]
            app = create_app(lambda *args: None, auth, project_root=root, workspace_dir=str(root/'work'), session_db_path=root/'test.db', provider_catalog_provider=lambda _: allowed, narration_writer=writer)
            run = sample(session_id='b'*32); done = threading.Event()
            def work(stop, emit):
                emit('agent_done', {'reply':'订单共12条，其中2条还需要核实。'}); done.set()
            with TestClient(app) as client:
                app.state.runs.submit(run, 'test', work, lambda:None); self.assertTrue(done.wait(2))
                endpoint = '/api/runs/' + run['id'] + '/narration'
                self.assertEqual(client.post(endpoint,json={}).status_code,401)
                user = client.post('/api/auth/login',json={'username':'alice','password':'TestPassword123'}).json()
                headers = {'X-CSRF-Token':user['csrf_token']}
                self.assertEqual(client.post(endpoint,json={}).status_code,403)
                response = client.post(endpoint,json={},headers=headers)
                self.assertEqual(response.status_code,200); self.assertIn('12', response.json()['text'])
                allowed.clear()
                self.assertEqual(client.post(endpoint,json={},headers=headers).status_code,403)
                allowed.append({'name':'test','configured':True})
                user = client.post('/api/auth/login',json={'username':'bob','password':'TestPassword123'}).json()
                self.assertEqual(client.post(endpoint,json={},headers={'X-CSRF-Token':user['csrf_token']}).status_code,404)
                self.assertEqual(writer.call_count,1)

if __name__ == '__main__': unittest.main()
