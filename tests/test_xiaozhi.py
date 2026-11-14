import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from adapters.xiaozhi import BusinessService


class XiaozhiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.auth = patch('adapters.xiaozhi.AuthStore').start()
        self.addCleanup(patch.stopall)
        self.auth.return_value.get_access.return_value = dict(skills='*', tools='*', models='*')
        self.auth.return_value.list_skill_settings.return_value = {}
        self.auth.return_value.list_models.return_value = [{'name': 'existing', 'api_key_configured': True}]
        env = patch.dict('os.environ', {}, clear=True)
        env.start()
        self.agent = Mock(last_usage={'input_tokens': 1, 'output_tokens': 2})
        self.agent.run.return_value = ('已创建入库单 RK001，未审核。', [])
        self.factory = Mock(return_value=self.agent)
        self.service = BusinessService({'xiaozhi': {'username': 'robot'}}, Path(self.tmp.name), self.factory)

    def test_history_and_account(self):
        first = self.service.execute('创建入库单')
        self.service.execute('查询状态', first['conversation_id'])
        self.assertEqual(len(self.agent.run.call_args.kwargs['history']), 2)
        self.assertEqual(self.factory.call_args.args[0]['current_user'], 'robot')
        self.assertTrue(first['conversation_id'].startswith('xiaozhi-'))

    def test_web_session_rejected(self):
        with self.assertRaises(ValueError):
            self.service.execute('继续', 'web-session')
        self.agent.run.assert_not_called()

    def test_revoked_account(self):
        self.auth.return_value.get_access.return_value = None
        with self.assertRaises(RuntimeError):
            self.service.execute('创建')
        self.agent.run.assert_not_called()

    def test_failure_is_not_retried(self):
        self.agent.run.side_effect = TimeoutError()
        result = self.service.execute('创建')
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(self.agent.run.call_count, 1)

    def test_busy(self):
        self.service.lock.acquire()
        try:
            result = self.service.execute('创建')
            self.assertEqual(result['status'], 'busy')
            self.assertFalse(result['request_started'])
            self.agent.run.assert_not_called()
        finally:
            self.service.lock.release()

    def test_default_admin_and_existing_model(self):
        service = BusinessService({}, Path(self.tmp.name), self.factory)
        service.execute('查询')
        self.assertEqual(service.username, 'admin')
        self.assertEqual(self.factory.call_args.kwargs['provider_override'], 'existing')

    def test_no_model(self):
        self.auth.return_value.list_models.return_value = []
        with self.assertRaises(RuntimeError):
            self.service.execute('查询')

    def test_model_permission(self):
        self.auth.return_value.get_access.return_value['models'] = []
        with self.assertRaises(RuntimeError):
            self.service.execute('查询')
