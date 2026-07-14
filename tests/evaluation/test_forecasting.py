from __future__ import annotations

import math
import json
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from src.agents.research.schemas import FinalReport, StockDecision
from src.evaluation.forecasting import EvaluationForecaster, ResearchDraft, blend_forecast
from src.evaluation.models import StockPoolEntry


AS_OF = date(2026, 7, 14)
TARGET = date(2026, 7, 15)
GENERATED_AT = datetime(2026, 7, 14, 18, 30, tzinfo=timezone(timedelta(hours=8)))
ENTRY = StockPoolEntry(code="600519", name="贵州茅台", industry="白酒", rule_version="1.0")


def valid_llm_response(**overrides):
    payload = {
        "expected_return": 0.02,
        "interval_low_return": -0.01,
        "interval_high_return": 0.04,
        "confidence": 0.7,
        "company_trend": "经营稳健",
        "industry_trend": "需求平稳",
        "core_thesis": ["盈利能力稳定"],
        "catalysts": ["旺季需求"],
        "risks": ["估值偏高"],
    }
    payload.update(overrides)
    return payload


class FakeLLM:
    def __init__(
        self,
        response=None,
        *,
        model="injected-evaluation-model",
        base_url="https://api.example.com/v1",
    ):
        self.response = valid_llm_response() if response is None else response
        self.model = model
        self.base_url = base_url
        self.payload = None
        self.calls = []

    def structured(self, **kwargs):
        self.calls.append(kwargs)
        self.payload = kwargs["user_payload"]
        if isinstance(self.response, list):
            return self.response.pop(0)
        return self.response


class FakeOrchestrator:
    def __init__(self, news_time="2026-07-14T17:00:00+08:00"):
        self.calls = []
        self.news = SimpleNamespace(
            llm_client=SimpleNamespace(model="injected-research-news-model"),
            news_agent_model="configured-research-news-model",
        )
        self.cio = SimpleNamespace(
            llm_client=SimpleNamespace(model="injected-research-cio-model"),
            model="configured-research-cio-model",
        )
        self.decision = StockDecision(
            code="600519",
            name="贵州茅台",
            action="watch",
            confidence=0.6,
            rank_score=65,
            position_bias="5%",
            reason="量化与基本面综合判断",
            top_reasons=["LSTM model expected return is positive", "盈利稳定"],
            risk_flags=["估值偏高"],
            invalidation_conditions=["需求下降"],
            quant={
                "code": "600519",
                "status": "ok",
                "latest_close": 100.0,
                "volatility_20d": 0.02,
                "model_expected_return": 0.03,
                "key_factors": ["LSTM expected return +3.0%", "20日趋势向上"],
                "risk_flags": [],
            },
            fundamental={"code": "600519", "status": "ok", "key_factors": ["盈利稳定"]},
            news={
                "code": "600519",
                "status": "ok",
                "events": [
                    {
                        "summary": "渠道反馈",
                        "published_at": news_time,
                        "source": "测试新闻",
                        "sentiment": "positive",
                        "severity": "medium",
                    }
                ],
            },
            sentiment={"code": "600519", "status": "ok", "sentiment_score": 10},
        )

    def analyze(self, candidates, context, mode="single", **kwargs):
        self.calls.append({
            "candidates": candidates,
            "context": context,
            "mode": mode,
            **kwargs,
        })
        return FinalReport(
            generated_at=GENERATED_AT.isoformat(),
            mode=mode,
            all_decisions=[self.decision],
        )


