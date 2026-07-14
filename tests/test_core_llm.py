from __future__ import annotations

import subprocess
import sys
import unittest
from types import SimpleNamespace

from src.core.llm import LLMClient


class _Completions:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        function = SimpleNamespace(name="sample_tool", arguments='{"code": "600519"}')
        tool_call = SimpleNamespace(id="call-1", function=function)
        message = SimpleNamespace(content="", tool_calls=[tool_call])
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class CoreLLMTests(unittest.TestCase):
    def test_core_import_does_not_load_agents_or_tools(self):
        script = (
            "import sys; import src.core; "
            "assert not any(name == 'src.tools' or name.startswith('src.tools.') for name in sys.modules); "
            "assert not any(name == 'src.agents' or name.startswith('src.agents.') for name in sys.modules)"
        )
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_chat_with_tools_normalizes_sdk_tool_calls(self):
        llm = LLMClient.__new__(LLMClient)
        llm.model = "test-model"
        llm.base_url = ""
        completions = _Completions()
        llm.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        response = llm.chat_with_tools(
            [{"role": "user", "content": "analyze"}],
            [{"type": "function", "function": {"name": "sample_tool"}}],
        )

        self.assertEqual(response.content, "")
        self.assertEqual(len(response.tool_calls), 1)
        self.assertEqual(response.tool_calls[0].id, "call-1")
        self.assertEqual(response.tool_calls[0].name, "sample_tool")
        self.assertEqual(response.tool_calls[0].arguments, {"code": "600519"})
        self.assertNotIn("extra_body", completions.last_kwargs)

    def test_deepseek_v4_requests_disable_thinking(self):
        llm = LLMClient.__new__(LLMClient)
        llm.model = "deepseek-v4-pro"
        llm.base_url = "https://api.deepseek.com"
        completions = _Completions()
        llm.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        llm.chat_with_tools(
            [{"role": "user", "content": "analyze"}],
            [{"type": "function", "function": {"name": "sample_tool"}}],
        )

        self.assertEqual(
            completions.last_kwargs["extra_body"],
            {"thinking": {"type": "disabled"}},
        )


if __name__ == "__main__":
    unittest.main()
