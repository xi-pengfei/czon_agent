#!/usr/bin/env python3
"""
czon Agent 统一入口

子命令：
  python main.py                       # 选择 WebUI 或 CLI
  python main.py cli                   # 交互式 CLI
  python main.py "消息内容"             # 单次执行并退出
  python main.py webui                 # 按 config.yaml 启动 WebUI
  python main.py setup-code            # 查看首次管理员安装码
  python main.py reset-admin           # 重置管理员密码
  python main.py backup                # 创建迁移备份
  python main.py restore <备份文件>     # 恢复迁移备份
"""
import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
load_dotenv(PROJECT_ROOT / ".env")

_CLI_MODEL_PRESETS = (
    {"name": "deepseek", "display_name": "DeepSeek", "base_url": "https://api.deepseek.com/v1",
     "supports_vision": False, "supports_tools": True, "supports_streaming": True},
    {"name": "kimi", "display_name": "Kimi", "base_url": "https://api.moonshot.cn/v1",
     "supports_vision": True, "supports_tools": True, "supports_streaming": True},
    {"name": "qwen", "display_name": "通义千问", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "supports_vision": True, "supports_tools": True, "supports_streaming": True},
    {"name": "ollama", "display_name": "Ollama（本机或内网）", "base_url": "http://127.0.0.1:11434/v1",
     "api_key": "ollama", "supports_vision": False, "supports_tools": True, "supports_streaming": True},
)


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
    shell.register(registry, active_provider=provider, workspace_dir=workspace_dir)
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

    provider = _select_cli_provider(config)
    agent = build_agent(config, provider_override=provider)

    if message:
        run_once(agent, message)
    else:
        run_interactive(agent)


def _select_cli_provider(config: dict, input_fn=None, secret_fn=None) -> str:
    from core.auth_store import AuthStore

    input_fn = input_fn or input
    secret_fn = secret_fn or getpass.getpass
    webui_cfg = config.get("webui") or {}
    db_path = Path(webui_cfg.get("session_db", "./data/czon_agent.db"))
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    store = AuthStore(db_path)
    configured = [item for item in store.list_models() if item["api_key_configured"]]
    configured_names = {item["name"] for item in configured}
    preferred = os.getenv("CZON_ACTIVE_PROVIDER") or str(config.get("active_provider", ""))
    if preferred in configured_names:
        return preferred
    if not sys.stdin.isatty() and input_fn is input:
        raise RuntimeError("CLI 尚未选择模型，请在交互式终端运行 python main.py cli，或先使用 WebUI 配置")
    if configured:
        print("\n请选择本次 CLI 使用的模型：")
        for index, item in enumerate(configured, 1):
            print(f"  {index}. {item['display_name']} · {item['model']}")
        selected = _read_choice(input_fn, len(configured), "模型")
        return configured[selected - 1]["name"]
    return _configure_first_cli_model(config, store, input_fn, secret_fn)


def _configure_first_cli_model(config: dict, store, input_fn, secret_fn) -> str:
    from openai import OpenAI

    print("\n尚未配置大模型，现在完成首次设置。")
    for index, preset in enumerate(_CLI_MODEL_PRESETS, 1):
        print(f"  {index}. {preset['display_name']}")
    selected = _read_choice(input_fn, len(_CLI_MODEL_PRESETS), "服务商")
    preset = dict(_CLI_MODEL_PRESETS[selected - 1])
    api_key = preset.pop("api_key", "") or secret_fn("API Key（输入时不会显示）：").strip()
    if not api_key:
        raise RuntimeError("API Key 不能为空")

    print("正在获取模型列表...")
    timeout = int((config.get("agent") or {}).get("llm_read_timeout_seconds", 60))
    client = OpenAI(api_key=api_key, base_url=preset["base_url"], max_retries=0, timeout=timeout)
    try:
        models = sorted({item.id for item in client.models.list().data if getattr(item, "id", None)})
        if not models:
            raise RuntimeError("接口没有返回可用模型")
        print("请选择使用的模型：")
        for index, name in enumerate(models, 1):
            print(f"  {index}. {name}")
        model = models[_read_choice(input_fn, len(models), "模型") - 1]
        print("正在进行实际对话测试...")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with exactly OK."}],
            max_tokens=32,
            temperature=0,
        )
        content = response.choices[0].message.content if response.choices else ""
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("模型没有返回有效对话")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("模型连接测试失败，请检查网络、API Key 和服务状态") from exc
    finally:
        client.close()

    store.upsert_model({
        **preset,
        "model": model,
        "api_key": api_key,
        "enabled": True,
    }, actor="cli_setup")
    print(f"配置完成：{preset['display_name']} · {model}\n")
    return preset["name"]


def _read_choice(input_fn, count: int, label: str) -> int:
    while True:
        value = input_fn(f"请选择{label} [1-{count}]：").strip()
        if value.isdigit() and 1 <= int(value) <= count:
            return int(value)
        print("输入无效，请输入对应的数字。")


