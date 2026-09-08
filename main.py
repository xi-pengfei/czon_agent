#!/usr/bin/env python3
"""
czon Agent 统一入口

子命令：
  python main.py                       # 交互式 REPL
  python main.py "消息内容"             # 单次执行并退出
  python main.py webui                 # 按 config.yaml 启动 WebUI
  python main.py setup-admin           # 创建首个系统管理员
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
load_dotenv(PROJECT_ROOT / ".env")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise RuntimeError(f"配置文件不存在：{CONFIG_PATH}")
    with CONFIG_PATH.open(encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    if not isinstance(config, dict):
        raise RuntimeError("config.yaml 顶层必须是映射结构")
    return config


def build_agent(config: dict, provider_override: Optional[str] = None):
    """根据配置构建 Agent 实例"""
    from core.access_control import allowed_names
    from core.agent import Agent
    from core.llm import make_llm_from_config
    from core.skills import SkillLoader
    from core.tools import ToolPolicy, ToolRegistry
    from tools_builtin import file_ops, shell, skill_ops

    # 如果有 provider 覆盖（WebUI 切换模型用）
    if provider_override:
        config = {**config, "active_provider": provider_override}
    username = str(config.get("current_user", "cli"))
    access = config.get("current_access")
    if access is None:
        from types import SimpleNamespace
        access = SimpleNamespace(skills="*", tools="*", models="*", role="administrator")
    provider = str(config.get("active_provider", ""))
    if access.models != "*" and provider not in access.models:
        raise RuntimeError(f"用户 '{username}' 没有使用模型 '{provider}' 的权限")

    llm = make_llm_from_config(config, PROJECT_ROOT)

    skills_cfg = config.get("skills", {})
    skills_dir = Path(skills_cfg.get("dir", "./skills"))
    enabled = skills_cfg.get("enabled")  # None = 全部
    enabled = allowed_names(enabled, access.skills)

    skill_loader = SkillLoader(skills_dir=skills_dir, enabled=enabled)
    skill_loader.scan()

    workspace_dir = config.get("workspace", {}).get("dir", "./workspace")

    policy_config = dict(config.get("tool_policy", {}))
    if access.tools != "*":
        known_tools = {"read", "write", "bash", "activate_skill"}
        policy_config["block_tools"] = sorted(
            set(policy_config.get("block_tools") or []) | (known_tools - set(access.tools))
        )
    tool_policy = ToolPolicy(policy_config)
    registry = ToolRegistry(policy=tool_policy)
    file_ops.register(registry, workspace_dir=workspace_dir)
    shell.register(registry, active_provider=provider)
    skill_ops.register(registry, skill_loader)
    agent_cfg = config.get("agent", {})
    extra_rules = [
        _render_rule(rule, workspace_dir)
        for rule in (agent_cfg.get("extra_rules") or [])
    ]
    return Agent(
        llm=llm,
        skill_loader=skill_loader,
        tool_registry=registry,
        max_runtime_seconds=_positive_int(agent_cfg, "max_runtime_seconds"),
        max_consecutive_errors=_positive_int(agent_cfg, "max_consecutive_errors"),
        extra_rules=extra_rules,
    )


def cmd_cli(config: dict, message: Optional[str] = None):
    """CLI 模式"""
    from adapters.cli import run_interactive, run_once

    agent = build_agent(config)

    if message:
        run_once(agent, message)
    else:
        run_interactive(agent)


def cmd_webui(config: dict, args):
    """WebUI 模式"""
    import uvicorn
    from adapters.server import create_app

    webui_cfg = config.get("webui")
    if not isinstance(webui_cfg, dict):
        raise RuntimeError("config.yaml 缺少 webui 配置")
    host = str(webui_cfg["host"]).strip()
    port = _positive_int(webui_cfg, "port")

    from types import SimpleNamespace
    from core.access_control import allowed_names
    from core.auth_store import AuthStore, DEFAULT_ROLES
    from core.llm import DEFAULT_MODELS
    from core.skills import SkillLoader

    session_db = webui_cfg.get("session_db", "./data/czon_agent.db")
    db_path = Path(session_db)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    auth_store = AuthStore(db_path)
    auth_store.seed_roles(DEFAULT_ROLES)
    auth_store.seed_models(DEFAULT_MODELS)

    def access_resolver(username: str):
        access = auth_store.get_access(username)
        if access is None:
            raise RuntimeError("用户不存在或已禁用")
        return SimpleNamespace(**access)

    def agent_factory(provider: str, username: str):
        access = access_resolver(username)
        webui_rules = config.get("webui", {}).get("extra_rules") or []
        merged_config = {
            **config,
            "current_user": username,
            "current_access": access,
            "agent": {
                **(config.get("agent") or {}),
                "extra_rules": [
                    *((config.get("agent") or {}).get("extra_rules") or []),
                    *webui_rules,
                ],
            },
        }
        return build_agent(merged_config, provider_override=provider)

    def skill_catalog_provider(username: str):
        access = access_resolver(username)
        skills_cfg = config.get("skills") or {}
        enabled = allowed_names(skills_cfg.get("enabled"), access.skills)
        loader = SkillLoader(Path(skills_cfg.get("dir", "./skills")), enabled=enabled)
        loader.scan()
        return [
            {"name": meta.name, "description": meta.description}
            for meta in loader.catalog.values()
        ]

    def provider_catalog_provider(username: str):
        access = access_resolver(username)
        providers = {item["name"]: item for item in auth_store.list_models()}
        allowed = providers.keys() if access.models == "*" else access.models
        return [
            {
                "name": name,
                "display_name": providers[name]["display_name"],
                "model": providers[name]["model"],
                "supports_vision": providers[name]["supports_vision"],
                "configured": bool(auth_store.get_model_api_key(name)),
            }
            for name in allowed
            if name in providers
        ]

    workspace_dir = config.get("workspace", {}).get("dir", "./workspace")
    app = create_app(
        agent_factory,
        workspace_dir=workspace_dir,
        project_root=PROJECT_ROOT,
        session_db_path=session_db,
        auth_store=auth_store,
        cookie_secure=bool(webui_cfg.get("cookie_secure", False)),
        skill_catalog_provider=skill_catalog_provider,
        provider_catalog_provider=provider_catalog_provider,
    )
    print(f"czon Agent WebUI 启动中：http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning", server_header=False)


def cmd_setup_admin(config: dict):
    import getpass
    import re
    from core.auth_store import AuthStore, DEFAULT_ROLES
    from core.llm import DEFAULT_MODELS

    webui_cfg = config.get("webui") or {}
    db_path = Path(webui_cfg.get("session_db", "./data/czon_agent.db"))
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    store = AuthStore(db_path)
    store.seed_roles(DEFAULT_ROLES)
    store.seed_models(DEFAULT_MODELS)
    if store.has_users():
        raise RuntimeError("系统中已存在用户，请在管理员页面创建或管理账号")
    username = input("管理员账号 [admin]：").strip() or "admin"
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,64}", username):
        raise RuntimeError("用户名格式不合法")
    password = getpass.getpass("初始密码（至少 6 位）：")
    confirm = getpass.getpass("再次输入密码：")
    if password != confirm:
        raise RuntimeError("两次输入的密码不一致")
    if len(password) < 6:
        raise RuntimeError("密码至少需要 6 位")
    store.create_user(username, password, "administrator", must_change=True)
    print(f"管理员 {username} 已创建，请启动 WebUI 并登录后修改初始密码。")


def _render_rule(rule, workspace_dir: str) -> str:
    return str(rule).replace("{workspace_dir}", workspace_dir.rstrip("/"))


def _positive_int(section: dict, key: str) -> int:
    if key not in section:
        raise RuntimeError(f"config.yaml 缺少配置项：{key}")
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(f"config.yaml 配置项 {key} 必须是正整数")
    return value


def main():
    os.chdir(PROJECT_ROOT)
    parser = argparse.ArgumentParser(
        prog="czon_agent",
        description="czon Agent — 极简 Python Agent Runtime",
    )
    parser.add_argument("command_or_message", nargs="?", help="webui / setup-admin / 或直接输入消息")
    parser.add_argument("message_parts", nargs=argparse.REMAINDER, help="消息剩余内容")

    args = parser.parse_args()

    # 初始化日志
    from core.logging_setup import setup_logging
    import logging
    debug = "--debug" in sys.argv
    setup_logging(level=logging.DEBUG if debug else logging.INFO)

    try:
        config = load_config()
    except (OSError, yaml.YAMLError, RuntimeError, KeyError) as exc:
        print(f"[配置错误] {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        command = args.command_or_message
        if command == "setup-admin":
            cmd_setup_admin(config)
        elif command == "webui":
            cmd_webui(config, args)
        elif command:
            message = " ".join([command] + args.message_parts).strip()
            cmd_cli(config, message=message)
        else:
            cmd_cli(config)
    except (RuntimeError, KeyError) as exc:
        print(f"[启动失败] {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
