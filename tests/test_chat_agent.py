from __future__ import annotations

import unittest

from src.agents.chat.tool_catalog import build_default_registry
from src.agents.chat.workflow import run_chat_turn
from src.core.llm import LLMResponse, LLMToolCall
from src.tools.definitions import ToolDefinition
from src.tools.registry import ToolRegistry


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
    def test_chat_workflow_executes_tool_then_returns_answer(self):
        registry = ToolRegistry(
            [
                ToolDefinition(
                    name="lookup",
                    description="lookup",
                    properties={"code": {"type": "string"}},
                    required=("code",),
                    handler=lambda code: {"ok": True, "code": code},
                )
            ]
        )
        llm = _FakeLLM()

        state = run_chat_turn("分析 600519", llm_client=llm, registry=registry)

        self.assertEqual(state["final_answer"], "工具结果已处理。")
        self.assertEqual(state["tool_results"][0]["name"], "lookup")
        self.assertEqual(llm.calls, 2)

    def test_default_catalog_contains_light_and_deep_tools(self):
        names = {schema["function"]["name"] for schema in build_default_registry().schemas()}
        self.assertIn("get_realtime_price", names)
        self.assertIn("run_deep_research", names)

    def test_llm_exception_is_sanitized(self):
        state = run_chat_turn(
            "hello",
            llm_client=_FailingLLM(),
            registry=ToolRegistry([]),
        )

        self.assertEqual(state["final_answer"], "LLM 调用失败，请稍后重试。")
        self.assertEqual(state["error"], "llm request failed")
        self.assertNotIn("secret-token", str(state))

    def test_tool_round_limit_returns_explicit_answer(self):
        llm = _LoopingLLM()
        registry = ToolRegistry(
            [
                ToolDefinition(
                    name="lookup",
                    description="lookup",
                    properties={},
                    required=(),
                    handler=lambda: {"ok": True},
                )
            ]
        )

        state = run_chat_turn("loop", llm_client=llm, registry=registry)

        self.assertEqual(llm.calls, 8)
        self.assertEqual(state["final_answer"], "工具调用轮次已达上限，请缩小问题范围后重试。")
        self.assertEqual(state["pending_tool_calls"], [])


if __name__ == "__main__":
    unittest.main()
