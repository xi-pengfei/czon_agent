"""
工具注册表：统一管理所有内置工具的 schema 和处理函数
"""
import logging
from typing import Callable, Dict

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self):
        # name -> {"schema": dict, "handler": Callable}
        self.tools: Dict[str, Dict] = {}

    def register(self, name: str, description: str, parameters: dict, handler: Callable):
        """注册一个工具"""
        self.tools[name] = {
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            },
            "handler": handler,
        }
        logger.debug(f"工具已注册：{name}")

    def get_openai_schemas(self) -> list[dict]:
        """返回 OpenAI function calling 格式的 tools 列表"""
        return [v["schema"] for v in self.tools.values()]

    def execute(self, name: str, arguments: dict) -> str:
        """
        执行工具，返回字符串结果。
        不存在的工具返回错误字符串（让 LLM 自己纠错，而不是抛异常）。
        """
        if name not in self.tools:
            available = ", ".join(self.tools.keys())
            return f"[error] 工具 '{name}' 不存在。可用工具：{available}"
        try:
            logger.info(f"执行工具：{name}，参数：{arguments}")
            result = self.tools[name]["handler"](**arguments)
            result_str = str(result)
            logger.info(f"工具 {name} 执行完成，输出长度：{len(result_str)}")
            logger.debug(f"工具 {name} 输出：{result_str[:500]}")
            return result_str
        except Exception as e:
            logger.error(f"工具 {name} 执行出错：{e}", exc_info=True)
            return f"[error] 工具 '{name}' 执行失败：{e}"
