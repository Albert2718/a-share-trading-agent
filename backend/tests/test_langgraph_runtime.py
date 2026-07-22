import pytest
from pydantic import BaseModel

from app.agent_runtime.specs import AsyncToolRegistry, BoundToolExecutor, ToolEffect, ToolSpec
from app.agent_runtime.tools import WebToolContext, build_web_tool_registry
from app.schemas.knowledge import RagSource
from app.services.knowledge_service import KnowledgeService
from src.agents.chat import LangGraphChatAgent
from src.core.llm import LLMResponse, LLMToolCall


class EchoArgs(BaseModel):
    value: str


class FakeLLM:
    def __init__(self, responses):
        self.responses = iter(responses)

    def chat_with_tools(self, _messages, _tools, _temperature=0):
        return next(self.responses)


@pytest.mark.asyncio
async def test_langgraph_executes_tool_then_returns_final_answer():
    calls = []

    async def echo(_context, args):
        calls.append(args.value)
        return {"ok": True, "echo": args.value}

    registry = AsyncToolRegistry([
        ToolSpec("echo", "echo test", EchoArgs, ToolEffect.READ, echo)
    ])
    llm = FakeLLM([
        LLMResponse(tool_calls=[LLMToolCall(id="call-1", name="echo", arguments={"value": "600519"})]),
        LLMResponse(content="工具执行完成。"),
    ])
    result = await LangGraphChatAgent(
        BoundToolExecutor(registry, object()),
        "test system prompt",
        llm_client=llm,
    ).run([
        {"role": "user", "content": "测试"}
    ])

    assert result.answer == "工具执行完成。"
    assert calls == ["600519"]
    assert result.tool_results[0]["result"]["echo"] == "600519"


@pytest.mark.asyncio
async def test_langgraph_confirmation_tool_is_prepared_not_executed():
    async def forbidden(_context, _args):
        raise AssertionError("confirmation handler must not execute")

    registry = AsyncToolRegistry([
        ToolSpec("portfolio_upsert", "prepare write", EchoArgs, ToolEffect.CONFIRM_WRITE, forbidden)
    ])
    llm = FakeLLM([
        LLMResponse(tool_calls=[LLMToolCall(
            id="call-1", name="portfolio_upsert", arguments={"value": "pending"}
        )]),
        LLMResponse(content="请确认。"),
    ])
    events = []
    result = await LangGraphChatAgent(
        BoundToolExecutor(registry, object()),
        "test system prompt",
        llm_client=llm,
    ).run([
        {"role": "user", "content": "测试写入"}
    ], on_event=lambda event, data: events.append((event, data)))

    assert result.pending_action == {
        "tool_name": "portfolio_upsert",
        "arguments": {"value": "pending"},
    }
    assert result.answer == "请确认。"
    confirmation = next(data for event, data in events if event == "awaiting_confirmation")
    assert confirmation["tool_name"] == "portfolio_upsert"
    assert confirmation["status"] == "awaiting_confirmation"


@pytest.mark.asyncio
async def test_web_agent_knowledge_tool_filters_user_sources(monkeypatch):
    received = {}

    async def fake_search(_service, **kwargs):
        received.update(kwargs)
        return [
            RagSource(
                document_id="doc-1",
                title="年度报告",
                filename="report.pdf",
                source_type="financial_report",
                page_number=12,
                chunk_index=3,
                content="经营现金流同比改善。",
                score=0.88,
            )
        ]

    monkeypatch.setattr(KnowledgeService, "search", fake_search)
    placeholder = object()
    context = WebToolContext(
        user_id="user-1",
        risk_profile="balanced",
        portfolio=placeholder,
        research=placeholder,
        memory=placeholder,
        knowledge=placeholder,
        outbox=placeholder,
    )

    execution = await build_web_tool_registry().execute(
        context,
        "knowledge_search",
        {
            "question": "现金流有什么变化？",
            "stock_code": "600519",
            "source_types": ["financial_report"],
            "top_k": 3,
        },
    )

    assert execution.result["ok"] is True
    assert execution.result["sources"][0]["source_type"] == "financial_report"
    assert received["user_id"] == "user-1"
    assert received["stock_code"] == "600519"
    assert received["source_types"] == ["financial_report"]
