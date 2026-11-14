"""Isolated voice-wait experiment. No Agent, API calls, or business mutations."""
import asyncio
import logging
import time
import uuid

logger = logging.getLogger(__name__)


class WaitDemo:
    def __init__(self):
        self.task_id = ''
        self.started = 0.0
        self.lock = asyncio.Lock()

    async def poll(self, task_id: str = '') -> dict:
        if self.lock.locked():
            return {'status': 'busy', 'summary': '已有等待测试调用正在进行，请勿并行调用。'}
        async with self.lock:
            now = time.monotonic()
            if not task_id:
                # Repeated starts during a live demo attach to it instead of restarting.
                if not self.task_id or now - self.started >= 25:
                    self.task_id = uuid.uuid4().hex
                    self.started = now
                    logger.info('等待播报测试开始 task=%s', self.task_id)
                return self.result('running', '开始等待播报测试。这次不用跑业务，我陪你等一小会儿。')
            if task_id != self.task_id:
                return {'status': 'error', 'summary': '等待测试编号无效或已失效，请重新开始测试。'}
            remaining = 25 - (now - self.started)
            if remaining > 0:
                await asyncio.sleep(min(10, remaining))
            elapsed = time.monotonic() - self.started
            if elapsed >= 25:
                return self.result('completed', '等待测试结束。刚才只是模拟等待，没有执行任何业务。')
            phrase = ('这次是模拟等待，你负责提问，我负责跑腿。' if elapsed < 20
                      else '这道应用题还没交卷。别着急，测试还在继续。')
            return self.result('running', phrase)

    def result(self, status, summary):
        elapsed = round(time.monotonic() - self.started, 1)
        logger.info('等待播报测试返回 task=%s status=%s elapsed=%.1f', self.task_id, status, elapsed)
        result = {'status': status, 'task_id': self.task_id, 'summary': summary,
                  'elapsed_seconds': elapsed, 'simulation': True}
        if status == 'running':
            result['next_action'] = '先用语音播报 summary，再调用 wait_demo 并传回 task_id；不要调用 business_request。'
        else:
            result['next_action'] = '播报 summary，停止查询。'
        return result
