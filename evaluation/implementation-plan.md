# Agent 现实性评测 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为固定 20 只沪深 300 股票建立可重复、可结算的次日预测与 2026-07-23 阶段趋势评测，并生成适合答辩使用的本地报告。

**Architecture:** `src/evaluation` 作为独立业务边界，复用现有 `ResearchOrchestrator`、`LLMClient`、`AkshareMarketData` 和本地 LSTM。预测器先让深度研究生成结构化研究证据，再让评测专用 LLM 只根据已截止证据生成研究收益率，最后以 85% 研究结果和 15% LSTM 收益率确定最终价格并执行波动率约束。不可覆盖的 JSON 记录是事实来源，结算和 Markdown/JSON 报告均由记录重新计算。

**Tech Stack:** Python dataclasses、unittest、pandas、numpy、AKShare 1.18.64、OpenAI-compatible structured output、本地 PyTorch LSTM、标准库 `concurrent.futures`/`hashlib`/`json`。

## Global Constraints

- 所有源码、JSON 和 Markdown 均以 UTF-8 读写，不得改变无关文件的编码和换行。
- `.env` 中的 API Key 不得打印、写入评测记录或提交到仓库。
- 股票池固定为首次运行时从沪深 300 自动筛选的 20 只股票，并冻结至 2026-07-24 答辩结束。
- 阶段趋势的起点为 2026-07-14 收盘，结算目标为 2026-07-23 收盘。
- 每日预测只输出看涨或看跌、预计收盘价、预计涨跌幅、价格区间和置信度，不模拟交易或计算回撤。
- 评测仅比较完整 Agent 和 LSTM，不增加简单价格基线。
- `evaluation/data/` 和 `evaluation/reports/` 只保存在本地并加入 `.gitignore`；协议、实现计划和 `stock_pool.json` 可以版本控制。
- 历史预测不可覆盖；补跑只能补充缺失股票或新增结算结果。

---

## File Map

- Create `src/evaluation/__init__.py`: 导出评测入口和公共数据类型。
- Create `src/evaluation/models.py`: 股票池、预测、结算、批次和指标 dataclass。
- Create `src/evaluation/calendar.py`: 交易日解析、下一交易日和目标日验证。
- Create `src/evaluation/metrics.py`: Agent/LSTM 价格与方向指标。
- Create `src/evaluation/storage.py`: UTF-8 JSON、原子创建、哈希链、断点续跑和记录读取。
- Create `src/evaluation/market.py`: 沪深 300、行业映射、交易日历和原始行情适配器。
- Create `src/evaluation/stock_pool.py`: 20 股筛选、冻结和读取。
- Create `src/evaluation/prompts.py`: 次日与阶段趋势预测的中文系统提示词。
- Create `src/evaluation/forecasting.py`: 深度研究证据过滤、结构化 LLM 预测、15% LSTM 融合及波动约束。
- Create `src/evaluation/settlement.py`: 到期预测结算、除权标记和结果写入。
- Create `src/evaluation/reporting.py`: 累计 JSON/Markdown 报告与 7 月 23 日阶段对照表。
- Create `src/evaluation/runner.py`: 首次初始化、结算、受限并发预测、检查点和批次状态。
- Create `cli/evaluation.py`: CLI 参数到 runner 的薄适配层。
- Modify `cli/main.py`: 增加 `evaluate daily`、`evaluate report` 子命令。
- Modify `src/tools/market_data.py`: `history` 支持复权方式、截止日和成交额列，默认行为保持不变。
- Modify `.gitignore`: 忽略本地评测数据和报告。
- Modify `README.md`: 描述评测结构、命令、日期口径和本地数据位置。
- Create `tests/evaluation/`: 与上述模块一一对应的纯本地测试。

---

### Task 1: Domain Models, Calendar, And Metrics

**Files:**
- Create: `src/evaluation/__init__.py`
- Create: `src/evaluation/models.py`
- Create: `src/evaluation/calendar.py`
- Create: `src/evaluation/metrics.py`
- Create: `tests/evaluation/__init__.py`
- Create: `tests/evaluation/test_calendar_metrics.py`

