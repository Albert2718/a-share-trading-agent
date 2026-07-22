import pytest
from decimal import Decimal

from conftest import auth_headers, register


@pytest.mark.asyncio
async def test_register_login_duplicate_username_and_protected_route(app_context):
    client = app_context["client"]
    auth = await register(client, "alpha")

    me = await client.get("/api/v1/auth/me", headers=auth_headers(auth))
    assert me.status_code == 200
    assert me.json()["username"] == "user_alpha"

    duplicate = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "other@example.com",
            "username": "user_alpha",
            "password": "password123",
        },
    )
    assert duplicate.status_code == 409
    assert "用户名" in duplicate.json()["detail"]

    unauthorized = await client.get("/api/v1/portfolio/positions")
    assert unauthorized.status_code == 401


@pytest.mark.asyncio
async def test_conversations_are_isolated_by_user(app_context):
    client = app_context["client"]
    first = await register(client, "first")
    second = await register(client, "second")

    created = await client.post(
        "/api/v1/chat/conversations", headers=auth_headers(first)
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    hidden = await client.get(
        f"/api/v1/chat/conversations/{conversation_id}",
        headers=auth_headers(second),
    )
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_business_resources_are_isolated_by_user(app_context):
    client = app_context["client"]
    first = await register(client, "owner")
    second = await register(client, "viewer")
    owner_headers = auth_headers(first)
    viewer_headers = auth_headers(second)

    position = await client.put(
        "/api/v1/portfolio/positions/600519",
        headers=owner_headers,
        json={
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "quantity": 10,
            "average_cost": 1400,
        },
    )
    memory = await client.post(
        "/api/v1/memory",
        headers=owner_headers,
        json={
            "memory_type": "preference",
            "memory_key": "style",
            "memory_value": "长期",
        },
    )
    research = await client.post(
        "/api/v1/research/jobs",
        headers=owner_headers,
        json={"stock_code": "600519", "depth": "quick", "risk_profile": "balanced"},
    )
    assert position.status_code == 200
    assert memory.status_code == 201
    assert research.status_code == 202

    upload = await client.post(
        "/api/v1/knowledge/documents",
        headers=owner_headers,
        files={"file": ("notes.txt", "仅供测试的投研资料", "text/plain")},
        data={"source_type": "personal_note", "stock_code": "600519"},
    )
    assert upload.status_code == 202, upload.text
    assert upload.json()["source_type"] == "personal_note"

    assert (await client.get("/api/v1/portfolio/positions", headers=viewer_headers)).json() == []
    assert (await client.get("/api/v1/memory", headers=viewer_headers)).json() == []
    assert (await client.get("/api/v1/research/jobs", headers=viewer_headers)).json() == []
    assert (await client.get("/api/v1/knowledge/documents", headers=viewer_headers)).json() == []
    assert len((await client.get("/api/v1/knowledge/documents", headers=owner_headers)).json()) == 1


@pytest.mark.asyncio
async def test_portfolio_positions_include_live_pnl_snapshot(app_context, monkeypatch):
    client = app_context["client"]
    auth = await register(client, "portfolio_snapshot")
    headers = auth_headers(auth)
    await client.put(
        "/api/v1/portfolio/positions/600519",
        headers=headers,
        json={
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "quantity": 10,
            "average_cost": 100,
        },
    )
    monkeypatch.setattr(
        "app.services.portfolio_service.get_realtime_price",
        lambda code: {
            "ok": True,
            "code": code,
            "name": "贵州茅台",
            "latest_price": 110,
            "quote_time": "2026-07-22T10:00:00",
            "is_realtime": True,
            "source": "test_quote",
        },
    )

    response = await client.get("/api/v1/portfolio/positions", headers=headers)

    assert response.status_code == 200
    snapshot = response.json()[0]
    assert Decimal(snapshot["market_price"]) == Decimal("110")
    assert Decimal(snapshot["market_value"]) == Decimal("1100")
    assert Decimal(snapshot["unrealized_pnl"]) == Decimal("100")
    assert Decimal(snapshot["pnl_pct"]) == Decimal("10")
    assert snapshot["is_realtime"] is True
