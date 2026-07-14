from __future__ import annotations

from typing import Dict

import numpy as np

from src.tools.market_data import AkshareMarketData
from src.tools.utils import normalize_a_share_code, safe_float


def get_technical_indicators(code: str) -> Dict:
    """Calculate common technical indicators from daily close prices."""
    norm = normalize_a_share_code(code)
    history = AkshareMarketData().history(norm, days=120)
    if len(history) < 35:
        return {"ok": False, "code": norm, "error": "history rows fewer than 35"}

    close = history["close"].astype(float)
    high = history["high"].astype(float)
    low = history["low"].astype(float)

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs.iloc[-1]))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd_hist = dif.iloc[-1] - dea.iloc[-1]

    low_min = low.rolling(9).min()
    high_max = high.rolling(9).max()
    rsv = (close - low_min) / (high_max - low_min) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d

    boll_mid = close.rolling(20).mean()
    boll_std = close.rolling(20).std()
    latest_close = close.iloc[-1]
    return {
        "ok": True,
        "code": norm,
        "date": str(history.iloc[-1]["date"]),
        "latest_close": safe_float(latest_close),
        "macd": {
            "dif": safe_float(dif.iloc[-1]),
            "dea": safe_float(dea.iloc[-1]),
            "hist": safe_float(macd_hist),
            "signal": "bullish" if macd_hist > 0 else "bearish",
        },
        "rsi_14": safe_float(rsi),
        "kdj": {"k": safe_float(k.iloc[-1]), "d": safe_float(d.iloc[-1]), "j": safe_float(j.iloc[-1])},
        "boll": {
            "upper": safe_float(boll_mid.iloc[-1] + 2 * boll_std.iloc[-1]),
            "mid": safe_float(boll_mid.iloc[-1]),
            "lower": safe_float(boll_mid.iloc[-1] - 2 * boll_std.iloc[-1]),
        },
        "source": "akshare_history_calculated",
    }