**Interfaces:**
- Produces: `StockPoolEntry`, `EvidenceItem`, `ModelForecast`, `PredictionRecord`, `OutcomeRecord`, `BatchSummary`, `MetricSummary` dataclasses.
- Produces: `next_trade_date(trade_dates: Sequence[date], as_of: date) -> date`.
- Produces: `settle_direction(previous_close: float, actual_close: float) -> str`.
- Produces: `summarize_metrics(outcomes: Sequence[OutcomeRecord], model: str) -> MetricSummary`.

- [ ] **Step 1: Write failing calendar and metric tests**

```python
class CalendarMetricTests(unittest.TestCase):
    def test_next_trade_date_skips_weekend(self):
        dates = [date(2026, 7, 17), date(2026, 7, 20)]
        self.assertEqual(next_trade_date(dates, date(2026, 7, 17)), date(2026, 7, 20))

    def test_flat_sample_has_no_direction_hit(self):
        outcome = make_outcome(previous_close=10.0, actual_close=10.0, agent_price=10.1)
        summary = summarize_metrics([outcome], model="agent")
        self.assertEqual(summary.direction_samples, 0)
        self.assertEqual(summary.price_samples, 1)

    def test_price_metrics_and_interval_coverage(self):
        outcomes = [
            make_outcome(10.0, 10.2, agent_price=10.1, low=10.0, high=10.3),
            make_outcome(10.0, 9.8, agent_price=10.0, low=9.9, high=10.1),
        ]
        summary = summarize_metrics(outcomes, model="agent")
        self.assertAlmostEqual(summary.mae, 0.15)
        self.assertEqual(summary.direction_hits, 1)
        self.assertEqual(summary.interval_hits, 1)
```

- [ ] **Step 2: Run tests and verify the imports fail**

Run: `python -m unittest tests.evaluation.test_calendar_metrics -v`

Expected: `ModuleNotFoundError: No module named 'src.evaluation'`.

- [ ] **Step 3: Implement immutable dataclasses and metric functions**

Use literal directions `"up"`, `"down"`, and actual-only `"flat"`. `PredictionRecord` contains identity/timestamps, stock metadata, `current_close`, `agent`, `lstm`, evidence snapshots, warnings, model IDs, and optional stage thesis fields. `OutcomeRecord` contains the prediction ID, actual OHLC/return/direction, corporate-action flag, and per-model error fields.

```python
@dataclass(frozen=True)
class ModelForecast:
    direction: str
    expected_return: float
    predicted_close: float
    interval_low: float
    interval_high: float
    confidence: float


def settle_direction(previous_close: float, actual_close: float) -> str:
    if actual_close > previous_close:
        return "up"
    if actual_close < previous_close:
        return "down"
    return "flat"


def _model_error(forecast: ModelForecast, actual_close: float, actual_direction: str) -> ModelError:
    error = forecast.predicted_close - actual_close
    return ModelError(
        error=error,
        absolute_error=abs(error),
        absolute_percentage_error=abs(error) / actual_close,
        direction_hit=None if actual_direction == "flat" else forecast.direction == actual_direction,
        tolerance_hit=abs(error) / actual_close <= 0.01,
        interval_hit=forecast.interval_low <= actual_close <= forecast.interval_high,
    )
```

`summarize_metrics` uses population RMSE, excludes flat samples only from direction accuracy, and returns `None` instead of zero when a denominator is empty. Add `coverage_rate=successful_predictions / pool_size` to `BatchSummary`.

- [ ] **Step 4: Run focused tests**

Run: `python -m unittest tests.evaluation.test_calendar_metrics -v`

Expected: all calendar, flat-direction, MAE/RMSE/MAPE, 1% tolerance and interval tests pass.

- [ ] **Step 5: Commit the foundation**

```powershell
git add src/evaluation tests/evaluation
git commit -m "feat: add evaluation domain metrics"
```

---

### Task 2: Append-Only UTF-8 Storage And Hash Chain

**Files:**
- Create: `src/evaluation/storage.py`
- Create: `tests/evaluation/test_storage.py`

**Interfaces:**
- Consumes: dataclasses from `src.evaluation.models`.
- Produces: `EvaluationStorage(root: Path)`.
- Produces: `append_prediction(record: PredictionRecord) -> Path`, `append_outcome(record: OutcomeRecord) -> Path`, `prediction_exists(prediction_id: str) -> bool`, `load_predictions() -> list[PredictionRecord]`, `load_outcomes() -> list[OutcomeRecord]`.

- [ ] **Step 1: Write failing append-only tests**

