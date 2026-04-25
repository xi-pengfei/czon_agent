"""
Agent 主循环：无状态，每次 run() 独立执行
"""
import base64
import json
import logging
import mimetypes
from pathlib import Path
from typing import Callable, Optional, List, Dict, Tuple

logger = logging.getLogger(__name__)


class Agent:
    def __init__(self, llm, skill_loader, tool_registry, max_iterations: int = 15):
        self.llm = llm
        self.skill_loader = skill_loader
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations

    def run(
        self,
        user_text: str,
        image_paths: Optional[List[str]] = None,
        on_step: Optional[Callable] = None,
    ) -> Tuple[str, List[Dict]]:
        """
        执行一次完整的 agent loop。
        返回 (最终回复文本, 步骤列表)。
        步骤格式：{"type": "tool_call", "name": ..., "args": ..., "result": ...}
        """
        logger.info(f"Agent 开始处理请求：{user_text[:100]}...")
        system = self._build_system_prompt()
        messages = [self._build_user_message(user_text, image_paths)]
        steps: List[Dict] = []

        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"第 {iteration} 轮 LLM 调用")
            tools = self.tool_registry.get_openai_schemas()
            msg = self.llm.complete(system, messages, tools)

            # 无工具调用 → 最终回复
            if not msg.tool_calls:
                reply = msg.content or ""
                logger.info(f"Agent 完成，共 {iteration} 轮，回复长度 {len(reply)}")
                return reply, steps

            # 有工具调用 → 追加 assistant 消息
            assistant_msg = {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            }
            # 如果有 reasoning_content（扩展思考模型），保留它
            if hasattr(msg, 'reasoning_content') and msg.reasoning_content:
                assistant_msg["reasoning_content"] = msg.reasoning_content
            messages.append(assistant_msg)

            # 逐个执行工具
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                result = self.tool_registry.execute(tool_name, args)
                step = {"type": "tool_call", "name": tool_name, "args": args, "result": result}
                steps.append(step)

                if on_step:
                    on_step(step)

                # 追加 tool 结果消息
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        # 超出最大轮次
        last_progress = steps[-1]["result"][:200] if steps else "无"
        reply = f"任务未能在 {self.max_iterations} 轮内完成，已中止。最后的进展是：{last_progress}"
        logger.warning(f"Agent 超出最大迭代次数 {self.max_iterations}")
        return reply, steps

    def _build_system_prompt(self) -> str:
        """构建核心 system prompt（< 1000 tokens）"""
        catalog = self.skill_loader.get_catalog_text()
        return f"""You are a task execution agent that uses tools and skills to help users.

You have 4 built-in tools: read, write, bash, activate_skill.

IMPORTANT: Before executing any specialized task, check if there's a relevant skill in the catalog below. If yes, use activate_skill(name) to load its full instructions. Don't guess — skills contain the exact commands and schemas you need.

{catalog}

Rules:
- Always use activate_skill BEFORE bash-ing into a skill's scripts
- After activating a skill, follow its SKILL.md instructions exactly
- Keep responses concise unless user asks for detail
- Respond in the same language the user uses"""

    def _build_user_message(self, text: str, image_paths: Optional[list[str]]) -> dict:
        """构建用户消息，支持多模态（图片 base64 编码）"""
        if not image_paths:
            return {"role": "user", "content": text}

        content = []
        for path_str in image_paths:
            path = Path(path_str)
            if not path.exists():
                logger.warning(f"图片文件不存在：{path_str}")
                content.append({"type": "text", "text": f"[图片文件不存在：{path_str}]"})
                continue
            mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
            if not mime.startswith("image/"):
                # 非图片文件作为文本路径传入
                content.append({"type": "text", "text": f"[附件路径：{path_str}]"})
                continue
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })

        content.append({"type": "text", "text": text})
        return {"role": "user", "content": content}