class FakeMarketData:
    def __init__(
        self,
        *,
        latest_date=AS_OF,
        empty=False,
        volatility=0.02,
        date_defect=None,
    ):
        self.calls = []
        self.latest_date = latest_date
        self.empty = empty
        self.volatility = volatility
        self.date_defect = date_defect

    def raw_history(self, code, days, end_date):
        self.calls.append({"code": code, "days": days, "end_date": end_date})
        if self.empty:
            return pd.DataFrame(columns=["date", "close", "volume"])
        returns = [self.volatility if index % 2 else -self.volatility for index in range(29)]
        closes = [100.0]
        for value in returns:
            closes.append(closes[-1] * (1.0 + value))
        scale = 100.0 / closes[-1]
        closes = [value * scale for value in closes]
        start = self.latest_date - timedelta(days=len(closes) - 1)
        frame = pd.DataFrame({
            "date": [start + timedelta(days=index) for index in range(len(closes))],
            "close": closes,
            "volume": [1000.0] * len(closes),
        })
        if self.date_defect == "invalid":
            frame.loc[5, "date"] = "not-a-date"
        elif self.date_defect == "duplicate":
            frame.loc[5, "date"] = frame.loc[4, "date"]
        elif self.date_defect == "duplicate_day":
            frame.loc[5, "date"] = datetime.combine(
                frame.loc[4, "date"],
                datetime.min.time(),
                tzinfo=timezone.utc,
            ) + timedelta(hours=12)
        elif self.date_defect == "unsorted":
            frame.loc[4, "date"], frame.loc[5, "date"] = (
                frame.loc[5, "date"],
                frame.loc[4, "date"],
            )
        elif self.date_defect == "future":
            frame.loc[5, "date"] = self.latest_date + timedelta(days=1)
        return frame


class FakeLSTM:
    def __init__(self, value=-0.01, model_path="fake-lstm.pt"):
        self.value = value
        self.model_path = Path(model_path)
        self.calls = []

    def predict_return(self, close):
        self.calls.append(close.copy())
        return self.value


def make_forecaster(
    *,
    news_time="2026-07-14T17:00:00+08:00",
    llm_response=None,
    lstm_return=-0.01,
    market_data=None,
    model_path="fake-lstm.pt",
    model_id=None,
    provider=None,
    llm=None,
):
    llm = llm or FakeLLM(llm_response)
    orchestrator = FakeOrchestrator(news_time=news_time)
    forecaster = EvaluationForecaster(
        orchestrator=orchestrator,
        llm_client=llm,
        market_data=market_data or FakeMarketData(),
        lstm_predictor=FakeLSTM(lstm_return, model_path=model_path),
        model_id=model_id,
        provider=provider,
    )
    return forecaster, llm, orchestrator


class FusionTests(unittest.TestCase):
    def test_lstm_has_exactly_fifteen_percent_influence(self):
        result = blend_forecast(
            draft=ResearchDraft(
                expected_return=0.02,
                interval_low_return=-0.01,
                interval_high_return=0.04,
                confidence=0.7,
            ),
            lstm_return=-0.01,
            current_close=100.0,
            volatility=0.02,
            horizon_days=1,
            code="600519",
        )

        self.assertAlmostEqual(result.expected_return, 0.0155)
        self.assertAlmostEqual(result.predicted_close, 101.55)
        self.assertEqual(result.direction, "up")

    def test_lstm_unavailable_uses_research_return_unchanged(self):
        result = blend_forecast(
            ResearchDraft(0.02, -0.01, 0.04, 0.7),
            None,
            current_close=100.0,
            volatility=0.02,
            horizon_days=1,
            code="600519",
        )

        self.assertAlmostEqual(result.expected_return, 0.02)

    def test_central_price_is_always_inside_interval(self):
        result = blend_forecast(
            ResearchDraft(0.04, 0.05, 0.06, 0.7),
            None,
            current_close=100.0,
            volatility=0.02,
            horizon_days=1,
            code="600519",
        )

        self.assertLessEqual(result.interval_low, result.predicted_close)
        self.assertLessEqual(result.predicted_close, result.interval_high)

    def test_main_board_next_day_return_is_capped_at_ten_percent(self):
        result = blend_forecast(
            ResearchDraft(0.50, -0.50, 0.50, 0.7),
            None,
            current_close=100.0,
            volatility=0.20,
            horizon_days=1,
            code="600519",
        )

        self.assertAlmostEqual(result.expected_return, 0.10)
        self.assertAlmostEqual(result.interval_low, 90.0)
        self.assertAlmostEqual(result.interval_high, 110.0)

    def test_chinext_and_star_next_day_returns_are_capped_at_twenty_percent(self):
        for code in ("300750", "688981"):
            with self.subTest(code=code):
                result = blend_forecast(
                    ResearchDraft(-0.50, -0.50, 0.50, 0.7),
                    None,
                    current_close=100.0,
                    volatility=0.20,
                    horizon_days=1,
                    code=code,
                )
                self.assertAlmostEqual(result.expected_return, -0.20)

    def test_stage_cap_scales_with_volatility_and_square_root_horizon(self):
        result = blend_forecast(
            ResearchDraft(0.50, -0.50, 0.50, 0.7),
            None,
            current_close=100.0,
            volatility=0.01,
            horizon_days=9,
            code="600519",
        )

        self.assertAlmostEqual(result.expected_return, 2.5 * 0.01 * math.sqrt(9))

    def test_zero_return_still_derives_a_binary_direction(self):
        result = blend_forecast(
            ResearchDraft(0.0, 0.0, 0.0, 0.5),
            None,
            current_close=100.0,
            volatility=0.02,
            horizon_days=1,
            code="600519",
        )

        self.assertIn(result.direction, {"up", "down"})