```python
class StorageTests(unittest.TestCase):
    def test_prediction_cannot_be_overwritten(self):
        with TemporaryDirectory() as root:
            storage = EvaluationStorage(Path(root))
            record = sample_prediction("next_day:2026-07-14:600519")
            storage.append_prediction(record)
            with self.assertRaises(FileExistsError):
                storage.append_prediction(record)

    def test_hash_chain_links_records(self):
        with TemporaryDirectory() as root:
            storage = EvaluationStorage(Path(root))
            first = storage.append_prediction(sample_prediction("p1"))
            second = storage.append_prediction(sample_prediction("p2"))
            first_data = json.loads(first.read_text(encoding="utf-8"))
            second_data = json.loads(second.read_text(encoding="utf-8"))
            self.assertEqual(second_data["previous_hash"], first_data["content_hash"])
            self.assertTrue(storage.verify_chain()["ok"])
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m unittest tests.evaluation.test_storage -v`

Expected: import failure for `EvaluationStorage`.

- [ ] **Step 3: Implement canonical hashing and exclusive file creation**

Serialize dataclasses with `asdict`, use `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))` for hashing, and write with mode `"x"` plus `encoding="utf-8"`. The runner is the only chain writer; worker threads return in-memory predictions to it.

```python
def _hash_payload(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write_new_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
```

Prediction files use `predictions/<as_of_trade_date>/<code>-<kind>.json`; outcomes use `outcomes/<target_trade_date>/<prediction_id_hash>.json`. Maintain separate prediction and outcome chain heads, verify every stored hash before settlement, and reject a broken chain.

- [ ] **Step 4: Run storage tests**

Run: `python -m unittest tests.evaluation.test_storage -v`

Expected: overwrite rejection, UTF-8 Chinese round trip, chain link and tamper detection tests pass.

- [ ] **Step 5: Commit storage**

```powershell
git add src/evaluation/storage.py tests/evaluation/test_storage.py
git commit -m "feat: add append-only evaluation storage"
```

---

### Task 3: Raw Market Data, Trade Calendar, And Frozen CSI 300 Pool

**Files:**
- Modify: `src/tools/market_data.py`
- Create: `src/evaluation/market.py`
- Create: `src/evaluation/stock_pool.py`
- Create: `tests/evaluation/test_stock_pool.py`
- Modify: `tests/test_shared_tools.py`

**Interfaces:**
- Extends: `AkshareMarketData.history(code, days=160, adjust="qfq", end_date=None) -> pd.DataFrame` with `amount` column.
- Produces: `EvaluationMarketData.trade_dates()`, `csi300_constituents()`, `industry_map()`, `raw_history(code, days, end_date)`.
- Produces: `StockPoolManager.freeze(path: Path, selected_at: datetime) -> list[StockPoolEntry]` and `load(path: Path) -> list[StockPoolEntry]`.

- [ ] **Step 1: Write failing market/pool tests**

```python
class StockPoolTests(unittest.TestCase):
    def test_selects_twenty_distinct_industries_before_duplicates(self):
        provider = FakePoolProvider(candidate_count=30, industry_count=25)
        entries = StockPoolManager(provider).select(selected_at=FIXED_TIME)
        self.assertEqual(len(entries), 20)
        self.assertEqual(len({entry.industry for entry in entries}), 20)

    def test_frozen_pool_is_loaded_without_refetch(self):
        with TemporaryDirectory() as root:
            provider = FakePoolProvider(candidate_count=25, industry_count=25)
            manager = StockPoolManager(provider)
            first = manager.freeze(Path(root) / "stock_pool.json", FIXED_TIME)
            second = manager.freeze(Path(root) / "stock_pool.json", FIXED_TIME)
            self.assertEqual(first, second)
            self.assertEqual(provider.constituent_calls, 1)
```

Add a shared-tool test proving `history(..., adjust="", end_date=date(2026, 7, 14))` passes an empty adjustment and `20260714` to AKShare while the existing default remains `qfq`.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m unittest tests.evaluation.test_stock_pool tests.test_shared_tools -v`

Expected: missing evaluation market/pool classes and unsupported `history` arguments.

- [ ] **Step 3: Extend history without changing existing callers**

Include `adjust` and `end_date` in the cache key. Normalize `成交额`/`amount`; use `0.0` when providers omit it. Keep `adjust="qfq"` as the default.

```python
def history(self, code: str, days: int = 160, adjust: str = "qfq", end_date: date | str | None = None) -> pd.DataFrame:
    norm = normalize_a_share_code(code)
    end_value = pd.Timestamp(end_date or self._now_fn().date()).strftime("%Y%m%d")
    start_value = (pd.Timestamp(end_value) - timedelta(days=days * 2)).strftime("%Y%m%d")
    cache_key = f"{norm}_{days}_{adjust or 'raw'}_{end_value}"
