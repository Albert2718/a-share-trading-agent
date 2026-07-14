from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from src.core import UserMemoryStore
from src.tools.financial import get_stock_basic
from src.tools.market import get_realtime_price
from src.tools.deep_research.utils import normalize_a_share_code, safe_float


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _resolve_stock(code_or_name: str) -> Dict[str, Any]:
    basic = get_stock_basic(code_or_name)
    if basic.get("ok") and basic.get("code"):
        return {"ok": True, "code": basic.get("code"), "name": basic.get("name") or ""}
    matches = basic.get("matches") or []
    if matches:
        first = matches[0]
        return {"ok": True, "code": first.get("code"), "name": first.get("name") or ""}
    return {"ok": False, "error": basic.get("error") or "stock not found", "raw": basic}


def add_portfolio_position(code_or_name: str, quantity: float, cost_price: float, note: str | None = None) -> Dict[str, Any]:
    """Add or merge a portfolio position in local memory."""
    resolved = _resolve_stock(code_or_name)
    if not resolved.get("ok"):
        return {"ok": False, "error": resolved.get("error"), "source": "local_memory"}

    quantity_value = safe_float(quantity)
    cost_value = safe_float(cost_price)
    if quantity_value is None or quantity_value <= 0 or cost_value is None or cost_value <= 0:
        return {"ok": False, "error": "quantity and cost_price must be positive", "source": "local_memory"}

    code = normalize_a_share_code(str(resolved["code"]))
    store = UserMemoryStore()
    data = store.load()
    portfolio: List[Dict[str, Any]] = list(data.get("portfolio", []))

    existing = next((item for item in portfolio if normalize_a_share_code(str(item.get("code"))) == code), None)
    if existing:
        old_qty = safe_float(existing.get("quantity")) or 0.0
        old_cost = safe_float(existing.get("cost_price")) or 0.0
        new_qty = old_qty + quantity_value
        avg_cost = ((old_qty * old_cost) + (quantity_value * cost_value)) / new_qty if new_qty else cost_value
        existing.update(
            {
                "code": code,
                "name": resolved.get("name") or existing.get("name") or "",
                "quantity": new_qty,
                "cost_price": avg_cost,
                "note": note if note is not None else existing.get("note"),
                "updated_at": _now(),
            }
        )
        position = existing
    else:
        position = {
            "code": code,
            "name": resolved.get("name") or "",
            "quantity": quantity_value,
            "cost_price": cost_value,
            "note": note or "",
            "created_at": _now(),
            "updated_at": _now(),
        }
        portfolio.append(position)

    data["portfolio"] = portfolio
    path = store.save(data)
    return {"ok": True, "position": position, "memory_path": str(path), "source": "local_memory"}


def remove_portfolio_position(code_or_name: str, quantity: float | None = None) -> Dict[str, Any]:
    """Remove all or part of a portfolio position."""
    resolved = _resolve_stock(code_or_name)
    if not resolved.get("ok"):
        return {"ok": False, "error": resolved.get("error"), "source": "local_memory"}

    code = normalize_a_share_code(str(resolved["code"]))
    store = UserMemoryStore()
    data = store.load()
    portfolio: List[Dict[str, Any]] = list(data.get("portfolio", []))
    existing = next((item for item in portfolio if normalize_a_share_code(str(item.get("code"))) == code), None)
    if not existing:
        return {"ok": False, "code": code, "error": "position not found", "source": "local_memory"}

    qty_to_remove = safe_float(quantity)
    current_qty = safe_float(existing.get("quantity")) or 0.0
    if qty_to_remove is None or qty_to_remove >= current_qty:
        portfolio = [item for item in portfolio if normalize_a_share_code(str(item.get("code"))) != code]
        removed = current_qty
    elif qty_to_remove <= 0:
        return {"ok": False, "error": "quantity must be positive", "source": "local_memory"}
    else:
        existing["quantity"] = current_qty - qty_to_remove
        existing["updated_at"] = _now()
        removed = qty_to_remove

    data["portfolio"] = portfolio
    path = store.save(data)
    return {"ok": True, "code": code, "removed_quantity": removed, "memory_path": str(path), "source": "local_memory"}


