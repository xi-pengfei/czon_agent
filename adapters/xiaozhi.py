"""Optional Xiaozhi MCP adapter; business behavior remains in the existing Skills."""
import asyncio
import json
import logging
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from core.auth_store import AuthStore
from core.session_store import SessionStore

VOICE_RULE = ('当前入口是小智语音业务助手。按已有 Skills 执行业务，不额外增加草稿或确认流程；'
              'Skill 本身要求确认则遵守。缺必填信息才追问。最终回复使用简短中文口语，'
              '先说结果，保留单号、数量、单据状态等关键事实，不输出表格、代码、内部日志。'
              '执行结果不确定时明确说明，不得宣称成功或自行重复提交。')


class BusinessService:
    def __init__(self, config, root, factory):
        self.config, self.root, self.factory = config, Path(root), factory
        settings = config.get('xiaozhi') or {}
        self.username = str(settings.get('username') or 'admin').strip() or 'admin'
        self.provider = str(os.environ.get('CZON_ACTIVE_PROVIDER') or settings.get('provider') or config.get('active_provider') or '').strip()
        db = self.path((config.get('webui') or {}).get('session_db', './data/czon_agent.db'))
        self.auth = AuthStore(db)
        self.sessions = SessionStore(db)
        self.lock = threading.Lock()
        self.conversations = set()
        self.active_started = None
        self.select_provider(self.access())

    def path(self, value):
        path = Path(value)
        return path if path.is_absolute() else self.root / path

    def access(self):
        access = self.auth.get_access(self.username)
        if access is None:
            raise RuntimeError('小智绑定账号不存在或已禁用')
        return SimpleNamespace(**access)

    def select_provider(self, access):
        models = [item['name'] for item in self.auth.list_models()
                  if item['api_key_configured']
                  and (access.models == '*' or item['name'] in access.models)]
        if self.provider:
            if self.provider not in models:
                raise RuntimeError('指定模型不可用或绑定账号没有权限，请检查系统模型配置')
            return self.provider
        if not models:
            raise RuntimeError('没有可用模型，请先在系统模型配置中配置模型并授予绑定账号权限')
        return models[0]

    def execute(self, message: str, conversation_id: str = '') -> dict:
        if not message.strip() or len(message) > 12000:
            raise ValueError('业务请求不能为空且不能超过 12000 字符')
        if not self.lock.acquire(blocking=False):
            elapsed = int(time.monotonic() - self.active_started) if self.active_started is not None else 0
            logging.getLogger(__name__).info('小智请求未执行：busy active_elapsed=%ss', elapsed)
            return {'status': 'busy', 'summary': f'上一项任务仍在执行，已等待{elapsed}秒。本次请求尚未执行。',
                    'active_elapsed_seconds': elapsed, 'request_started': False}
        self.active_started = time.monotonic()
        try:
            access = self.access()  # Recheck revocation on every call.
            if conversation_id and conversation_id not in self.conversations:
                raise ValueError('会话无效，请开启新的小智会话')
            sid = conversation_id or 'xiaozhi-' + uuid.uuid4().hex
            skills = dict(self.config.get('skills') or {})
            from core.skills import SkillLoader
            loader = SkillLoader(self.path(skills.get('dir', './skills')), enabled=skills.get('enabled'))
            loader.scan()
            settings = self.auth.list_skill_settings()
            skills.update(dir=str(loader.skills_dir), enabled=[n for n in loader.catalog if settings.get(n, {}).get('enabled', True)])
            cfg = {**self.config, 'current_user': self.username, 'current_access': access,
                   'skills': skills,
                   'workspace': {'dir': str(self.path((self.config.get('workspace') or {}).get('dir', './workspace')))},
                   'agent': {**self.config.get('agent', {}), 'extra_rules': [*self.config.get('agent', {}).get('extra_rules', []), VOICE_RULE]}}
            agent = self.factory(cfg, provider_override=self.select_provider(access))
            history = self.sessions.get_messages(sid, self.username, 40)
            started = time.monotonic()
            try:
                logging.getLogger(__name__).info('小智请求开始 session=%s', sid)
                reply, _ = agent.run(message, history=history)
                logging.getLogger(__name__).info('小智请求结束 session=%s duration=%.1fs', sid, time.monotonic()-started)
                status = 'completed'  # Conversation completed; not a claim of business success.
            except Exception as exc:
                logging.getLogger(__name__).error('小智业务执行异常：%s', type(exc).__name__)
                reply = '本次处理异常，业务是否完成需要核实，请勿重复创建单据。'
                status = 'unknown'
            self.sessions.append_exchange(sid, self.username, message, reply,
                title='[小智] ' + message[:40],
                metrics={**agent.last_usage, 'duration_ms': int((time.monotonic()-started)*1000)})
            self.conversations.add(sid)
            return {'status': status, 'summary': reply, 'conversation_id': sid}
        finally:
            self.active_started = None
            self.lock.release()


