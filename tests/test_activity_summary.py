import unittest
from unittest.mock import Mock
from core.narration import NarrationService


class ActivitySummaryTests(unittest.TestCase):
    def run_data(self):
        return dict(id='activity-test', owner='alice', provider='test', status='running',
                    text='核对本周单据', reply='我先核对日期范围，再检查审批状态。',
                    steps=[dict(id='step1', name='bash', args={'command':'SECRET'}, progress='SECRET raw log')])

    def test_public_evidence_only_and_cache(self):
        writer = Mock(return_value='本次核对日期范围和审批状态，当前操作还未返回新结果。')
        service = NarrationService(writer)
        run = self.run_data()
        self.assertEqual(service.prepare('alice', run, 'activity')['text'], writer.return_value)
        self.assertNotIn('SECRET', str(writer.call_args))
        service.prepare('alice', run, 'activity')
        self.assertEqual(writer.call_count, 1)
        run['steps'][0]['result'] = {'ok':True}
        service.prepare('alice', run, 'activity')
        self.assertEqual(writer.call_count, 2)
        service.prepare('bob', run, 'activity')
        self.assertEqual(writer.call_count, 3)

    def test_unverified_numbers_fall_back(self):
        result = NarrationService(Mock(return_value='已经核实999条。')).prepare('alice',self.run_data(),'activity')
        self.assertTrue(result['fallback'])
        self.assertNotIn('999',result['text'])
        self.assertIn('尚未返回',result['text'])

    def test_finished_run_does_not_generate(self):
        writer=Mock()
        run=self.run_data();run['status']='completed'
        self.assertTrue(NarrationService(writer).prepare('alice',run,'activity')['done'])
        writer.assert_not_called()