```

- [ ] **Step 4: Implement AKShare evaluation adapter**

Use `index_stock_cons_csindex(symbol="000300")`, `stock_board_industry_name_em()`, `stock_board_industry_cons_em(symbol=name)`, and `tool_trade_date_hist_sina()`. Cache constituents and trading dates for one day, industry mapping for seven days, and each 60-day raw history for 30 minutes. Empty or schema-invalid responses raise `RuntimeError`; no weekday or stale-data fallback is allowed.

- [ ] **Step 5: Implement deterministic pool selection and freeze**

Filter ST/退市 names, fewer than 250 valid rows, listing history shorter than two years, missing latest close, and zero recent volume. Compute `average_amount_60d` from `amount`, falling back to `close * volume` only when the provider lacks amount and record `liquidity_source="close_x_volume"`.

Select in two passes: first take the highest-liquidity stock in each industry and keep the 20 highest-liquidity industry winners; if fewer than 20 industries remain, fill by global liquidity while enforcing at most two stocks per industry. Persist `rule_version="1.0"`, constituent source date, selected timestamp, criteria and all 20 entries with UTF-8 JSON.

- [ ] **Step 6: Run focused tests**

Run: `python -m unittest tests.evaluation.test_stock_pool tests.test_shared_tools -v`

Expected: pool size, industry cap, exclusion, deterministic ordering, freeze reuse, raw history and default history tests pass.

- [ ] **Step 7: Commit market and pool support**

```powershell
git add src/tools/market_data.py src/evaluation/market.py src/evaluation/stock_pool.py tests/evaluation/test_stock_pool.py tests/test_shared_tools.py
git commit -m "feat: freeze diversified CSI 300 pool"
```

---

### Task 4: Structured Deep-Research Forecasting With Auxiliary LSTM

**Files:**
- Create: `src/evaluation/prompts.py`
- Create: `src/evaluation/forecasting.py`
- Create: `tests/evaluation/test_forecasting.py`

**Interfaces:**
- Consumes: `ResearchOrchestrator.analyze`, embedded analyst reports in `StockDecision`, `LLMClient.structured`, raw history and `StockPoolEntry`.
- Produces: `EvaluationForecaster.forecast(entry, as_of, target, kind) -> PredictionRecord`.
- Produces: `blend_forecast(draft, lstm_return, current_close, volatility, horizon_days, code) -> ModelForecast`.

- [ ] **Step 1: Write failing fusion and cutoff tests**

```python
class ForecastingTests(unittest.TestCase):
    def test_lstm_has_exactly_fifteen_percent_influence(self):
        result = blend_forecast(
            draft=ResearchDraft(expected_return=0.02, interval_low_return=-0.01, interval_high_return=0.04, confidence=0.7),
            lstm_return=-0.01,
            current_close=100.0,
            volatility=0.02,
            horizon_days=1,
            code="600519",
        )
        self.assertAlmostEqual(result.expected_return, 0.0155)
        self.assertAlmostEqual(result.predicted_close, 101.55)
        self.assertEqual(result.direction, "up")

    def test_future_news_is_removed_before_llm_call(self):
        forecaster, llm = make_forecaster(news_time="2026-07-14T19:00:00+08:00")
        forecaster.forecast(ENTRY, AS_OF, TARGET, "next_day", generated_at="2026-07-14T18:30:00+08:00")
        self.assertEqual(llm.payload["reports"]["news"]["events"], [])
        self.assertIn("news_after_cutoff", llm.payload["warnings"])
```

Also test LSTM unavailable fallback, malformed LLM output, central price inside interval, main-board 10% cap, 300/688 board 20% cap, stage volatility scaling, and binary direction derivation.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m unittest tests.evaluation.test_forecasting -v`

Expected: missing forecasting module.

- [ ] **Step 3: Add strict structured prompts and schema**

