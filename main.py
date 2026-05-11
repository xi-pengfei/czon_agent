#!/usr/bin/env python3
"""
czon Agent 统一入口

子命令：
  python main.py                       # 交互式 REPL
  python main.py "消息内容"             # 单次执行并退出
  python main.py webui                 # 启动 WebUI（默认端口 8000）
  python main.py setup                 # 初始化示例数据（sample.db）
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

# 加载 .env
load_dotenv()

_qdrant_start_attempted = False


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
    from core.tools import ToolPolicy, ToolRegistry
    from tools_builtin import file_ops, shell, skill_ops, vector_store

    # 如果有 provider 覆盖（WebUI 切换模型用）
    if provider_override:
        config = {**config, "active_provider": provider_override}

    llm = make_llm_from_config(config)

    skills_cfg = config.get("skills", {})
    skills_dir = Path(skills_cfg.get("dir", "./skills"))
    enabled = skills_cfg.get("enabled")  # None = 全部

    skill_loader = SkillLoader(skills_dir=skills_dir, enabled=enabled)
    skill_loader.scan()

    workspace_dir = config.get("workspace", {}).get("dir", "./workspace")

    tool_policy = ToolPolicy(config.get("tool_policy", {}))
    registry = ToolRegistry(policy=tool_policy)
    file_ops.register(registry, workspace_dir=workspace_dir)
    shell.register(registry)
    skill_ops.register(registry, skill_loader)
    vector_store.register(registry)

    agent_cfg = config.get("agent", {})
    max_iter = agent_cfg.get("max_iterations", 15)
    extra_rules = [
        _render_rule(rule, workspace_dir)
        for rule in (agent_cfg.get("extra_rules") or [])
    ]
    return Agent(
        llm=llm,
        skill_loader=skill_loader,
        tool_registry=registry,
        max_iterations=max_iter,
        extra_rules=extra_rules,
    )


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


def ensure_qdrant_running(config: dict):
    global _qdrant_start_attempted

    qdrant_cfg = config.get("qdrant") or {}
    if not qdrant_cfg.get("auto_start", True):
        return

    url = str(qdrant_cfg.get("url", "http://localhost:6333")).rstrip("/")
    if _qdrant_healthy(url):
        return
    if _qdrant_start_attempted:
        print(f"[警告] Qdrant 仍未通过健康检查，已跳过重复启动：{url}")
        return

    bin_path = Path(os.path.expanduser(str(qdrant_cfg.get("bin", "./.runtime/qdrant/bin/qdrant"))))
    if not bin_path.is_absolute():
        bin_path = Path.cwd() / bin_path
    bin_path = bin_path.resolve()
    if not bin_path.exists():
        print(f"[警告] Qdrant 未运行，且未找到可执行文件：{bin_path}")
        print("       请先运行：bash scripts/install_qdrant.sh")
        return

    data_dir = Path(str(qdrant_cfg.get("data_dir", "./data/qdrant"))).expanduser()
    if not data_dir.is_absolute():
        data_dir = Path.cwd() / data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    log_path = data_dir / "qdrant.log"
    log_file = open(log_path, "ab")
    try:
        subprocess.Popen(
            [str(bin_path)],
            cwd=str(data_dir),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        _qdrant_start_attempted = True
    finally:
        log_file.close()

    for _ in range(20):
        if _qdrant_healthy(url):
            print(f"[Qdrant] 已启动：{url}，数据目录：{data_dir}")
            return
        time.sleep(0.5)

    print(f"[警告] Qdrant 启动后健康检查未通过，日志：{log_path}")


def _qdrant_healthy(url: str) -> bool:
    try:
        import requests
        response = requests.get(f"{url}/healthz", timeout=1)
        return response.ok and "passed" in response.text.lower()
    except Exception:
        return False


def cmd_cli(config: dict, message: Optional[str] = None):
    """CLI 模式"""
    from adapters.cli import run_interactive, run_once

    ensure_qdrant_running(config)
    agent = build_agent(config)

    if message:
        run_once(agent, message)
    else:
        run_interactive(agent)


def cmd_webui(config: dict, args):
    """WebUI 模式"""
    import uvicorn
    from adapters.server import create_app

    ensure_qdrant_running(config)

    webui_cfg = config.get("webui", {})
    host = webui_cfg.get("host", "127.0.0.1")
    port = webui_cfg.get("port", 8000)

    def agent_factory(provider: str):
        webui_rules = config.get("webui", {}).get("extra_rules") or []
        merged_config = {
            **config,
            "agent": {
                **(config.get("agent") or {}),
                "extra_rules": [
                    *((config.get("agent") or {}).get("extra_rules") or []),
                    *webui_rules,
                ],
            },
        }
        return build_agent(merged_config, provider_override=provider)

    workspace_dir = config.get("workspace", {}).get("dir", "./workspace")
    app = create_app(agent_factory, workspace_dir=workspace_dir)
    print(f"czon Agent WebUI 启动中：http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


def _render_rule(rule, workspace_dir: str) -> str:
    return str(rule).replace("{workspace_dir}", workspace_dir.rstrip("/"))


def main():
    parser = argparse.ArgumentParser(
        prog="czon-agent",
        description="czon Agent — 极简 Python Agent Runtime",
    )
    parser.add_argument("command_or_message", nargs="?", help="webui / setup / 或直接输入消息")
    parser.add_argument("message_parts", nargs=argparse.REMAINDER, help="消息剩余内容")

    args = parser.parse_args()

    # 初始化日志
    from core.logging_setup import setup_logging
    import logging
    debug = "--debug" in sys.argv
    setup_logging(level=logging.DEBUG if debug else logging.INFO)

    config = load_config()

    command = args.command_or_message
    if command == "setup":
        cmd_setup(config)
    elif command == "webui":
        cmd_webui(config, args)
    elif command:
        message = " ".join([command] + args.message_parts).strip()
        cmd_cli(config, message=message)
    else:
        cmd_cli(config)


if __name__ == "__main__":
    main()
