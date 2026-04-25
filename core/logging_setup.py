"""
日志初始化：同时输出到文件（纯文本）和 stdout（rich 彩色）
格式：[时间] [级别] [模块] 内容
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

from rich.logging import RichHandler


def setup_logging(log_dir: str = "logs", level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    if getattr(root, "_czon_logging_configured", False):
        for handler in root.handlers:
            handler.setLevel(level)
        return

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = log_path / f"agent-{date_str}.log"

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件 handler（纯文本）
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # stdout handler（rich 彩色）
    rich_handler = RichHandler(
        rich_tracebacks=True,
        show_path=False,
        markup=False,
    )
    rich_handler.setLevel(level)

    root.addHandler(file_handler)
    root.addHandler(rich_handler)
    root._czon_logging_configured = True
