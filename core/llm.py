"""
LLM 抽象层：封装 Kimi / Qwen / DeepSeek 三家 OpenAI 兼容接口
"""
import logging
import os
from typing import Dict, Literal, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

ProviderName = Literal["kimi", "qwen", "deepseek"]

PROVIDERS: Dict[str, Dict] = {
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-128k",
        "supports_vision": True,
        "env_key": "MOONSHOT_API_KEY",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-vl-max",
        "supports_vision": True,
        "env_key": "DASHSCOPE_API_KEY",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-v4-pro",
        "supports_vision": False,
        "env_key": "DEEPSEEK_API_KEY",
    },
}


class LLM:
    def __init__(self, provider: ProviderName, api_key: str, model: Optional[str] = None):
        cfg = PROVIDERS[provider]
        self.provider = provider
        self._supports_vision: bool = cfg["supports_vision"]
        self.model = model or cfg["default_model"]
        self.client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
        logger.info(f"LLM 初始化：provider={provider}, model={self.model}")

    @property
    def supports_vision(self) -> bool:
        return self._supports_vision

    def complete(self, system: str, messages: List, tools: List):
        """
        调用 chat.completions.create，返回原始 message 对象。
        如果 provider 不支持视觉但消息里含图片，把图片 url 替换为文字提示并警告。
        """
        kwargs = self._build_chat_kwargs(system, messages, tools)
        response = self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        logger.debug(f"LLM 响应：content={str(msg.content)[:200]}, tool_calls={msg.tool_calls}")
        return msg

    def stream_complete(self, system: str, messages: List, tools: List):
        """以 stream=True 调用 chat.completions.create，返回 chunk iterator。"""
        kwargs = self._build_chat_kwargs(system, messages, tools)
        kwargs["stream"] = True
        return self.client.chat.completions.create(**kwargs)

    def _build_chat_kwargs(self, system: str, messages: List, tools: List) -> Dict:
        if not self._supports_vision:
            messages = self._strip_images(messages)

        all_messages = [{"role": "system", "content": system}] + messages
        logger.debug(f"LLM 请求：model={self.model}, messages={len(all_messages)} 条, tools={len(tools)} 个")

        kwargs: Dict = {
            "model": self.model,
            "messages": all_messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return kwargs

    def _strip_images(self, messages: List) -> List:
        """DeepSeek 不支持视觉，把图片内容替换为文字说明"""
        result = []
        for m in messages:
            if isinstance(m.get("content"), list):
                new_parts = []
                for part in m["content"]:
                    if part.get("type") == "image_url":
                        url = part.get("image_url", {}).get("url", "")
                        logger.warning(f"当前 provider ({self.provider}) 不支持图片，图片已作为文本传入：{url[:60]}...")
                        new_parts.append({"type": "text", "text": f"[图片：{url[:80]}（该 provider 不支持视觉，已忽略）]"})
                    else:
                        new_parts.append(part)
                result.append({**m, "content": new_parts})
            else:
                result.append(m)
        return result


def make_llm_from_config(config: dict) -> LLM:
    """从 config.yaml 解析内容构建 LLM 实例"""
    from dotenv import load_dotenv
    load_dotenv()

    provider: ProviderName = config.get("active_provider", "kimi")
    cfg = PROVIDERS[provider]
    api_key = os.getenv(cfg["env_key"], "")
    if not api_key:
        raise RuntimeError(f"未找到 {cfg['env_key']} 环境变量，请在 .env 中配置")

    # 取 config.yaml 里的 model 覆盖
    model_override = config.get("providers", {}).get(provider, {}).get("model")
    return LLM(provider=provider, api_key=api_key, model=model_override)
