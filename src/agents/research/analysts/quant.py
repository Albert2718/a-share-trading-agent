from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from ..schemas import AnalysisContext, QuantReport, StockCandidate
from src.tools.lstm import LSTMPredictor
from src.tools.market_data import AkshareMarketData
from src.tools.utils import clamp


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "lstm_training" / "lstm_model.pt"
DEFAULT_FALLBACK_DATA_PATH = PROJECT_ROOT / "lstm_training" / "train_data.npy"


class QuantAnalyst:
    def __init__(
        self,
        akshare_tools: AkshareMarketData | None = None,
        model_tool: LSTMPredictor | None = None,
        model_path: str | Path = DEFAULT_MODEL_PATH,
        fallback_data_path: str | Path = DEFAULT_FALLBACK_DATA_PATH,
    ):
        self.akshare_tools = akshare_tools or AkshareMarketData()
        self.model_tool = model_tool or LSTMPredictor(model_path)
        self.fallback_data_path = Path(fallback_data_path)

    def analyze(self, candidate: StockCandidate, context: AnalysisContext) -> QuantReport:
        try:
            history = self._history(candidate.code, context.history_days)
            if len(history) < 20:
                return QuantReport(
                    code=candidate.code,
                    name=candidate.name,
                    status="data_insufficient",
                    error="history rows fewer than 20",
                )
            return self._build_report(candidate, history)
        except Exception as exc:
            return QuantReport(code=candidate.code, name=candidate.name, status="error", error=str(exc))

    def _history(self, code: str, days: int) -> pd.DataFrame:
        try:
            history = self.akshare_tools.history(code, days=days)
            if len(history) >= 20:
                return history
            raise RuntimeError(f"history rows fewer than 20: {len(history)}")
        except Exception as exc:
            raise RuntimeError(f"real market history unavailable: {exc}") from exc

    def _fallback_history(self, days: int) -> pd.DataFrame:
        if not self.fallback_data_path.exists():
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        values = np.load(self.fallback_data_path).astype(float).reshape(-1)[-days:]
        dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=len(values), freq="B")
        return pd.DataFrame(
            {
                "date": dates.strftime("%Y-%m-%d"),
                "open": values,
                "high": values,
                "low": values,
                "close": values,
                "volume": np.ones(len(values), dtype=float),
            }
        )

    def _build_report(self, candidate: StockCandidate, history: pd.DataFrame) -> QuantReport:
        close = history["close"].astype(float)
        volume = history["volume"].astype(float).replace(0, np.nan)
        latest_close = float(close.iloc[-1])
        ret_5 = self._period_return(close, 5)
        ret_20 = self._period_return(close, 20)
        volatility_20 = float(close.pct_change().tail(20).std() or 0.0)
        volume_ratio = self._volume_ratio(volume)
        rsi_14 = self._rsi(close, 14)
        macd_hist = self._macd_hist(close)
        model_return = self.model_tool.predict_return(close.tail(14).to_numpy(dtype=np.float32))

        score = 50.0
        factors = []
        risks = []

        ma5 = float(close.tail(5).mean())
        ma10 = float(close.tail(10).mean())
        ma20 = float(close.tail(20).mean())
        if latest_close > ma5 > ma10 > ma20:
            score += 14
            factors.append("MA bullish alignment")
        elif latest_close < ma5 < ma10 < ma20:
            score -= 14
            factors.append("MA bearish alignment")

        if ret_5 is not None:
            score += clamp(ret_5 * 180, -12, 12)
            factors.append(f"5d return {ret_5 * 100:.2f}%")
        if ret_20 is not None:
            score += clamp(ret_20 * 120, -12, 12)
            factors.append(f"20d return {ret_20 * 100:.2f}%")
        if volume_ratio is not None and volume_ratio > 1.5:
            score += 6
            factors.append(f"volume expansion {volume_ratio:.2f}x")
        if rsi_14 is not None:
            if rsi_14 > 75:
                score -= 8
                risks.append("RSI overbought")
            elif rsi_14 < 30:
                score -= 3
                risks.append("RSI weak")
        if macd_hist is not None:
            score += 5 if macd_hist > 0 else -5
            factors.append("MACD histogram positive" if macd_hist > 0 else "MACD histogram negative")
        if model_return is not None:
            score += clamp(model_return * 500, -10, 10)
            factors.append(f"14d LSTM expected return {model_return * 100:.2f}%")
        if volatility_20 > 0.04:
            score -= 8
            risks.append("20d volatility elevated")
        if ret_5 is not None and ret_5 > 0.18:
            score -= 6
            risks.append("short-term rise is extended")

        final_score = int(round(clamp(score, 0, 100)))
        trend = "bullish" if final_score >= 65 else "bearish" if final_score <= 40 else "neutral"
        return QuantReport(
            code=candidate.code,
            name=candidate.name,
            quant_score=final_score,
            trend=trend,
            model_expected_return=model_return,
            latest_close=latest_close,
            return_5d=ret_5,
            return_20d=ret_20,
            volatility_20d=volatility_20,
            volume_ratio=volume_ratio,
            rsi_14=rsi_14,
            macd_hist=macd_hist,
            key_factors=factors[:8],
            risk_flags=risks,
        )

    def _period_return(self, close: pd.Series, days: int) -> Optional[float]:
        if len(close) <= days:
            return None
        base = float(close.iloc[-days - 1])
        if abs(base) < 1e-9:
            return None
        return float(close.iloc[-1] / base - 1.0)

    def _volume_ratio(self, volume: pd.Series) -> Optional[float]:
        if len(volume) < 20:
            return None
        recent = volume.tail(5).mean()
        base = volume.tail(20).mean()
        if not np.isfinite(recent) or not np.isfinite(base) or base <= 0:
            return None
        return float(recent / base)

    def _rsi(self, close: pd.Series, period: int) -> Optional[float]:
        if len(close) <= period:
            return None
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        value = 100 - (100 / (1 + rs.iloc[-1]))
        return float(value) if np.isfinite(value) else None

    def _macd_hist(self, close: pd.Series) -> Optional[float]:
        if len(close) < 35:
            return None
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        hist = dif.iloc[-1] - dea.iloc[-1]
        return float(hist) if np.isfinite(hist) else None
