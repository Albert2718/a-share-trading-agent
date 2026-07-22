import pytest

from conftest import auth_headers, register
from src.agents.chat import AgentRunResult, LangGraphChatAgent


@pytest.mark.asyncio
async def test_portfolio_confirmation_is_durable_and_idempotent(app_context, monkeypatch):
    client = app_context["client"]
    auth = await register(client, "confirm")
    headers = auth_headers(auth)
    created = await client.post("/api/v1/chat/conversations", headers=headers)
    conversation_id = created.json()["id"]

    async def pending_write(_runtime, _messages):
        return AgentRunResult(
            answer="请确认写入持仓。",
            pending_action={
                "tool_name": "portfolio_upsert",
                "arguments": {
                    "stock_code": "600519",
                    "stock_name": "贵州茅台",
                    "quantity": 100,
                    "average_cost": 1450.0,
                },
            },
        )

    monkeypatch.setattr(LangGraphChatAgent, "run", pending_write)
    message = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": "记录 600519 100 股，成本 1450 元"},
    )
    assert message.status_code == 200, message.text
    payload = message.json()
    assert payload["tool_payload"]["status"] == "pending_confirmation"

    first = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/confirm/{payload['id']}",
        headers=headers,
    )
    assert first.status_code == 200, first.text

    duplicate = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/confirm/{payload['id']}",
        headers=headers,
    )
    assert duplicate.status_code == 400

    positions = await client.get(
        "/api/v1/portfolio/positions?refresh_market=false", headers=headers
    )
    assert positions.status_code == 200
    assert len(positions.json()) == 1
    assert positions.json()[0]["stock_code"] == "600519"


@pytest.mark.asyncio
async def test_portfolio_can_be_confirmed_with_natural_language(app_context, monkeypatch):
    client = app_context["client"]
    auth = await register(client, "natural_confirm")
    headers = auth_headers(auth)
    created = await client.post("/api/v1/chat/conversations", headers=headers)
    conversation_id = created.json()["id"]
    agent_calls = 0

    async def pending_write(_runtime, _messages):
        nonlocal agent_calls
        agent_calls += 1
        return AgentRunResult(
            answer="请确认写入持仓。",
            pending_action={
                "tool_name": "portfolio_upsert",
                "arguments": {
                    "stock_code": "600567",
                    "stock_name": "山鹰国际",
                    "quantity": 1000,
                    "average_cost": 1.34,
                },
            },
        )

    monkeypatch.setattr(LangGraphChatAgent, "run", pending_write)
    prepared = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": "记录山鹰国际 600567，1000 股，成本 1.34 元"},
    )
    confirmed = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": "我确认以上信息无误，请写入"},
    )

    assert prepared.json()["tool_payload"]["status"] == "pending_confirmation"
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["content"] == "已保存 600567 的持仓记录。"
    assert confirmed.json()["tool_payload"]["status"] == "completed"
    assert agent_calls == 1

    conversation = await client.get(
        f"/api/v1/chat/conversations/{conversation_id}", headers=headers
    )
    assert [item["content"] for item in conversation.json()["messages"]][-2:] == [
        "我确认以上信息无误，请写入",
        "已保存 600567 的持仓记录。",
    ]
    positions = await client.get(
        "/api/v1/portfolio/positions?refresh_market=false", headers=headers
    )
    assert positions.json()[0]["stock_code"] == "600567"


@pytest.mark.asyncio
async def test_pending_write_can_be_cancelled_with_natural_language(app_context, monkeypatch):
    client = app_context["client"]
    auth = await register(client, "natural_cancel")
    headers = auth_headers(auth)
    created = await client.post("/api/v1/chat/conversations", headers=headers)
    conversation_id = created.json()["id"]

    async def pending_write(_runtime, _messages):
        return AgentRunResult(
            answer="请确认写入持仓。",
            pending_action={
                "tool_name": "portfolio_upsert",
                "arguments": {
                    "stock_code": "600567",
                    "stock_name": "山鹰国际",
                    "quantity": 1000,
                    "average_cost": 1.34,
                },
            },
        )

    monkeypatch.setattr(LangGraphChatAgent, "run", pending_write)
    await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": "记录 600567 1000 股，成本 1.34 元"},
    )
    cancelled = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": "取消"},
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["tool_payload"]["status"] == "cancelled"
    positions = await client.get(
        "/api/v1/portfolio/positions?refresh_market=false", headers=headers
    )
    assert positions.json() == []