def serve(config, root, factory):
    from mcp.server.fastmcp import FastMCP
    service = BusinessService(config, root, factory)
    server = FastMCP('czon-business')
    from adapters.xiaozhi_wait_demo import WaitDemo
    demo = WaitDemo()

    @server.tool()
    async def business_request(message: str, conversation_id: str = '') -> dict:
        """查询企业业务或按 Skills 创建真实单据。完整转交用户需求；播报返回摘要。
        后续补充信息传回 conversation_id，新业务留空。不得因超时自动重复提交。
        completed 仅代表处理结束，实际业务结果以 summary 为准。
        """
        return await asyncio.to_thread(service.execute, message, conversation_id)

    @server.tool()
    async def wait_demo(task_id: str = '') -> dict:
        """仅在用户明确要求“等待播报测试”时调用。模拟25秒等待，不执行业务。
        首次 task_id 留空；先语音播报 summary，再传回 task_id 继续调用本工具。
        running 时继续，completed 时播报并停止。不要交给 business_request。
        本实验验证小智能否在多次工具调用之间播报，并非真实任务进度。
        """
        return await demo.poll(task_id)

    server.run(transport='stdio')


async def bridge(endpoint):
    from websockets.asyncio.client import connect
    # Keep the worker alive across reconnects: never restart an in-flight operation.
    process = await asyncio.create_subprocess_exec(sys.executable, 'main.py', 'xiaozhi-stdio',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
    try:
        async def outgoing(ws):
            while line := await process.stdout.readline():
                await ws.send(line.decode())
            raise RuntimeError('MCP worker exited')

        async def incoming(ws):
            async for message in ws:
                # Only accept a single JSON-RPC message per WebSocket frame.
                payload = json.loads(message)
                process.stdin.write((json.dumps(payload) + '\n').encode())
                await process.stdin.drain()

        delay = 1
        while process.returncode is None:
            try:
                async with connect(endpoint, max_size=2**20) as ws:
                    print('小智 MCP 已连接', file=sys.stderr)
                    delay = 1
                    tasks = [asyncio.create_task(outgoing(ws)), asyncio.create_task(incoming(ws))]
                    try:
                        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for task in done:
                            task.result()
                    finally:
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
            except Exception:
                if process.returncode is not None:
                    raise RuntimeError('小智 MCP 工作进程已退出，请检查配置') from None
                print('小智连接断开，准备重连；不会重发业务请求', file=sys.stderr)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
    finally:
        if process.returncode is None:
            process.terminate()
        await process.wait()


def run(config, root, factory):
    BusinessService(config, root, factory)  # Fail fast before opening a connection.
    endpoint = os.environ.get('XIAOZHI_MCP_ENDPOINT', '')
    if not endpoint.startswith('wss://'):
        raise RuntimeError('请在 .env 设置 XIAOZHI_MCP_ENDPOINT=wss://...')
    try:
        asyncio.run(bridge(endpoint))
    except KeyboardInterrupt:
        pass
