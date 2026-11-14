"""No business calls: exercise actual stdio framing and asynchronous tool dispatch."""
import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from adapters.xiaozhi import serve


class TransportTests(unittest.TestCase):
    def test_logging_keeps_stdout_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            code = ('import logging; from core.logging_setup import setup_logging; '
                    f'setup_logging(log_dir={directory!r}, stderr=True); '
                    'logging.info("test marker"); print("{\\\"jsonrpc\\\":\\\"2.0\\\"}")')
            result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout), {'jsonrpc': '2.0'})
            self.assertIn('test marker', result.stderr)

    def test_business_tool_is_async(self):
        captured = {}
        server = Mock()
        def register():
            def decorator(fn):
                captured[fn.__name__] = fn
                return fn
            return decorator
        server.tool.side_effect = register
        with patch('adapters.xiaozhi.BusinessService') as service, patch('mcp.server.fastmcp.FastMCP', return_value=server):
            service.return_value.execute.return_value = {'summary': 'ok'}
            serve({}, Path('.'), None)
            self.assertTrue(asyncio.iscoroutinefunction(captured['business_request']))
            self.assertEqual(asyncio.run(captured['business_request']('query')), {'summary': 'ok'})