The prompt states that the model is an evaluation forecaster, only supplied evidence may be used, LSTM is deliberately absent from the research draft, and output must contain:

```python
FORECAST_SCHEMA = {
    "name": "evaluation_forecast",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "expected_return": {"type": "number"},
            "interval_low_return": {"type": "number"},
            "interval_high_return": {"type": "number"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "company_trend": {"type": "string"},
            "industry_trend": {"type": "string"},
            "core_thesis": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            "catalysts": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            "risks": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        },
        "required": ["expected_return", "interval_low_return", "interval_high_return", "confidence", "company_trend", "industry_trend", "core_thesis", "catalysts", "risks"],
    },
}
```

- [ ] **Step 4: Implement evidence sanitization and deterministic fusion**

Extract reports from the deep-research decision. Remove `model_expected_return` and LSTM text from the quant report before the LLM call, but preserve them separately in the prediction record. Parse all news timestamps; events later than `generated_at` or without a verifiable timestamp are excluded and recorded as warnings.

Use `research_weight=0.85` and `lstm_weight=0.15`; if LSTM is unavailable, use the research return unchanged and add `lstm_unavailable`. Clamp next-day return to `min(board_limit, max(0.02, 2.5 * volatility))`; clamp stage return to `min(0.30, max(0.05, 2.5 * volatility * sqrt(horizon_days)))`. Derive direction from the clamped return and ensure `interval_low <= predicted_close <= interval_high`.

- [ ] **Step 5: Build PredictionRecord from actual deep research**

Call one-stock `ResearchOrchestrator.analyze` with `AnalysisContext(depth="full", risk_profile="balanced", use_llm=True, as_of=as_of.isoformat(), history_days=250)`. Reject missing quant history or a latest history date different from `as_of`. Save the full sanitized analyst reports, CIO decision, model ID, LSTM checkpoint path/hash, warnings, and stage thesis fields.

- [ ] **Step 6: Run forecasting tests**

Run: `python -m unittest tests.evaluation.test_forecasting -v`

Expected: all cutoff, fusion, cap, malformed output, unavailable LSTM and stage-field tests pass without network access.

- [ ] **Step 7: Validate Chinese files and imports**

Run: `Get-Content -Raw -Encoding UTF8 -Path src\evaluation\prompts.py`

Run: `$env:PYTHONDONTWRITEBYTECODE = "1"; python -c "import src.evaluation.forecasting; import src.evaluation.prompts"`

Expected: Chinese prompt displays correctly and imports complete without output.

- [ ] **Step 8: Commit forecasting**

```powershell
git add src/evaluation/prompts.py src/evaluation/forecasting.py tests/evaluation/test_forecasting.py
git commit -m "feat: add bounded research forecasts"
```

---

### Task 5: Settlement And Reproducible Reports

**Files:**
- Create: `src/evaluation/settlement.py`
- Create: `src/evaluation/reporting.py`
- Create: `tests/evaluation/test_settlement_reporting.py`

**Interfaces:**
- Produces: `SettlementService.settle_due(latest_trade_date: date) -> list[OutcomeRecord]`.
- Produces: `ReportBuilder.build() -> tuple[Path, Path]` for `summary.json` and `summary.md`.

- [ ] **Step 1: Write failing settlement/report tests**

```python
class SettlementReportingTests(unittest.TestCase):
    def test_due_prediction_is_settled_once(self):
        service, storage = make_service(actual_close=102.0)
        first = service.settle_due(date(2026, 7, 15))
        second = service.settle_due(date(2026, 7, 15))
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertTrue(first[0].agent_error.direction_hit)

    def test_report_contains_agent_lstm_and_coverage(self):
        report = build_sample_report()
        self.assertIn("完整 Agent", report)
        self.assertIn("LSTM", report)
        self.assertIn("预测覆盖率", report)
        self.assertNotIn("最大回撤", report)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m unittest tests.evaluation.test_settlement_reporting -v`

Expected: missing settlement/reporting modules.

- [ ] **Step 3: Implement idempotent settlement**

Load predictions whose target date is no later than the latest complete trading date and have no outcome. Fetch raw OHLC for the exact target date, compute actual return/direction and both model errors, detect corporate actions from an abnormal gap between raw and qfq return or explicit adjustment metadata, then append one outcome. Missing target bars remain pending with a recorded reason; they are not converted to zero returns.

- [ ] **Step 4: Implement JSON and Chinese Markdown reports**

