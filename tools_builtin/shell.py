"""
内置工具：bash（执行 shell 命令）
"""
import logging
import subprocess

logger = logging.getLogger(__name__)

_MAX_OUTPUT = 10_000


def run_bash(command: str, timeout: int = 60) -> str:
    """
    执行 shell 命令，返回 stdout + stderr。
    返回格式：[exit_code=N]\\nSTDOUT:\\n...\\nSTDERR:\\n...
    """
    logger.info(f"执行 bash 命令：{command[:200]}")
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        output = f"[exit_code={proc.returncode}]\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        if len(output) > _MAX_OUTPUT:
            output = output[:_MAX_OUTPUT] + f"\n\n[输出已截断，只显示前 {_MAX_OUTPUT} 字符]"
        return output
    except subprocess.TimeoutExpired:
        logger.error(f"命令超时（{timeout}s）：{command[:100]}")
        return f"[error] 命令执行超时（{timeout} 秒）：{command[:100]}"
    except Exception as e:
        logger.error(f"bash 执行出错：{e}")
        return f"[error] bash 执行出错：{e}"


def register(registry):
    """向 ToolRegistry 注册 bash 工具"""
    registry.register(
        name="bash",
        description="Execute a shell command. Use this to run skill scripts, curl APIs, install packages, or any command-line operation. Returns stdout+stderr, truncated to 10,000 chars.",
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
