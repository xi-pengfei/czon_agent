"""Built-in bash tool with cooperative progress and cancellation."""
import logging
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_OUTPUT = 10_000
_MAX_PROGRESS = 30_000
_HEARTBEAT_SECONDS = 5
_ROOT_DIR = Path(__file__).resolve().parent.parent
_SECRET_RE = re.compile(
    r"(?i)(authorization|api[_-]?key|access[_-]?token|password|secret)(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")


def run_bash(
    command: str,
    timeout: int = 60,
    progress_callback=None,
    stop_event: threading.Event | None = None,
    control_timeout: int | None = None,
    extra_env: dict[str, str] | None = None,
) -> dict:
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        timeout = 60
    if control_timeout is not None:
        timeout = min(timeout, max(1, int(control_timeout)))
    logger.info("执行 bash 命令：%s", _redact(command[:200]))
    process = None
    try:
        process_env = os.environ.copy()
        process_env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{process_env.get('PATH', '')}"
        process_env["PYTHONUNBUFFERED"] = "1"
        process_env.update(extra_env or {})
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_ROOT_DIR,
            bufsize=1,
            start_new_session=True,
            env=process_env,
        )
        output_queue = queue.Queue()
        readers = [
            threading.Thread(target=_read_stream, args=(process.stdout, "stdout", output_queue), daemon=True),
            threading.Thread(target=_read_stream, args=(process.stderr, "stderr", output_queue), daemon=True),
        ]
        for reader in readers:
            reader.start()

        outputs = {"stdout": [], "stderr": []}
        closed_streams = 0
        progress_chars = 0
        progress_truncated = False
        started = time.monotonic()
        timed_out = False
        stopped = False
        last_progress = started

        while closed_streams < 2 or process.poll() is None:
            if stop_event and stop_event.is_set():
                stopped = True
                _terminate_process_group(process)
            if time.monotonic() - started >= timeout:
                timed_out = True
                _terminate_process_group(process)

            try:
                stream_name, line = output_queue.get(timeout=0.1)
            except queue.Empty:
                elapsed = int(time.monotonic() - started)
                if progress_callback and time.monotonic() - last_progress >= _HEARTBEAT_SECONDS:
                    progress_callback({"stream": "stdout", "text": f"[运行] 命令仍在执行，已用时 {elapsed} 秒\n"})
                    last_progress = time.monotonic()
                if stopped or timed_out:
                    break
                continue
            if line is None:
                closed_streams += 1
                continue
            outputs[stream_name].append(line)
            last_progress = time.monotonic()
            if progress_callback and progress_chars < _MAX_PROGRESS:
                safe_line = _redact(line)
                remaining = _MAX_PROGRESS - progress_chars
                chunk = safe_line[:remaining]
                if chunk:
                    progress_callback({"stream": stream_name, "text": chunk})
                    progress_chars += len(chunk)
                if len(safe_line) > remaining and not progress_truncated:
                    progress_callback({"stream": stream_name, "text": "\n[实时输出已截断]\n"})
                    progress_truncated = True

        if process.poll() is None:
            _terminate_process_group(process)
        return_code = process.wait(timeout=3)
        stdout, stdout_truncated = _truncate("".join(outputs["stdout"]))
        stderr, stderr_truncated = _truncate("".join(outputs["stderr"]))
        if timed_out and not stderr:
            stderr = f"命令执行超时（{timeout} 秒）"
        if stopped and not stderr:
            stderr = "命令已由用户停止"
        return {
            "command": _redact(command),
            "exit_code": return_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "stopped": stopped,
            "truncated": stdout_truncated or stderr_truncated or progress_truncated,
        }
    except KeyboardInterrupt:
        if process and process.poll() is None:
            _terminate_process_group(process)
        raise
    except Exception as exc:
        if process and process.poll() is None:
            _terminate_process_group(process)
        logger.error("bash 执行出错：%s", exc)
        return {
            "command": _redact(command),
            "exit_code": None,
            "stdout": "",
            "stderr": f"bash 执行出错：{exc}",
            "timed_out": False,
            "stopped": False,
            "truncated": False,
        }


def _read_stream(stream, stream_name: str, output_queue: queue.Queue) -> None:
    try:
        for line in iter(stream.readline, ""):
            output_queue.put((stream_name, line))
    finally:
        stream.close()
        output_queue.put((stream_name, None))


def _terminate_process_group(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _redact(text: str) -> str:
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    return _SECRET_RE.sub(r"\1\2[REDACTED]", text)


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= _MAX_OUTPUT:
        return text, False
    return text[:_MAX_OUTPUT] + f"\n\n[输出已截断，只显示前 {_MAX_OUTPUT} 字符]", True


def register(registry, active_provider: str = ""):
    def handler(command, timeout=60, progress_callback=None, stop_event=None, control_timeout=None):
        return run_bash(
            command, timeout, progress_callback, stop_event, control_timeout,
            extra_env={"CZON_ACTIVE_PROVIDER": active_provider} if active_provider else None,
        )

    registry.register(
        name="bash",
        description="Execute a shell command in the project runtime. The python/python3 commands resolve to the active virtual environment. Returns structured output and streams progress.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "default": 60, "description": "Timeout in seconds"},
            },
            "required": ["command"],
        },
        handler=handler,
        supports_progress=True,
    )
