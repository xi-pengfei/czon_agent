"""OpenAI-compatible LLM client backed by the application's model registry."""
import logging
import os
from pathlib import Path
from typing import Dict, List

import httpx
from openai import OpenAI

logger = logging.getLogger(__name__)

DEFAULT_MODELS = {
    "kimi": {"display_name": "Kimi", "base_url": "https://api.moonshot.cn/v1", "model": "kimi-k3", "supports_vision": True},
    "qwen": {"display_name": "通义千问", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-vl-max", "supports_vision": True},
    "deepseek": {"display_name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-v4-pro", "supports_vision": False},
}


def get_provider_configs(config: dict) -> Dict[str, Dict]:
    providers = config.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise RuntimeError("config.yaml 中 providers 必须是非空映射")
    result = {}
    for name, raw in providers.items():
        if not isinstance(name, str) or not name or not isinstance(raw, dict):
            raise RuntimeError("config.yaml 中 provider 配置格式不合法")
        cfg = dict(raw)
        for key in ("base_url", "model"):
            if not isinstance(cfg.get(key), str) or not cfg[key].strip():
                raise RuntimeError(f"provider '{name}' 缺少有效的 {key}")
        if not cfg.get("api_key"):
            raise RuntimeError(f"provider '{name}' 缺少 API Key 配置")
        if not isinstance(cfg.get("supports_vision"), bool):
            raise RuntimeError(f"provider '{name}' 的 supports_vision 必须是布尔值")
        cfg["display_name"] = str(cfg.get("display_name") or name)
        result[name] = cfg
    return result


def get_runtime_provider_configs(config: dict, project_root: Path | None = None) -> Dict[str, Dict]:
    """Resolve every model and secret from the shared application database."""
    if project_root is None:
        raise RuntimeError("未指定项目目录，无法读取数据库中的模型配置")

    from core.auth_store import AuthStore

    webui_config = config.get("webui") or {}
    db_path = Path(webui_config.get("session_db", "./data/czon_agent.db"))
    if not db_path.is_absolute():
        db_path = project_root / db_path
    store = AuthStore(db_path)
    store.seed_models(DEFAULT_MODELS)
    providers = {}
    for item in store.list_models():
        api_key = store.get_model_api_key(item["name"])
        if not api_key:
            continue
        providers[item["name"]] = {
            "display_name": item["display_name"],
            "base_url": item["base_url"],
            "model": item["model"],
            "api_key": api_key,
            "supports_vision": bool(item["supports_vision"]),
        }
    return get_provider_configs({"providers": providers}) if providers else {}


class LLM:
    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        base_url: str,
        supports_vision: bool,
        request_timeout: int = 120,
    ):
        self.provider = provider
        self._supports_vision = supports_vision
        self.model = model
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.Client(proxy=None, timeout=request_timeout),
        )
        logger.info("LLM 初始化：provider=%s, model=%s", provider, self.model)

    @property
    def supports_vision(self) -> bool:
        return self._supports_vision

    def complete(self, system: str, messages: List, tools: List):
        kwargs = self._build_chat_kwargs(system, messages, tools)
        response = self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        logger.debug("LLM 响应：content=%s, tool_calls=%s", str(msg.content)[:200], msg.tool_calls)
        return type("LLMMessage", (), {
            "content": msg.content,
            "tool_calls": msg.tool_calls,
            "reasoning_content": getattr(msg, "reasoning_content", None),
            "usage": response.usage,
        })()

    def stream_complete(self, system: str, messages: List, tools: List):
        kwargs = self._build_chat_kwargs(system, messages, tools)
        kwargs["stream"] = True
        kwargs["stream_options"] = {"include_usage": True}
        return self.client.chat.completions.create(**kwargs)

    def _build_chat_kwargs(self, system: str, messages: List, tools: List) -> Dict:
        if not self._supports_vision:
            messages = self._strip_images(messages)
        all_messages = [{"role": "system", "content": system}] + messages
        logger.debug("LLM 请求：model=%s, messages=%s 条, tools=%s 个", self.model, len(all_messages), len(tools))
        kwargs: Dict = {"model": self.model, "messages": all_messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return kwargs

    def _strip_images(self, messages: List) -> List:
        result = []
        for message in messages:
            if isinstance(message.get("content"), list):
                new_parts = []
                for part in message["content"]:
                    if part.get("type") == "image_url":
                        logger.warning("当前 provider (%s) 不支持图片，已忽略图片", self.provider)
                        new_parts.append({"type": "text", "text": "[图片已忽略：当前模型不支持视觉]"})
                    else:
                        new_parts.append(part)
                result.append({**message, "content": new_parts})
            else:
                result.append(message)
        return result


def make_llm_from_config(config: dict, project_root: Path | None = None) -> LLM:
    providers = get_runtime_provider_configs(config, project_root)
    provider = os.getenv("CZON_ACTIVE_PROVIDER") or str(config.get("active_provider", ""))
    if provider not in providers:
        raise RuntimeError(f"当前模型 '{provider}' 不存在、未启用或尚未配置 API Key")
    cfg = providers[provider]
    api_key = cfg.get("api_key")
    if not api_key:
        raise RuntimeError("当前模型尚未配置 API Key")
    timeout = config.get("agent", {}).get("llm_request_timeout_seconds")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise RuntimeError("config.yaml 中 agent.llm_request_timeout_seconds 必须是正整数")
    return LLM(
        provider=provider,
        api_key=api_key,
        model=cfg["model"],
        base_url=cfg["base_url"],
        supports_vision=cfg["supports_vision"],
        request_timeout=timeout,
    )