Recompute all metrics from verified prediction/outcome chains. Include sample count, coverage, Agent/LSTM comparison, 5-day/20-day rolling tables, stock/industry/confidence breakdowns, maximum errors, corporate-action-inclusive/exclusive views, failed stocks, and pending predictions. Stage report includes 2026-07-14 versus 2026-07-23 price and a thesis/catalyst/risk evidence table.

Reports are derived files and may be atomically replaced using a temporary file in the same directory followed by `Path.replace`; prediction and outcome files remain append-only.

- [ ] **Step 5: Run settlement/report tests**

Run: `python -m unittest tests.evaluation.test_settlement_reporting -v`

Expected: idempotence, flat handling, missing bars, metric values, UTF-8 report and no-trading-metric tests pass.

- [ ] **Step 6: Commit settlement and reporting**

```powershell
git add src/evaluation/settlement.py src/evaluation/reporting.py tests/evaluation/test_settlement_reporting.py
git commit -m "feat: settle and report evaluation results"
```

---

### Task 6: Resumable Runner And CLI

**Files:**
- Create: `src/evaluation/runner.py`
- Create: `cli/evaluation.py`
- Modify: `cli/main.py`
- Create: `tests/evaluation/test_runner.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `EvaluationRunner.run_daily(now: datetime) -> BatchSummary`.
- Produces: `EvaluationRunner.build_report() -> tuple[Path, Path]`.
- CLI: `python run_agent.py evaluate daily` and `python run_agent.py evaluate report`.

- [ ] **Step 1: Write failing runner and parser tests**

```python
class RunnerTests(unittest.TestCase):
    def test_daily_settles_before_forecasting_and_resumes_missing_codes(self):
        runner, calls = make_runner(existing_codes={"600519"})
        summary = runner.run_daily(FIXED_AFTER_CLOSE)
        self.assertEqual(calls[0], "settle")
        self.assertNotIn("600519", calls)
        self.assertEqual(summary.pool_size, 20)
        self.assertEqual(summary.successful_predictions, 19)

    def test_before_close_is_rejected(self):
        runner, _ = make_runner()
        with self.assertRaisesRegex(RuntimeError, "market has not closed"):
            runner.run_daily(datetime(2026, 7, 14, 14, 59, tzinfo=HONG_KONG))