def get_portfolio_status() -> Dict[str, Any]:
    """Return portfolio positions with current mark-to-market values."""
    store = UserMemoryStore()
    portfolio = store.portfolio()
    positions = []
    total_cost = 0.0
    total_market_value = 0.0
    errors = []

    for item in portfolio:
        code = normalize_a_share_code(str(item.get("code")))
        quantity = safe_float(item.get("quantity")) or 0.0
        cost_price = safe_float(item.get("cost_price")) or 0.0
        cost_value = quantity * cost_price
        price_data = get_realtime_price(code)
        latest_price = safe_float(price_data.get("latest_close")) if price_data.get("ok") else None
        if latest_price is None:
            errors.append({"code": code, "error": price_data.get("error") or "price unavailable"})
            market_value = None
            pnl = None
            pnl_pct = None
        else:
            market_value = quantity * latest_price
            pnl = market_value - cost_value
            pnl_pct = pnl / cost_value if cost_value else None
            total_market_value += market_value
        total_cost += cost_value
        positions.append(
            {
                "code": code,
                "name": item.get("name") or price_data.get("name") or "",
                "quantity": quantity,
                "cost_price": cost_price,
                "latest_price": latest_price,
                "cost_value": cost_value,
                "market_value": market_value,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "price_date": price_data.get("date"),
                "note": item.get("note") or "",
            }
        )

    total_pnl = total_market_value - total_cost if total_market_value else None
    total_pnl_pct = total_pnl / total_cost if total_pnl is not None and total_cost else None
    return {
        "ok": True,
        "positions": positions,
        "summary": {
            "total_cost": total_cost,
            "total_market_value": total_market_value if positions else 0.0,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "position_count": len(positions),
        },
        "errors": errors,
        "source": "local_memory_with_akshare_price",
    }


def update_user_preference(
    risk_profile: str | None = None,
    investment_style: str | None = None,
    favorite_sectors: str | None = None,
    avoid_sectors: str | None = None,
    notes: str | None = None,
) -> Dict[str, Any]:
    """Persist user investment preferences."""
    store = UserMemoryStore()
    data = store.load()
    preferences = dict(data.get("preferences", {}))
    updates = {
        "risk_profile": risk_profile,
        "investment_style": investment_style,
        "favorite_sectors": favorite_sectors,
        "avoid_sectors": avoid_sectors,
        "notes": notes,
    }
    for key, value in updates.items():
        if value not in (None, ""):
            preferences[key] = value
    preferences["updated_at"] = _now()
    data["preferences"] = preferences
    path = store.save(data)
    return {"ok": True, "preferences": preferences, "memory_path": str(path), "source": "local_memory"}


def get_user_preference() -> Dict[str, Any]:
    """Return persisted user investment preferences."""
    return {"ok": True, "preferences": UserMemoryStore().preferences(), "source": "local_memory"}


def add_price_alert(code_or_name: str, operator: str, target_price: float, note: str | None = None) -> Dict[str, Any]:
    """Persist a price alert. This records the alert; it does not start a background monitor."""
    resolved = _resolve_stock(code_or_name)
    if not resolved.get("ok"):
        return {"ok": False, "error": resolved.get("error"), "source": "local_memory"}
    op = str(operator or "").strip()
    if op not in {">", ">=", "<", "<="}:
        return {"ok": False, "error": "operator must be one of >, >=, <, <=", "source": "local_memory"}
    target = safe_float(target_price)
    if target is None or target <= 0:
        return {"ok": False, "error": "target_price must be positive", "source": "local_memory"}

    store = UserMemoryStore()
    data = store.load()
    alerts = list(data.get("alerts", []))
    alert = {
        "id": f"alert_{len(alerts) + 1}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "code": normalize_a_share_code(str(resolved["code"])),
        "name": resolved.get("name") or "",
        "operator": op,
        "target_price": target,
        "note": note or "",
        "active": True,
        "created_at": _now(),
    }
    alerts.append(alert)
    data["alerts"] = alerts
    path = store.save(data)
    return {
        "ok": True,
        "alert": alert,
        "memory_path": str(path),
        "source": "local_memory",
        "note": "Alert is stored locally. A background monitor is needed to send proactive notifications.",
    }


def list_price_alerts(active_only: bool = True) -> Dict[str, Any]:
    """Return stored price alerts."""
    alerts = UserMemoryStore().alerts()
    if active_only:
        alerts = [alert for alert in alerts if alert.get("active", True)]
    return {"ok": True, "alerts": alerts, "source": "local_memory"}
