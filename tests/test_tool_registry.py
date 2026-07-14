from __future__ import annotations

import unittest

from src.tools.definitions import ToolDefinition
from src.tools.registry import ToolRegistry


class ToolRegistryTests(unittest.TestCase):
    def setUp(self):
        self.definition = ToolDefinition(
            name="lookup",
            description="Lookup one value.",
            properties={"code": {"type": "string", "description": "Stock code."}},
            required=("code",),
            handler=lambda code: {"ok": True, "code": code},
        )
        self.registry = ToolRegistry([self.definition])

    def test_schema_is_openai_compatible(self):
        schema = self.registry.schemas()[0]
        self.assertEqual(schema["function"]["name"], "lookup")
        self.assertEqual(schema["function"]["parameters"]["required"], ["code"])
        self.assertFalse(schema["function"]["parameters"]["additionalProperties"])

    def test_execute_discards_unexpected_arguments(self):
        result = self.registry.execute("lookup", {"code": "600519", "ignored": True})
        self.assertEqual(result, {"ok": True, "code": "600519", "tool": "lookup"})

    def test_unknown_tool_returns_stable_error(self):
        result = self.registry.execute("missing", {})
        self.assertEqual(result, {"ok": False, "tool": "missing", "error": "unknown tool"})

    def test_handler_exception_is_sanitized(self):
        def fail():
            raise RuntimeError("api_key=secret-token at C:\\private\\path")

        registry = ToolRegistry(
            [
                ToolDefinition(
                    name="fail",
                    description="fail",
                    properties={},
                    required=(),
                    handler=fail,
                )
            ]
        )

        result = registry.execute("fail", {})

        self.assertEqual(result, {"ok": False, "tool": "fail", "error": "tool execution failed"})
        self.assertNotIn("secret-token", str(result))


if __name__ == "__main__":
    unittest.main()