class ForecastingTests(unittest.TestCase):
    def test_future_news_is_removed_before_llm_call(self):
        forecaster, llm, _ = make_forecaster(news_time="2026-07-14T19:00:00+08:00")

        record = forecaster.forecast(
            ENTRY, AS_OF, TARGET, "next_day", generated_at=GENERATED_AT
        )

        self.assertEqual(llm.payload["reports"]["news"]["events"], [])
        self.assertIn("news_after_cutoff", llm.payload["warnings"])
        self.assertIn("news_after_cutoff", record.warnings)
        cio_evidence = next(
            item for item in record.evidence if item.evidence_type == "cio_decision"
        )
        self.assertEqual(
            cio_evidence.metadata["decision"]["news"]["events"], ()
        )

    def test_news_without_verifiable_timestamp_is_removed(self):
        forecaster, llm, _ = make_forecaster(news_time="")

        record = forecaster.forecast(
            ENTRY, AS_OF, TARGET, "next_day", generated_at=GENERATED_AT
        )

        self.assertEqual(llm.payload["reports"]["news"]["events"], [])
        self.assertIn("news_timestamp_unverifiable", record.warnings)

    def test_residual_lstm_values_are_removed_from_payload_and_persisted_research(self):
        forecaster, llm, orchestrator = make_forecaster()
        orchestrator.decision.quant.update({
            "error": "LSTM predicted return leaked through error",
            "risk_flags": ["model prediction disagrees with trend"],
            "nested": {
                "model_prediction": {"expected_return": 0.99},
                "notes": ["auxiliary LSTM model forecast should be hidden"],
            },
        })
        orchestrator.decision.fundamental.update({
            "risk_flags": ["derived from LSTM model output"],
            "nested": [
                {"prediction_source": "model_prediction"},
                {"aux_model_prediction_details": {"return": "模型预测收益率 90%"}},
            ],
        })
        orchestrator.decision.news.update({
            "error": "news report mentions lstm-derived score",
            "risk_flags": ["模型预测显示上涨"],
        })
        orchestrator.decision.risk_flags.append("模型预测收益率 90%")
        orchestrator.decision.top_reasons.append("aux_model_prediction_details indicates upside")

        record = forecaster.forecast(
            ENTRY, AS_OF, TARGET, "next_day", generated_at=GENERATED_AT
        )

        quant_payload = llm.payload["reports"]["quant"]
        self.assertNotIn("model_expected_return", quant_payload)
        serialized_payload = json.dumps(llm.payload["reports"], ensure_ascii=False).lower()
        for forbidden in (
            "lstm",
            "model_prediction",
            "aux_model_prediction_details",
            "model expected",
            "predicted return",
            "模型预测",
            "预测收益率",
        ):
            self.assertNotIn(forbidden, serialized_payload)
        quant_evidence = next(
            item for item in record.evidence if item.source == "research:quant"
        )
        self.assertNotIn("model_expected_return", quant_evidence.metadata["report"])
        self.assertNotIn("lstm", str(quant_evidence.metadata).lower())
        cio_evidence = next(
            item for item in record.evidence if item.evidence_type == "cio_decision"
        )
        serialized_cio = json.dumps(cio_evidence.to_dict(), ensure_ascii=False).lower()
        for forbidden in ("lstm", "model_prediction", "aux_model_prediction_details", "模型预测", "预测收益率"):
            self.assertNotIn(forbidden, serialized_cio)

    def test_lstm_unavailable_adds_warning_and_preserves_research_forecast(self):
        forecaster, _, _ = make_forecaster(lstm_return=None)

        record = forecaster.forecast(
            ENTRY, AS_OF, TARGET, "next_day", generated_at=GENERATED_AT
        )

        self.assertAlmostEqual(record.agent.expected_return, 0.02)
        self.assertIn("lstm_unavailable", record.warnings)
        self.assertEqual(record.lstm.confidence, 0.0)

    def test_malformed_llm_output_is_rejected(self):
        forecaster, _, _ = make_forecaster(llm_response={"expected_return": "invalid"})

        with self.assertRaisesRegex(RuntimeError, "malformed structured forecast"):
            forecaster.forecast(
                ENTRY, AS_OF, TARGET, "next_day", generated_at=GENERATED_AT
            )

    def test_malformed_llm_output_is_retried_once(self):
        forecaster, llm, _ = make_forecaster(
            llm_response=[{"expected_return": "invalid"}, valid_llm_response()]
        )

        record = forecaster.forecast(
            ENTRY, AS_OF, TARGET, "next_day", generated_at=GENERATED_AT
        )

        self.assertEqual(record.code, ENTRY.code)
        self.assertEqual(len(llm.calls), 2)

    def test_forecast_uses_full_research_context_and_exact_as_of_history(self):
        forecaster, _, orchestrator = make_forecaster()

        forecaster.forecast(
            ENTRY, AS_OF, TARGET, "next_day", generated_at=GENERATED_AT
        )

        call = orchestrator.calls[0]
        self.assertEqual([candidate.code for candidate in call["candidates"]], [ENTRY.code])
        self.assertEqual(call["mode"], "single")
        self.assertEqual(call["context"].depth, "full")
        self.assertEqual(call["context"].risk_profile, "balanced")
        self.assertTrue(call["context"].use_llm)
        self.assertEqual(call["context"].as_of, AS_OF.isoformat())
        self.assertEqual(call["context"].cutoff_at, GENERATED_AT.isoformat())
        self.assertFalse(call["context"].include_model_signal)
        self.assertEqual(call["context"].history_days, 250)
        self.assertEqual(
            forecaster.market_data.calls,
            [{"code": ENTRY.code, "days": 250, "end_date": AS_OF}],
        )

    def test_next_day_forecast_uses_one_day_cap_across_calendar_gap(self):
        response = valid_llm_response(
            expected_return=0.50,
            interval_low_return=-0.50,
            interval_high_return=0.50,
        )
        forecaster, _, _ = make_forecaster(
            llm_response=response,
            lstm_return=None,
            market_data=FakeMarketData(volatility=0.20),
        )

        record = forecaster.forecast(
            ENTRY,
            AS_OF,
            date(2026, 7, 17),
            "next_day",
            generated_at=GENERATED_AT,
        )

        self.assertAlmostEqual(record.agent.expected_return, 0.10)

    def test_next_day_record_omits_stage_narrative_fields(self):
        forecaster, _, _ = make_forecaster()

        record = forecaster.forecast(
            ENTRY, AS_OF, TARGET, "next_day", generated_at=GENERATED_AT
        )

        self.assertIsNone(record.stage_direction)
        self.assertIsNone(record.stage_target_price)
        self.assertIsNone(record.stage_interval_low)
        self.assertIsNone(record.stage_interval_high)
        self.assertIsNone(record.stage_confidence)
        self.assertIsNone(record.stage_thesis)
        self.assertEqual(record.catalysts, ())
        self.assertEqual(record.risks, ())

    def test_missing_or_stale_history_is_rejected_before_forecast(self):
        for market_data in (
            FakeMarketData(empty=True),
            FakeMarketData(latest_date=date(2026, 7, 13)),
        ):
            with self.subTest(latest_date=market_data.latest_date, empty=market_data.empty):
                forecaster, _, _ = make_forecaster(market_data=market_data)
                with self.assertRaisesRegex(RuntimeError, "history"):
                    forecaster.forecast(
                        ENTRY, AS_OF, TARGET, "next_day", generated_at=GENERATED_AT
                    )

    def test_history_rejects_invalid_duplicate_unsorted_and_future_dates(self):
        for defect in ("invalid", "duplicate", "duplicate_day", "unsorted", "future"):
            with self.subTest(defect=defect):
                forecaster, _, _ = make_forecaster(
                    market_data=FakeMarketData(date_defect=defect)
                )
                with self.assertRaisesRegex(RuntimeError, "history"):
                    forecaster.forecast(
                        ENTRY, AS_OF, TARGET, "next_day", generated_at=GENERATED_AT
                    )

    def test_generated_at_must_have_same_local_date_as_as_of(self):
        forecaster, _, orchestrator = make_forecaster()

        with self.assertRaisesRegex(ValueError, "generated_at local date"):
            forecaster.forecast(
                ENTRY,
                AS_OF,
                TARGET,
                "next_day",
                generated_at="2026-07-13T23:59:00+08:00",
            )

        self.assertEqual(orchestrator.calls, [])

    def test_injected_models_and_sanitized_provider_are_recorded(self):
        llm = FakeLLM(
            model="injected-evaluation-model",
            base_url="https://user:password@api.example.com/v1?api_key=query-secret",
        )
        forecaster, _, _ = make_forecaster(
            llm=llm,
            model_id="configured-but-wrong-model",
        )

        record = forecaster.forecast(
            ENTRY, AS_OF, TARGET, "next_day", generated_at=GENERATED_AT
        )

        self.assertEqual(record.model_id, "injected-evaluation-model")
        self.assertEqual(record.research_news_model_id, "injected-research-news-model")
        self.assertEqual(record.research_cio_model_id, "injected-research-cio-model")
        self.assertEqual(record.provider, "api.example.com")

    def test_credentials_are_redacted_before_llm_payload_and_persistence(self):
        llm = FakeLLM(
            base_url="https://user:password@api.example.com/v1?api_key=query-secret"
        )
        forecaster, _, orchestrator = make_forecaster(llm=llm)
        orchestrator.decision.fundamental.update({
            "api_key": "top-secret",
            "OPENAI_API_KEY": "openai-secret",
            "openaiApiKey": "camel-openai-secret",
            "service_apikey": "service-api-secret",
            "service_passwd": "service-passwd-secret",
            "nested": {
                "client_secret": "client-secret",
                "clientSecret": "client-camel-secret",
                "Authorization": "Bearer nested-secret",
            },
            "error": (
                "Authorization: Bearer bearer-secret; "
                "https://user:password@provider.example/v1?token=query-secret"
            ),
        })

        record = forecaster.forecast(
            ENTRY, AS_OF, TARGET, "next_day", generated_at=GENERATED_AT
        )

        serialized = json.dumps(
            {
                "payload": llm.payload,
                "evidence": [item.to_dict() for item in record.evidence],
                "provider": record.provider,
            },
            ensure_ascii=False,
        ).lower()
        for secret in (
            "top-secret",
            "openai-secret",
            "camel-openai-secret",
            "service-api-secret",
            "service-passwd-secret",
            "client-secret",
            "client-camel-secret",
            "nested-secret",
            "bearer-secret",
            "query-secret",
            "user:password",
            "authorization: bearer",
        ):
            self.assertNotIn(secret, serialized)
        self.assertIn("[redacted]", serialized)

    def test_stage_record_contains_thesis_and_provenance(self):
        checkpoint = Path(__file__)
        forecaster, _, _ = make_forecaster(model_path=checkpoint)

        record = forecaster.forecast(
            ENTRY,
            AS_OF,
            date(2026, 7, 23),
            "stage",
            generated_at=GENERATED_AT,
        )

        self.assertEqual(record.model_id, "injected-evaluation-model")
        self.assertEqual(record.provider, "api.example.com")
        self.assertIn(str(checkpoint), record.lstm_checkpoint)
        self.assertIn("sha256:", record.lstm_checkpoint)
        self.assertEqual(record.stage_direction, record.agent.direction)
        self.assertEqual(record.stage_target_price, record.agent.predicted_close)
        self.assertEqual(record.stage_interval_low, record.agent.interval_low)
        self.assertEqual(record.stage_interval_high, record.agent.interval_high)
        self.assertEqual(record.stage_confidence, record.agent.confidence)
        self.assertIn("经营稳健", record.stage_thesis)
        self.assertEqual(record.catalysts, ("旺季需求",))
        self.assertEqual(record.risks, ("估值偏高",))
        self.assertTrue(any(item.evidence_type == "cio_decision" for item in record.evidence))


if __name__ == "__main__":
    unittest.main()
