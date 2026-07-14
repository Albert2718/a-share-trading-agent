from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .workflow import run_chat_turn
from src.tools.personal import add_price_alert, update_user_preference


class ChatAgent:
    def __init__(self, session_id: Optional[str] = None, max_history_messages: int = 20):
        self.session_id = session_id or "cli"
        self.max_history_messages = max_history_messages
        self.history: List[Dict[str, Any]] = []
        self.last_state: Dict[str, Any] = {}
        self.last_tool_results: List[Dict[str, Any]] = []

    def run(self, user_input: str) -> str:
        deterministic = self._try_memory_write(user_input)
        if deterministic is not None:
            return deterministic
        state = run_chat_turn(user_input, session_id=self.session_id, history=self.history[-self.max_history_messages :])
        self.last_state = dict(state)
        self.last_tool_results = list(state.get("tool_results", []))
        self.history = _compact_history(state.get("messages", []), self.max_history_messages)
        answer = state.get("final_answer", "")
        return answer or "我没有得到可用回答。"

    def _try_memory_write(self, user_input: str) -> Optional[str]:
        alert_answer = self._try_price_alert(user_input)
        if alert_answer is not None:
            return alert_answer
        preference_answer = self._try_preference(user_input)
        if preference_answer is not None:
            return preference_answer
        return None

    def _try_price_alert(self, text: str) -> Optional[str]:
        if "提醒" not in text:
            return None
        match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]+?)(涨到|超过|高于|跌到|低于|跌破)\s*([0-9]+(?:\.[0-9]+)?)\s*元?", text)
        if not match:
            return None
        stock, action, price = match.groups()
        stock = _clean_stock_query(stock)
        operator = ">=" if action in {"涨到", "超过", "高于"} else "<="
        result = add_price_alert(stock, operator, float(price), note=text)
        self.last_tool_results = [{"name": "add_price_alert", "arguments": {"code_or_name": stock, "operator": operator, "target_price": float(price), "note": text}, "result": result}]
        if not result.get("ok"):
            return f"价格预警记录失败：{result.get('error', 'unknown error')}"
        alert = result["alert"]
        return (
            f"已记录价格预警：{alert.get('name')}（{alert.get('code')}）"
            f"{alert.get('operator')} {alert.get('target_price')} 元。\n\n"
            "当前版本会把预警保存在本地记忆里；要做到自动推送，还需要后台监控进程持续检查价格。"
        )

    def _try_preference(self, text: str) -> Optional[str]:
        preference_terms = ["保守", "稳健", "激进", "高股息", "分红", "成长", "价值", "短线", "长线", "只喜欢", "偏好", "不喜欢", "回避"]
        if not any(term in text for term in preference_terms):
            return None
        if not any(marker in text for marker in ["我是", "我偏好", "我喜欢", "只喜欢", "不喜欢", "回避"]):
            return None
        risk_profile = None
        if "保守" in text or "稳健" in text:
            risk_profile = "conservative"
        elif "激进" in text:
            risk_profile = "aggressive"
        investment_style = None
        if "高股息" in text or "分红" in text:
            investment_style = "高股息"
        elif "成长" in text:
            investment_style = "成长"
        elif "价值" in text:
            investment_style = "价值"
        elif "短线" in text:
            investment_style = "短线"
        elif "长线" in text:
            investment_style = "长线"
        result = update_user_preference(risk_profile=risk_profile, investment_style=investment_style, notes=text)
        self.last_tool_results = [{"name": "update_user_preference", "arguments": {"risk_profile": risk_profile, "investment_style": investment_style, "notes": text}, "result": result}]
        if not result.get("ok"):
            return f"投资偏好记录失败：{result.get('error', 'unknown error')}"
        prefs = result.get("preferences", {})
        return (
            "已记录您的投资偏好：\n\n"
            f"- 风险偏好：{prefs.get('risk_profile') or '未指定'}\n"
            f"- 投资风格：{prefs.get('investment_style') or '未指定'}\n"
            f"- 备注：{prefs.get('notes') or text}"
        )


def _compact_history(messages: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    keep: List[Dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "user":
            keep.append({"role": "user", "content": message.get("content", "")})
        elif role == "assistant" and not message.get("tool_calls"):
            content = message.get("content", "")
            if content:
                keep.append({"role": "assistant", "content": content})
    return keep[-limit:]


def _clean_stock_query(text: str) -> str:
    cleaned = str(text or "").strip()
    for prefix in ["如果", "当", "请", "帮我", "给我"]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
    return cleaned.strip()
