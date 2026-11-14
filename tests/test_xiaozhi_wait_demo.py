import asyncio
import unittest
from unittest.mock import patch
from adapters.xiaozhi_wait_demo import WaitDemo


class WaitDemoTests(unittest.IsolatedAsyncioTestCase):
    async def test_sequence_finishes_and_duplicate_start_keeps_task(self):
        clock = [100.0]
        async def advance(seconds):
            clock[0] += seconds
        with patch('adapters.xiaozhi_wait_demo.time.monotonic', side_effect=lambda: clock[0]), patch('adapters.xiaozhi_wait_demo.asyncio.sleep', side_effect=advance):
            demo = WaitDemo()
            first = await demo.poll()
            self.assertEqual((await demo.poll())['task_id'], first['task_id'])
            for elapsed, status in [(10, 'running'), (20, 'running'), (25, 'completed')]:
                result = await demo.poll(first['task_id'])
                self.assertEqual(result['elapsed_seconds'], elapsed)
                self.assertEqual(result['status'], status)
            self.assertEqual((await demo.poll(first['task_id']))['status'], 'completed')
            self.assertEqual((await demo.poll('wrong'))['status'], 'error')

    async def test_wait_does_not_block_event_loop(self):
        demo = WaitDemo()
        first = await demo.poll()
        task = asyncio.create_task(demo.poll(first['task_id']))
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        self.assertEqual((await demo.poll(first['task_id']))['status'], 'busy')
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(demo.lock.locked())
