"""
Agent 主循环：无状态，每次 run() 独立执行
"""
import base64
import json
import logging
import mimetypes
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional, List, Dict, Tuple

from core.tools import ToolResult

logger = logging.getLogger(__name__)


class AgentStopped(RuntimeError):
    """Raised when the caller asks an active run to stop."""


class AgentTimeout(RuntimeError):
    """Raised when a run exceeds its total runtime budget."""


class Agent:
    def __init__(
        self,
        llm,
        skill_loader,
        tool_registry,
        max_runtime_seconds: int,
        max_consecutive_errors: int,
        extra_rules: Optional[List[str]] = None,
    ):
        self.llm = llm
        self.skill_loader = skill_loader
        self.tool_registry = tool_registry
        self.max_runtime_seconds = max_runtime_seconds
        self.max_consecutive_errors = max_consecutive_errors
        self.extra_rules = extra_rules or []
        self.last_usage = {"input_tokens": 0, "output_tokens": 0}

    def run(
        self,
        user_text: str,
        attachments: Optional[List] = None,
        history: Optional[List[Dict]] = None,
        on_step: Optional[Callable] = None,
        on_delta: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[Dict], None]] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Tuple[str, List[Dict]]:
        """
        执行一次完整的 agent loop。
        返回 (最终回复文本, 步骤列表)。
        步骤格式：{"type": "tool_call", "name": ..., "args": ..., "result": ...}
        """
        logger.info(f"Agent 开始处理请求：{user_text[:100]}...")
        system = self._build_system_prompt()
        messages = list(history or [])
        messages.append(self._build_user_message(user_text, attachments))
        steps: List[Dict] = []
        deadline = time.monotonic() + self.max_runtime_seconds
        iteration = 0
        consecutive_errors = 0
        self.last_usage = {"input_tokens": 0, "output_tokens": 0}

        while True:
            self._check_control(stop_event, deadline)
            iteration += 1
            logger.info(f"第 {iteration} 轮 LLM 调用")
            tools = self.tool_registry.get_openai_schemas()
            msg = self._complete(
                system,
                messages,
                tools,
                on_delta=on_delta,
                stop_event=stop_event,
                deadline=deadline,
            )
            self._record_usage(getattr(msg, "usage", None))
            self._check_control(stop_event, deadline)

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
                except json.JSONDecodeError as e:
                    args = {}
                    result = ToolResult.failure(
                        "InvalidToolArguments",
                        f"工具参数不是合法 JSON：{e}",
                        recoverable=True,
                        meta={"raw_arguments": tc.function.arguments},
                    )
                    result_payload = result.to_dict()
                    step = {
                        "type": "tool_call",
                        "name": tool_name,
                        "args": args,
                        "result": result_payload,
                    }
                    steps.append(step)
                    if on_step:
                        on_step(step)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result_payload, ensure_ascii=False),
                    })
                    consecutive_errors += 1
                    if consecutive_errors >= self.max_consecutive_errors:
                        return self._error_limit_reply(consecutive_errors), steps
                    continue

                self._check_control(stop_event, deadline)
                def report_progress(progress):
                    if on_progress:
                        on_progress({
                            "type": "tool_progress",
                            "id": tc.id,
                            "name": tool_name,
                            **progress,
                        })

                started = time.monotonic()
                if on_progress:
                    on_progress({"type": "tool_start", "id": tc.id, "name": tool_name})
                result = self.tool_registry.execute(
                    tool_name,
                    args,
                    progress_callback=report_progress,
                    stop_event=stop_event,
                    execution_timeout=max(1, int(deadline - time.monotonic())),
                )
                self._check_control(stop_event, deadline)
                result_payload = result.to_dict()
                step = {
                    "type": "tool_call", "id": tc.id, "name": tool_name, "args": args,
                    "result": result_payload, "duration_ms": round((time.monotonic() - started) * 1000),
                }
                steps.append(step)

                if on_step:
                    on_step(step)

                # 追加 tool 结果消息
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result_payload, ensure_ascii=False),
                })

                if _error_type(result_payload) == "ConfirmationRequired":
                    reply = "该工具调用需要用户确认，当前任务已暂停。"
                    logger.info("Agent 暂停，等待用户确认工具调用")
                    return reply, steps

                if result.ok:
                    consecutive_errors = 0
                else:
                    consecutive_errors += 1
                    if consecutive_errors >= self.max_consecutive_errors:
                        return self._error_limit_reply(consecutive_errors), steps

    def _error_limit_reply(self, error_count: int) -> str:
        logger.warning("Agent 连续工具失败 %s 次，已停止", error_count)
        return "工具连续多次执行失败，任务已停止。请检查最后一条错误后重试。"

    @staticmethod
    def _check_control(stop_event: Optional[threading.Event], deadline: float) -> None:
        if stop_event and stop_event.is_set():
            raise AgentStopped("任务已由用户停止")
        if time.monotonic() >= deadline:
            raise AgentTimeout("任务执行时间已达到上限")

    def _build_system_prompt(self) -> str:
        """构建核心 system prompt（< 1000 tokens）"""
        catalog = self.skill_loader.get_catalog_text()
        tool_names = ", ".join(self.tool_registry.tools.keys()) or "(none)"
        extra_rules = "\n".join(f"- {rule}" for rule in self.extra_rules)
        extra_rules_block = f"\nConfigured rules:\n{extra_rules}\n" if extra_rules else ""
        return f"""You are an execution agent, not a general chat assistant.

Available tools: {tool_names}.

Tool priority:
1. If a relevant skill exists, call activate_skill(name) first, then follow the skill instructions exactly.
2. If no skill fits but read/write/bash can solve the task, use the built-in tools.
3. If the task cannot be solved with available tools, say the capability is missing and suggest adding a skill.

For requests about current local state, files, folders, databases, command output, or the user's machine, do not answer from general knowledge. Inspect with tools. Do not say you cannot access local state unless a tool call fails.

{catalog}

Rules:
- Always use activate_skill BEFORE bash-ing into a skill's scripts
- After activating a skill, follow its SKILL.md instructions exactly
- Never merely tell the user what command to run when you can run it yourself
- Never install or upgrade Python packages during a task unless the user explicitly requested that dependency change
- Attached files are local files. Use read/bash for text files and activate a relevant skill for office documents. Do not treat non-image attachments as images.
- After any mutating action, verify with a follow-up command before claiming success
- Tool results are JSON objects with ok/data/error/meta fields; inspect error.type before retrying
- If a tool returns ok=false, report the actual error and do not claim success
- If error.type is ConfirmationRequired, say the action is paused for confirmation; do not retry the command or replace it with a confirmation echo
- Keep responses concise unless user asks for detail
- Respond in the same language the user uses
{extra_rules_block}"""

    def _build_user_message(self, text: str, attachments: Optional[list]) -> dict:
        """构建用户消息，支持附件。只有图片会转成多模态输入。"""
        if not attachments:
            return {"role": "user", "content": text}

        content = []
        for item in attachments:
            attachment = _normalize_attachment(item)
            path_str = attachment["path"]
            path = Path(path_str)
            if not path.exists():
                logger.warning(f"附件文件不存在：{path_str}")
                content.append({"type": "text", "text": f"[附件不存在：{path_str}]"})
                continue
            mime = attachment.get("mime") or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            if not mime.startswith("image/"):
                name = attachment.get("name") or path.name
                content.append({
                    "type": "text",
                    "text": f"[附件：name={name}, path={path_str}, mime={mime}]",
                })
                continue
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })

        content.append({"type": "text", "text": text})
        return {"role": "user", "content": content}

    def _complete(
        self,
        system: str,
        messages: List,
        tools: List,
        on_delta: Optional[Callable[[str], None]] = None,
        stop_event: Optional[threading.Event] = None,
        deadline: Optional[float] = None,
    ):
        if not on_delta:
            return self.llm.complete(system, messages, tools)

        stream = self.llm.stream_complete(system, messages, tools)
        return self._consume_stream(stream, on_delta, stop_event, deadline)

    def _consume_stream(
        self,
        stream,
        on_delta: Callable[[str], None],
        stop_event: Optional[threading.Event],
        deadline: Optional[float],
    ):
        content_parts = []
        reasoning_parts = []
        tool_call_parts: Dict[int, Dict] = {}
        usage = None

        for chunk in stream:
            if deadline is not None:
                self._check_control(stop_event, deadline)
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage = chunk_usage
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            text = getattr(delta, "content", None)
            if text:
                content_parts.append(text)
                on_delta(text)

            reasoning_text = _get_field(delta, "reasoning_content")
            if reasoning_text:
                reasoning_parts.append(reasoning_text)

            for tc in getattr(delta, "tool_calls", None) or []:
                index = getattr(tc, "index", None)
                if index is None:
                    logger.warning("流式 tool_call 缺少 index，回退到非流式调用以避免多工具参数合并")
                    raise ValueError("stream tool_call missing index")
                item = tool_call_parts.setdefault(index, {"id": "", "name": "", "arguments": ""})
                tc_id = getattr(tc, "id", None)
                if tc_id:
                    item["id"] = tc_id

                fn = getattr(tc, "function", None)
                if not fn:
                    continue
                name = getattr(fn, "name", None)
                arguments = getattr(fn, "arguments", None)
                if name:
                    item["name"] += name
                if arguments:
                    item["arguments"] += arguments

        tool_calls = []
        for index in sorted(tool_call_parts):
            item = tool_call_parts[index]
            if not item["name"]:
                continue
            tool_calls.append(SimpleNamespace(
                id=item["id"] or f"call_{index}",
                function=SimpleNamespace(name=item["name"], arguments=item["arguments"]),
            ))

        return SimpleNamespace(
            content="".join(content_parts),
            reasoning_content="".join(reasoning_parts) or None,
            tool_calls=tool_calls or None,
            usage=usage,
        )

    def _record_usage(self, usage) -> None:
        if usage is None:
            return
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        if input_tokens is None:
            input_tokens = getattr(usage, "input_tokens", 0)
        if output_tokens is None:
            output_tokens = getattr(usage, "output_tokens", 0)
        self.last_usage["input_tokens"] += max(0, int(input_tokens or 0))
        self.last_usage["output_tokens"] += max(0, int(output_tokens or 0))


def _error_type(result_payload: dict) -> Optional[str]:
    error = result_payload.get("error") if isinstance(result_payload, dict) else None
    return error.get("type") if isinstance(error, dict) else None


def _get_field(obj, name: str):
    value = getattr(obj, name, None)
    if value is not None:
        return value

    extra = getattr(obj, "model_extra", None)
    if isinstance(extra, dict):
        return extra.get(name)

    if isinstance(obj, dict):
        return obj.get(name)

    return None


def _normalize_attachment(item) -> Dict[str, str]:
    if isinstance(item, dict):
        path = str(item.get("path") or "")
        return {
            "path": path,
            "name": str(item.get("name") or Path(path).name),
            "mime": str(item.get("mime") or ""),
        }
    path = str(item)
    return {
        "path": path,
        "name": Path(path).name,
        "mime": mimetypes.guess_type(path)[0] or "",
    }
