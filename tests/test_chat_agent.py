from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass

from src.agents.chat import LangGraphChatAgent
from src.agents.chat.nodes import MAX_TOOL_ROUNDS
from src.core.llm import LLMResponse, LLMToolCall


@dataclass(frozen=True)
class _Execution:
    name: str
    result: dict
    pending_action: dict | None = None


class _Executor:
    def __init__(self):
        self.calls = []

    def schemas(self):
        return [{"type": "function", "function": {"name": "lookup", "description": "lookup", "parameters": {"type": "object"}}}]

    async def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return _Execution(name=name, result={"ok": True, **arguments})


class _FakeLLM:
    def __init__(self):
        self.calls = 0

    def chat_with_tools(self, messages, tools, temperature=0):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(tool_calls=[LLMToolCall(id="call-1", name="lookup", arguments={"code": "600519"})])
        return LLMResponse(content="工具结果已处理。")


class _FailingLLM:
    def chat_with_tools(self, messages, tools, temperature=0):
        raise RuntimeError("api_key=secret-token at C:\\private\\path")


class _LoopingLLM:
    def __init__(self):
        self.calls = 0

    def chat_with_tools(self, messages, tools, temperature=0):
        self.calls += 1
        return LLMResponse(tool_calls=[LLMToolCall(id=f"call-{self.calls}", name="lookup", arguments={})])


class ChatAgentTests(unittest.TestCase):
    def test_langgraph_executes_tool_then_returns_answer(self):
        executor = _Executor()
        llm = _FakeLLM()
        events = []

        result = asyncio.run(
            LangGraphChatAgent(executor, "test prompt", llm_client=llm).run(
                [{"role": "user", "content": "分析 600519"}],
                on_event=lambda event, data: events.append((event, data)),
            )
        )

        self.assertEqual(result.answer, "工具结果已处理。")
        self.assertEqual(result.tool_results[0]["name"], "lookup")
        self.assertEqual(executor.calls, [("lookup", {"code": "600519"})])
        self.assertEqual(llm.calls, 2)
        self.assertEqual(
            [event for event, _data in events],
            ["planning", "tool_started", "tool_completed", "synthesizing"],
        )
        self.assertEqual(events[2][1]["status"], "completed")
        self.assertIn("duration_ms", events[2][1])

    def test_llm_exception_is_sanitized(self):
        result = asyncio.run(
            LangGraphChatAgent(_Executor(), "test prompt", llm_client=_FailingLLM()).run(
                [{"role": "user", "content": "hello"}]
            )
        )

        self.assertEqual(result.answer, "当前 LLM 服务不可用。")
        self.assertEqual(result.error, "llm request failed")
        self.assertNotIn("secret-token", str(result))

    def test_tool_round_limit_returns_explicit_answer(self):
        llm = _LoopingLLM()

        result = asyncio.run(
            LangGraphChatAgent(_Executor(), "test prompt", llm_client=llm).run(
                [{"role": "user", "content": "loop"}]
            )
        )

        self.assertEqual(llm.calls, MAX_TOOL_ROUNDS)
        self.assertEqual(result.answer, "工具调用轮次已达上限，请缩小问题范围后重试。")


if __name__ == "__main__":
    unittest.main()
