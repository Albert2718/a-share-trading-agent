from __future__ import annotations

from typing import Any, Dict

import numpy as np

from src.tools.deep_research.tools import AkshareTools, LocalLSTMTool
from src.tools.deep_research.utils import normalize_a_share_code, safe_float


def predict_short_term_price(code: str) -> Dict[str, Any]:
    """Run the local LSTM model on the latest 14 closes and estimate next-step return."""
    norm = normalize_a_share_code(code)
    history = AkshareTools().history(norm, days=30)
    if len(history) < 14:
        return {"ok": False, "code": norm, "error": "history rows fewer than 14"}

    close = history["close"].astype(float)
    last_14_close = close.tail(14).to_numpy(dtype=np.float32)
    model = LocalLSTMTool()
    expected_return = model.predict_return(last_14_close)
    if expected_return is None:
        return {
            "ok": False,
            "code": norm,
            "date": str(history.iloc[-1]["date"]),
            "latest_close": safe_float(close.iloc[-1]),
            "model_path": str(model.model_path),
            "error": model.last_error or "local LSTM model unavailable or incompatible",
        }

    latest_close = float(close.iloc[-1])
    predicted_price = latest_close * (1.0 + expected_return)
    direction = "up" if expected_return > 0.002 else "down" if expected_return < -0.002 else "flat"
    confidence = min(0.75, 0.45 + abs(float(expected_return)) * 8)
    return {
        "ok": True,
        "code": norm,
        "date": str(history.iloc[-1]["date"]),
        "latest_close": safe_float(latest_close),
        "model_expected_return": safe_float(expected_return),
        "estimated_next_price": safe_float(predicted_price),
        "direction": direction,
        "confidence": safe_float(confidence),
        "lookback_days": 14,
        "source": "local_lstm_model",
        "note": "This is a local model estimate, not a guaranteed future price.",
    }