def _choose_start_mode(input_fn=None) -> str:
    input_fn = input_fn or input
    print("\n企业 AI 智能体")
    print("  1. 启动 WebUI（推荐）")
    print("  2. 使用命令行 CLI")
    choice = input_fn("请选择 [1]：").strip()
    if choice in {"", "1"}:
        return "webui"
    if choice == "2":
        return "cli"
    raise RuntimeError("请输入 1 或 2")


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
    from core.skills import SkillLoader

    session_db = webui_cfg.get("session_db", "./data/czon_agent.db")
    db_path = Path(session_db)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    auth_store = AuthStore(db_path)
    auth_store.seed_roles(DEFAULT_ROLES)
    skills_cfg = config.get("skills") or {}
    skills_dir = Path(skills_cfg.get("dir", "./skills"))
    if not skills_dir.is_absolute():
        skills_dir = PROJECT_ROOT / skills_dir

    def access_resolver(username: str):
        access = auth_store.get_access(username)
        if access is None:
            raise RuntimeError("用户不存在或已禁用")
        return SimpleNamespace(**access)

    def agent_factory(provider: str, username: str, user_workspace: str):
        access = access_resolver(username)
        webui_rules = config.get("webui", {}).get("extra_rules") or []
        merged_config = {
            **config,
            "current_user": username,
            "current_access": access,
            "workspace": {"dir": user_workspace},
            "skills": {
                **skills_cfg,
                "dir": str(skills_dir),
                "enabled": permitted_skill_names(username),
            },
            "agent": {
                **(config.get("agent") or {}),
                "extra_rules": [
                    *((config.get("agent") or {}).get("extra_rules") or []),
                    *webui_rules,
                ],
            },
        }
        return build_agent(merged_config, provider_override=provider)

    def permitted_skill_names(username: str) -> list[str]:
        access = access_resolver(username)
        loader = SkillLoader(skills_dir, enabled=None)
        loader.scan()
        names = list(loader.catalog)
        configured = skills_cfg.get("enabled")
        if configured is not None:
            configured_set = set(configured)
            names = [name for name in names if name in configured_set]
        settings = auth_store.list_skill_settings()
        names = [name for name in names if settings.get(name, {}).get("enabled", True)]
        return allowed_names(names, access.skills)

    def skill_catalog_provider(username: str):
        loader = SkillLoader(skills_dir, enabled=permitted_skill_names(username))
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
        skills_dir=str(skills_dir),
        skill_catalog_provider=skill_catalog_provider,
        provider_catalog_provider=provider_catalog_provider,
    )
    print(f"czon Agent WebUI 启动中：http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning", server_header=False)


def cmd_setup_code(config: dict):
    from core.auth_store import AuthStore

    session_db = (config.get("webui") or {}).get("session_db", "./data/czon_agent.db")
    db_path = Path(session_db)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    store = AuthStore(db_path)
    if store.has_users():
        print("管理员已经创建，无需安装码。")
    else:
        print(f"首次管理员安装码：{store.setup_code()}")


def cmd_reset_admin(config: dict, secret_fn=None):
    from core.auth_store import AuthStore

    secret_fn = secret_fn or getpass.getpass
    password = secret_fn("请输入 admin 的新密码（至少 6 位，不会显示）：")
    confirmation = secret_fn("请再次输入新密码：")
    if password != confirmation:
        raise RuntimeError("两次输入的密码不一致")
    if not 6 <= len(password) <= 256:
        raise RuntimeError("密码长度必须为 6 到 256 位")

    session_db = (config.get("webui") or {}).get("session_db", "./data/czon_agent.db")
    db_path = Path(session_db)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    store = AuthStore(db_path)
    if not store.reset_password("admin", password, actor="local_recovery", must_change=False):
        raise RuntimeError("admin 账号不存在，请先完成首次管理员设置")
    print("admin 密码已重置，原有登录会话已注销。")


def cmd_backup(config: dict, output_name: Optional[str] = None, secret_fn=None):
    from core.migration import create_backup

    _require_webui_stopped(config)
    secret_fn = secret_fn or getpass.getpass
    password = secret_fn("请设置迁移备份密码（至少 6 位，不会显示）：")
    if password != secret_fn("请再次输入备份密码："):
        raise RuntimeError("两次输入的备份密码不一致")
    if output_name:
        output = Path(output_name)
    else:
        from datetime import datetime
        output = PROJECT_ROOT / f"czon_agent_backup_{datetime.now():%Y%m%d_%H%M%S}.czon-backup"
    result = create_backup(PROJECT_ROOT, output, password)
    print(f"迁移备份已创建：{result}")


def cmd_restore(config: dict, backup_name: Optional[str], secret_fn=None):
    from core.migration import restore_backup

    if not backup_name:
        raise RuntimeError("请指定备份文件，例如：python main.py restore czon_agent_backup_xxx.czon-backup")
    _require_webui_stopped(config)
    secret_fn = secret_fn or getpass.getpass
    password = secret_fn("请输入迁移备份密码（不会显示）：")
    restore_backup(PROJECT_ROOT, Path(backup_name), password)
    print("迁移备份已恢复。启动服务后请先做只读试运行，确认无误后再执行任何外部写入或提交。")


def _require_webui_stopped(config: dict) -> None:
    import socket

    port = _positive_int(config.get("webui") or {}, "port")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            raise RuntimeError(f"请先停止 WebUI（端口 {port} 仍在使用），再执行迁移操作")
    except (ConnectionRefusedError, TimeoutError, OSError):
        return


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
    parser.add_argument("command_or_message", nargs="?", help="webui / cli / setup-code / reset-admin / backup / restore / 或直接输入消息")
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
        if command == "webui":
            cmd_webui(config, args)
        elif command == "cli":
            cmd_cli(config)
        elif command == "setup-code":
            cmd_setup_code(config)
        elif command == "reset-admin":
            cmd_reset_admin(config)
        elif command == "backup":
            cmd_backup(config, args.message_parts[0] if args.message_parts else None)
        elif command == "restore":
            cmd_restore(config, args.message_parts[0] if args.message_parts else None)
        elif command:
            message = " ".join([command] + args.message_parts).strip()
            cmd_cli(config, message=message)
        else:
            mode = _choose_start_mode()
            cmd_webui(config, args) if mode == "webui" else cmd_cli(config)
    except (RuntimeError, KeyError) as exc:
        print(f"[启动失败] {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
