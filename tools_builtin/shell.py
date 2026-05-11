"""
内置工具：bash（执行 shell 命令）
"""
import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_OUTPUT = 10_000

# 项目根目录：tools_builtin/ 的上一级，与项目名称无关
_ROOT_DIR = Path(__file__).resolve().parent.parent


def run_bash(command: str, timeout: int = 60) -> dict:
    """
    执行 shell 命令，返回结构化结果。
    bash 进程始终以项目根目录作为工作目录启动，
    skill 脚本可直接使用相对路径（如 skills/xxx/scripts/xxx.py），
    命令内部的 cd 仍可自由切换到任意目录。
    """
    logger.info(f"执行 bash 命令：{command[:200]}")
    sqlite_block = _bare_sqlite_db_target(command)
    if sqlite_block:
        return {
            "command": command,
            "exit_code": 2,
            "stdout": "",
            "stderr": (
                f"安全限制：禁止使用裸 SQLite 数据库路径 '{sqlite_block}'，"
                "请使用明确目录路径，例如 data/sample.db，或通过 sqlite-sample skill 的 query.py 查询。"
            ),
            "timed_out": False,
            "truncated": False,
        }
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_ROOT_DIR,   # 确保 bash 始终从项目根目录启动
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        stdout, stdout_truncated = _truncate(stdout)
        stderr, stderr_truncated = _truncate(stderr)
        return {
            "command": command,
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": False,
            "truncated": stdout_truncated or stderr_truncated,
        }
    except subprocess.TimeoutExpired:
        logger.error(f"命令超时（{timeout}s）：{command[:100]}")
        return {
            "command": command,
            "exit_code": None,
            "stdout": "",
            "stderr": f"命令执行超时（{timeout} 秒）",
            "timed_out": True,
            "truncated": False,
        }
    except Exception as e:
        logger.error(f"bash 执行出错：{e}")
        return {
            "command": command,
            "exit_code": None,
            "stdout": "",
            "stderr": f"bash 执行出错：{e}",
            "timed_out": False,
            "truncated": False,
        }


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= _MAX_OUTPUT:
        return text, False
    return text[:_MAX_OUTPUT] + f"\n\n[输出已截断，只显示前 {_MAX_OUTPUT} 字符]", True


def _bare_sqlite_db_target(command: str) -> str | None:
    """Block sqlite3 sample.db-style commands that create DB files in project root."""
    pattern = r"(?:^|[;&|]\s*|\s)sqlite3\s+(?:-[^\s]+\s+)*(?P<quote>['\"]?)(?P<db>[^'\"\s;&|]+\.db)(?P=quote)"
    for match in re.finditer(pattern, command):
        db_path = match.group("db")
        if db_path.startswith(("/", "~", "./", "../", "file:")) or "/" in db_path:
            continue
        return db_path
    return None


def register(registry):
    """向 ToolRegistry 注册 bash 工具"""
    registry.register(
        name="bash",
        description="Execute a shell command. Use this to inspect files, run skill scripts, query databases, or perform command-line operations. Returns structured exit_code/stdout/stderr, truncated to 10,000 chars per stream.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "default": 60, "description": "Timeout in seconds"},
            },
            "required": ["command"],
        },
        handler=run_bash,
    )