@pytest.mark.asyncio
async def test_llm_failure_uses_rule_fallback_but_still_creates_outbox(app_context, monkeypatch):
    client = app_context["client"]
    auth = await register(client, "fallback")
    headers = auth_headers(auth)
    created = await client.post("/api/v1/chat/conversations", headers=headers)

    async def unavailable(_runtime, _messages):
        return AgentRunResult(answer="当前 LLM 服务不可用。", error="llm request failed")

    monkeypatch.setattr(LangGraphChatAgent, "run", unavailable)
    response = await client.post(
        f"/api/v1/chat/conversations/{created.json()['id']}/messages",
        headers=headers,
        json={"content": "深度分析 600519，偏保守"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["tool_name"] == "research_submit"

    jobs = await client.get("/api/v1/research/jobs", headers=headers)
    assert len(jobs.json()) == 1

    from sqlalchemy import func, select
    from app.models import OutboxEvent

    async with app_context["session_maker"]() as session:
        count = await session.scalar(select(func.count()).select_from(OutboxEvent))
    assert count == 1


@pytest.mark.asyncio
async def test_memory_confirmation_writes_only_after_confirmation(app_context, monkeypatch):
    client = app_context["client"]
    auth = await register(client, "memory_confirm")
    headers = auth_headers(auth)
    created = await client.post("/api/v1/chat/conversations", headers=headers)
    conversation_id = created.json()["id"]

    async def pending_memory(_runtime, _messages):
        return AgentRunResult(
            answer="请确认保存长期记忆。",
            pending_action={
                "tool_name": "memory_upsert",
                "arguments": {
                    "memory_type": "preference",
                    "memory_key": "investment_style",
                    "memory_value": "长期高股息",
                    "confidence": 1.0,
                },
            },
        )

    monkeypatch.setattr(LangGraphChatAgent, "run", pending_memory)
    message = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": "记住我偏好长期高股息"},
    )
    assert (await client.get("/api/v1/memory", headers=headers)).json() == []

    confirmed = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/confirm/{message.json()['id']}",
        headers=headers,
    )
    assert confirmed.status_code == 200
    memories = (await client.get("/api/v1/memory", headers=headers)).json()
    assert len(memories) == 1
    assert memories[0]["memory_key"] == "investment_style"


@pytest.mark.asyncio
async def test_chat_stream_emits_tokens_and_persists_final_message(app_context, monkeypatch):
    client = app_context["client"]
    auth = await register(client, "stream")
    headers = auth_headers(auth)
    created = await client.post("/api/v1/chat/conversations", headers=headers)
    conversation_id = created.json()["id"]

    async def streamed(_runtime, _messages, on_token=None, on_event=None):
        assert on_token is not None
        assert on_event is not None
        on_event(
            "tool_started",
            {
                "id": "call-1",
                "phase": "tool_started",
                "status": "running",
                "tool_name": "market_quote",
            },
        )
        on_token("## 结论\n\n")
        on_event(
            "tool_completed",
            {
                "id": "call-1",
                "phase": "tool_completed",
                "status": "completed",
                "tool_name": "market_quote",
                "result": {"ok": True, "code": "600519"},
                "duration_ms": 12,
            },
        )
        on_token("谨慎观察")
        return AgentRunResult(answer="## 结论\n\n谨慎观察")

    monkeypatch.setattr(LangGraphChatAgent, "run", streamed)
    response = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages/stream",
        headers=headers,
        json={"content": "分析 600519"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: token" in response.text
    assert "event: tool_started" in response.text
    assert "event: tool_completed" in response.text
    assert "谨慎观察" in response.text
    assert "event: message" in response.text
    conversation = await client.get(
        f"/api/v1/chat/conversations/{conversation_id}", headers=headers
    )
    assert conversation.json()["messages"][-1]["content"] == "## 结论\n\n谨慎观察"
