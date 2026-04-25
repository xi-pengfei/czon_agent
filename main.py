#!/usr/bin/env python3
"""
Mini Agent 统一入口

子命令：
  python main.py cli "消息内容"        # 单次执行并退出
  python main.py cli --interactive     # 交互式 REPL
  python main.py webui                 # 启动 WebUI（默认端口 8000）
  python main.py setup                 # 初始化示例数据（sample.db）
"""
import argparse
import sys
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

# 加载 .env
load_dotenv()


def load_config() -> dict:
    config_path = Path("config.yaml")
    if not config_path.exists():
        print("[警告] config.yaml 不存在，使用默认配置")
        return {}
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_agent(config: dict, provider_override: Optional[str] = None):
    """根据配置构建 Agent 实例"""
    from core.agent import Agent
    from core.llm import make_llm_from_config
    from core.skills import SkillLoader
    from core.tools import ToolRegistry
    from tools_builtin import file_ops, shell, skill_ops

    # 如果有 provider 覆盖（WebUI 切换模型用）
    if provider_override:
        config = {**config, "active_provider": provider_override}

    llm = make_llm_from_config(config)

    skills_cfg = config.get("skills", {})
    skills_dir = Path(skills_cfg.get("dir", "./skills"))
    enabled = skills_cfg.get("enabled")  # None = 全部

    skill_loader = SkillLoader(skills_dir=skills_dir, enabled=enabled)
    skill_loader.scan()

    registry = ToolRegistry()
    file_ops.register(registry)
    shell.register(registry)
    skill_ops.register(registry, skill_loader)

    max_iter = config.get("agent", {}).get("max_iterations", 15)
    return Agent(llm=llm, skill_loader=skill_loader, tool_registry=registry, max_iterations=max_iter)


def cmd_setup(config: dict):
    """初始化示例数据库"""
    print("正在初始化示例数据库…")
    import subprocess
    result = subprocess.run(
        [sys.executable, "data/seed_sample_db.py"],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        sys.exit(1)


def cmd_cli(config: dict, args):
    """CLI 模式"""
    from adapters.cli import run_interactive, run_once

    agent = build_agent(config)

    if args.interactive:
        run_interactive(agent)
    elif args.message:
        run_once(agent, args.message)
    else:
        print("请提供消息内容，或使用 --interactive 进入交互模式。")
        print("示例：python main.py cli '你好，我叫小明'")
        sys.exit(1)


def cmd_webui(config: dict, args):
    """WebUI 模式"""
    import uvicorn
    from adapters.server import create_app

    webui_cfg = config.get("webui", {})
    host = webui_cfg.get("host", "127.0.0.1")
    port = webui_cfg.get("port", 8000)

    def agent_factory(provider: str):
        return build_agent(config, provider_override=provider)

    app = create_app(agent_factory)
    print(f"Mini Agent WebUI 启动中：http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


def main():
    # 检查并自动初始化 sample.db
    if not Path("data/sample.db").exists() and Path("data/seed_sample_db.py").exists():
        import subprocess
        subprocess.run([sys.executable, "data/seed_sample_db.py"], capture_output=True)

    parser = argparse.ArgumentParser(
        prog="mini-agent",
        description="Mini Agent — 极简 Python Agent Runtime",
    )
    subparsers = parser.add_subparsers(dest="command")

    # setup 子命令
    subparsers.add_parser("setup", help="初始化示例数据（sample.db）")

    # cli 子命令
    cli_parser = subparsers.add_parser("cli", help="命令行模式")
    cli_parser.add_argument("message", nargs="?", help="要发送的消息（不填则需要 --interactive）")
    cli_parser.add_argument("--interactive", "-i", action="store_true", help="进入交互式 REPL")

    # webui 子命令
    subparsers.add_parser("webui", help="启动 Web UI（默认）")

    args = parser.parse_args()

    # 未指定子命令时默认启动 webui
    if not args.command:
        args.command = "webui"

    # 初始化日志
    from core.logging_setup import setup_logging
    import logging
    debug = "--debug" in sys.argv
    setup_logging(level=logging.DEBUG if debug else logging.INFO)

    config = load_config()

    if args.command == "setup":
        cmd_setup(config)
    elif args.command == "cli":
        cmd_cli(config, args)
    elif args.command == "webui":
        cmd_webui(config, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