```

Parser test:

```python
args = build_parser().parse_args(["evaluate", "daily"])
self.assertEqual((args.command, args.action), ("evaluate", "daily"))
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m unittest tests.evaluation.test_runner tests.test_cli -v`

Expected: missing runner and unrecognized `evaluate` command.

- [ ] **Step 3: Implement ordered, resumable daily orchestration**

Require Asia/Hong_Kong time at or after 15:30 and verify the market provider's latest complete date equals today. Then execute in this order: verify chains, freeze/load pool, settle due predictions, generate stage predictions if absent and `as_of=2026-07-14`, generate next-day predictions, write batch summary, rebuild reports.

Use `ThreadPoolExecutor(max_workers=3)` for stock forecasting. Worker futures return records or structured errors; only the main thread appends storage records so the hash chain remains deterministic. Skip existing prediction IDs. Mark a batch complete at 20 successes, incomplete below 18, and partial at 18 or 19; all statuses expose coverage.

- [ ] **Step 4: Add CLI integration**

```python
evaluate = sub.add_parser("evaluate", help="Run or report the fixed-pool realistic evaluation.")
evaluate.add_argument("action", choices=["daily", "report"])
evaluate.add_argument("--root", default="evaluation")
```

`run_evaluate` loads `.env` non-interactively, refuses to prompt for secrets during a long batch, prints paths/status without printing raw evidence or keys, and returns a nonzero exit code for rejected or incomplete batches.

- [ ] **Step 5: Run CLI and runner tests**

Run: `python -m unittest tests.evaluation.test_runner tests.test_cli -v`

Expected: ordering, resume, status thresholds, before-close rejection, stale date rejection and parser tests pass.

- [ ] **Step 6: Commit runner and CLI**

```powershell
git add src/evaluation/runner.py cli/evaluation.py cli/main.py tests/evaluation/test_runner.py tests/test_cli.py
git commit -m "feat: add daily evaluation command"
```

---

### Task 7: Local Data Policy, README, Full Verification, And First Run

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `src/evaluation/__init__.py`
- Create at runtime: `evaluation/stock_pool.json`
- Create at runtime and ignore: `evaluation/data/**`, `evaluation/reports/**`

**Interfaces:**
- Documents the exact command, local-only files, fixed dates and Agent/LSTM comparison.

- [ ] **Step 1: Add local evaluation ignores**

```gitignore
evaluation/data/
evaluation/reports/
```

Do not ignore `evaluation/protocol.md`, `evaluation/implementation-plan.md`, or `evaluation/stock_pool.json`.

- [ ] **Step 2: Update README with the real workflow**

Add the `src/evaluation` and `evaluation` directories to the tree, explain the fixed 20-stock CSI 300 pool, and document:

```powershell
# 每个交易日收盘且行情更新后运行：先结算，再预测
python run_agent.py evaluate daily

# 仅重新生成累计报告
python run_agent.py evaluate report
```

State that daily records remain local, the 7/14–7/23 result is a stage-trend evaluation rather than proof of long-term performance, and no trading return/drawdown is calculated.

- [ ] **Step 3: Run all deterministic tests**

Run: `$env:PYTHONDONTWRITEBYTECODE = "1"; python -m unittest discover -s tests -v`

Expected: all existing and new tests pass; no network call is required by the test suite.

- [ ] **Step 4: Verify UTF-8 files and repository hygiene**

Run: `Get-Content -Raw -Encoding UTF8 -Path evaluation\protocol.md`

Run: `Get-Content -Raw -Encoding UTF8 -Path evaluation\implementation-plan.md`

Run: `Get-Content -Raw -Encoding UTF8 -Path README.md`

Run: `git diff --check`

Run: `git status --short`

Expected: Chinese is readable, no whitespace errors, `.env` is absent from status, and runtime `evaluation/data`/`evaluation/reports` files are absent from status.

- [ ] **Step 5: Run a real dependency smoke check**

Run: `$env:PYTHONDONTWRITEBYTECODE = "1"; python -c "from src.core import load_config; from src.tools.market_data import AkshareMarketData; c=load_config(); print({'llm_key':'set' if c.openai_api_key else 'missing','tavily_key':'set' if c.tavily_api_key else 'missing','akshare':AkshareMarketData().available()})"`

Expected: key status only, never key values; AKShare reports `True`.

- [ ] **Step 6: Run the first real evaluation after the 2026-07-14 close data is available**

Run: `python run_agent.py evaluate daily`

Expected: `evaluation/stock_pool.json` contains exactly 20 frozen entries, stage and next-day prediction coverage is at least 18/20, every included news item predates its prediction timestamp, and reports are generated locally. If AKShare has not published the 2026-07-14 complete daily bar, the command must reject the run without creating predictions; rerun after the source updates.

- [ ] **Step 7: Inspect generated results without exposing secrets**

Run: `python run_agent.py evaluate report`

Read `evaluation/reports/summary.md` as UTF-8 and inspect batch errors, prediction ranges, source timestamps, model IDs, hash-chain status and coverage. Do not print full `.env` or raw authorization headers.

- [ ] **Step 8: Commit implementation and tracked stock pool**

```powershell
git add .gitignore README.md src/evaluation cli/evaluation.py cli/main.py src/tools/market_data.py tests/evaluation tests/test_cli.py tests/test_shared_tools.py evaluation/stock_pool.json evaluation/implementation-plan.md
git commit -m "feat: add fixed-pool realistic evaluation"
```

Before committing, use `git diff --cached --name-only` to confirm that `evaluation/data/`, `evaluation/reports/`, `.env`, and unrelated user changes are not staged.

---

## Plan Self-Review Result

- Every protocol section maps to at least one task: pool and dates (Task 3/6), anti-leakage and bounded fusion (Task 4), append-only records (Task 2), settlement/metrics/reports (Task 1/5), manual execution and resilience (Task 6), local-only data and verification (Task 7).
- Public signatures use the same `PredictionRecord`, `OutcomeRecord`, `ModelForecast`, `EvaluationStorage`, `EvaluationForecaster`, and `EvaluationRunner` names throughout.
- Runtime reports are replaceable derived artifacts; predictions and outcomes are exclusive-create immutable records. This removes the apparent conflict between resumability and history protection.
- LSTM influence is applied once at 15%; its value is removed from the LLM research payload to prevent double counting through the existing quant/CIO path.
