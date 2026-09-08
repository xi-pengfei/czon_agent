import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.agent import Agent, AgentStopped, AgentTimeout
from core.tools import ToolRegistry


class EmptySkills:
    def get_catalog_text(self):
        return ""


def tool_call(index: int):
    return SimpleNamespace(
        content=None,
        tool_calls=[SimpleNamespace(
            id=f"call-{index}",
            function=SimpleNamespace(name="tick", arguments="{}"),
        )],
    )


class CountingLLM:
    def __init__(self, tool_rounds: int):
        self.tool_rounds = tool_rounds
        self.calls = 0

    def complete(self, system, messages, tools):
        self.calls += 1
        if self.calls <= self.tool_rounds:
            message = tool_call(self.calls)
        else:
            message = SimpleNamespace(content="done", tool_calls=None)
        message.usage = SimpleNamespace(prompt_tokens=10, completion_tokens=2)
        return message


def make_agent(llm, max_errors=3):
    registry = ToolRegistry()
    registry.register("tick", "test", {"type": "object", "properties": {}}, lambda: "ok")
    return Agent(
        llm=llm,
        skill_loader=EmptySkills(),
        tool_registry=registry,
        max_runtime_seconds=30,
        max_consecutive_errors=max_errors,
    )


class AgentControlTests(unittest.TestCase):
    def test_more_than_fifteen_rounds_can_complete(self):
        llm = CountingLLM(tool_rounds=20)
        agent = make_agent(llm)
        reply, steps = agent.run("work")
        self.assertEqual(reply, "done")
        self.assertEqual(len(steps), 20)
        self.assertEqual(llm.calls, 21)
        self.assertEqual(agent.last_usage, {"input_tokens": 210, "output_tokens": 42})

    def test_pre_set_stop_event_stops_before_llm_call(self):
        event = threading.Event()
        event.set()
        llm = CountingLLM(tool_rounds=0)
        with self.assertRaises(AgentStopped):
            make_agent(llm).run("work", stop_event=event)
        self.assertEqual(llm.calls, 0)

    def test_total_runtime_timeout_is_enforced(self):
        llm = CountingLLM(tool_rounds=0)
        with patch("core.agent.time.monotonic", side_effect=[0, 31]):
            with self.assertRaises(AgentTimeout):
                make_agent(llm).run("work")

    def test_consecutive_tool_errors_stop_the_run(self):
        llm = CountingLLM(tool_rounds=10)
        agent = make_agent(llm, max_errors=3)
        agent.tool_registry.tools.pop("tick")
        reply, steps = agent.run("work")
        self.assertIn("连续多次执行失败", reply)
        self.assertEqual(len(steps), 3)


if __name__ == "__main__":
    unittest.main()
