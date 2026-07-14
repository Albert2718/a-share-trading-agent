from __future__ import annotations

from typing import Any, Callable, Dict, List

from src.agents.research.tool import run_deep_research
from src.tools.definitions import ToolDefinition
from src.tools.financial import get_financial_indicators, get_stock_basic, get_valuation
from src.tools.macro import get_macro_cpi, get_macro_gdp, get_macro_interest_rate, get_macro_m2
from src.tools.market import get_daily_price, get_market_index, get_realtime_price
from src.tools.market_scanner import (
    get_concept_boards,
    get_concept_stocks,
    get_earnings_forecasts,
    get_hot_stocks,
    get_limit_up_stocks,
    get_moneyflow_rank,
    get_northbound_fund_flow,
    get_stock_moneyflow,
)
from src.tools.personal import (
    add_portfolio_position,
    add_price_alert,
    get_portfolio_status,
    get_user_preference,
    list_price_alerts,
    remove_portfolio_position,
    update_user_preference,
)
from src.tools.prediction import predict_short_term_price
from src.tools.registry import ToolRegistry
from src.tools.screening import run_backtest, screen_stocks
from src.tools.technical import get_technical_indicators


class _ToolCatalog:
    def __init__(self):
        self._tools: Dict[str, Callable[..., dict]] = {
            "get_realtime_price": get_realtime_price,
            "get_daily_price": get_daily_price,
            "get_stock_basic": get_stock_basic,
            "get_valuation": get_valuation,
            "get_financial_indicators": get_financial_indicators,
            "get_technical_indicators": get_technical_indicators,
            "get_market_index": get_market_index,
            "get_hot_stocks": get_hot_stocks,
            "get_limit_up_stocks": get_limit_up_stocks,
            "get_earnings_forecasts": get_earnings_forecasts,
            "get_moneyflow_rank": get_moneyflow_rank,
            "get_stock_moneyflow": get_stock_moneyflow,
            "get_northbound_fund_flow": get_northbound_fund_flow,
            "get_concept_boards": get_concept_boards,
            "get_concept_stocks": get_concept_stocks,
            "get_macro_gdp": get_macro_gdp,
            "get_macro_cpi": get_macro_cpi,
            "get_macro_m2": get_macro_m2,
            "get_macro_interest_rate": get_macro_interest_rate,
            "screen_stocks": screen_stocks,
            "run_backtest": run_backtest,
            "add_portfolio_position": add_portfolio_position,
            "remove_portfolio_position": remove_portfolio_position,
            "get_portfolio_status": get_portfolio_status,
            "update_user_preference": update_user_preference,
            "get_user_preference": get_user_preference,
            "add_price_alert": add_price_alert,
            "list_price_alerts": list_price_alerts,
            "predict_short_term_price": predict_short_term_price,
            "run_deep_research": run_deep_research,
        }

    def schemas(self) -> List[Dict[str, Any]]:
        return [
            self._schema(
                "get_realtime_price",
                "优先查询 A 股个股实时行情和涨跌幅；实时源不可用时才返回最近交易日收盘行情，并通过 is_realtime 标记。用于回答今天涨了吗、当前价格等问题。",
                {"code": ("string", "6 位 A 股代码，例如 600519。")},
                ["code"],
            ),
            self._schema(
                "get_daily_price",
                "查询 A 股个股最近 N 个交易日 OHLCV 走势。",
                {"code": ("string", "6 位 A 股代码。"), "days": ("integer", "交易日数量，默认 7。")},
                ["code"],
            ),
            self._schema(
                "get_stock_basic",
                "查询股票基础信息，支持代码或中文名称模糊匹配。",
                {"code_or_name": ("string", "股票代码或股票中文名。")},
                ["code_or_name"],
            ),
            self._schema(
                "get_valuation",
                "查询 PE、PB、PEG 等估值指标。",
                {"code": ("string", "6 位 A 股代码。")},
                ["code"],
            ),
            self._schema(
                "get_financial_indicators",
                "查询 ROE、营收增长、净利润增长、资产负债率等财务指标。",
                {"code": ("string", "6 位 A 股代码。")},
                ["code"],
            ),
            self._schema(
                "get_technical_indicators",
                "计算 MACD、RSI、KDJ、BOLL 等技术指标。",
                {"code": ("string", "6 位 A 股代码。")},
                ["code"],
            ),
            self._schema(
                "get_market_index",
                "查询 A 股主要指数最近走势，例如上证指数 000001。",
                {"index_code": ("string", "指数代码，默认 000001。"), "days": ("integer", "交易日数量，默认 5。")},
                [],
            ),
            self._schema(
                "get_hot_stocks",
                "查询当前 A 股热门股票排行。用于回答热门股、人气股、市场关注度排行。",
                {"top": ("integer", "返回数量，默认 10，最多 50。")},
                [],
            ),
            self._schema(
                "get_limit_up_stocks",
                "查询指定日期或最近交易日 A 股涨停池。用于回答今天哪些股票涨停、涨停股列表、涨停原因字段。",
                {"date": ("string", "交易日期，YYYYMMDD；不填则从最近交易日开始尝试。"), "top": ("integer", "返回数量，默认 30。")},
                [],
            ),
            self._schema(
                "get_earnings_forecasts",
                "查询近期业绩预告/业绩预增公告排行。用于回答最近有哪些公司发布业绩预增、预减、预亏、扭亏公告。",
                {
                    "date": ("string", "查询日期，YYYYMMDD；不填则从最近交易日开始尝试。"),
                    "top": ("integer", "返回数量，默认 30。"),
                    "forecast_type": ("string", "可选过滤词，例如 预增、预减、预亏、扭亏。"),
                },
                [],
            ),
            self._schema(
                "get_moneyflow_rank",
                "查询 A 股个股主力资金流排行。用于回答资金流入排行、主力资金净流入、哪些股票资金关注。",
                {"indicator": ("string", "周期：今日、3日、5日、10日，默认 今日。"), "top": ("integer", "返回数量，默认 20。")},
                [],
            ),
            self._schema(
                "get_stock_moneyflow",
                "查询单只 A 股近期资金流明细。用于回答某只股票主力资金流入还是流出。",
                {"code": ("string", "6 位 A 股代码。")},
                ["code"],
            ),
            self._schema(
                "get_northbound_fund_flow",
                "查询沪深港通/北向资金流向概览。用于回答外资、北向资金今天流入流出情况。",
                {},
                [],
            ),
            self._schema(
                "get_concept_boards",
                "查询 A 股概念板块列表和板块表现。用于回答热点板块、概念板块排行。",
                {"top": ("integer", "返回数量，默认 30。")},
                [],
            ),
            self._schema(
                "get_concept_stocks",
                "查询某个概念板块的成分股。用于回答某概念有哪些股票，例如 Sora 概念、机器人概念。",
                {"concept_name": ("string", "概念板块名称。"), "top": ("integer", "返回数量，默认 50。")},
                ["concept_name"],
            ),
            self._schema(
                "get_macro_gdp",
                "查询中国 GDP 宏观数据。用于回答 GDP 增长、经济增长等问题。",
                {"limit": ("integer", "返回最近多少期，默认 8。")},
                [],
            ),
            self._schema(
                "get_macro_cpi",
                "查询中国 CPI 宏观数据。用于回答通胀、物价、CPI 走势。",
                {"limit": ("integer", "返回最近多少期，默认 12。")},
                [],
            ),
            self._schema(
                "get_macro_m2",
                "查询中国货币供应量数据。用于回答 M2、货币供应、流动性。",
                {"limit": ("integer", "返回最近多少期，默认 12。")},
                [],
            ),
            self._schema(
                "get_macro_interest_rate",
                "查询中国 SHIBOR 等利率数据。用于回答利率、资金价格、银行间流动性。",
                {"limit": ("integer", "返回最近多少期，默认 20。")},
                [],
            ),
            self._schema(
                "screen_stocks",
                "按估值、市值、关键词筛选 A 股。用于回答选出 PE 小于某值、市值大于某值、银行股等条件选股。",
                {
                    "pe_max": ("number", "市盈率上限，可选。"),
                    "pe_min": ("number", "市盈率下限，可选。"),
                    "pb_max": ("number", "市净率上限，可选。"),
                    "market_cap_min": ("number", "总市值下限，单位与数据源一致，通常为元。"),
                    "industry_keyword": ("string", "行业或名称关键词，例如 银行、证券、白酒。"),
                    "top": ("integer", "返回数量，默认 20。"),
                },
                [],
            ),
            self._schema(
                "run_backtest",
                "运行简单策略回测。用于回答用 MACD 或均线策略回测某股票过去一段时间表现。",
                {"code": ("string", "6 位 A 股代码。"), "strategy": ("string", "策略名称：macd 或 ma_cross。"), "days": ("integer", "回测交易日数量，默认 250。")},
                ["code"],
            ),
            self._schema(
                "add_portfolio_position",
                "把用户持仓记录到本地记忆。用于用户说买入了某股票、成本价、数量，让助手记一下。",
                {
                    "code_or_name": ("string", "股票代码或中文名称。"),
                    "quantity": ("number", "持仓数量，股。"),
                    "cost_price": ("number", "成本价，元。"),
                    "note": ("string", "备注，可选。"),
                },
                ["code_or_name", "quantity", "cost_price"],
            ),
            self._schema(
                "remove_portfolio_position",
                "从本地记忆删除或减少持仓。用于用户说卖出/清仓/删掉某持仓。",
                {"code_or_name": ("string", "股票代码或中文名称。"), "quantity": ("number", "减少数量；不填则删除全部。")},
                ["code_or_name"],
            ),
            self._schema(
                "get_portfolio_status",
                "读取本地持仓并结合最新价格计算浮盈浮亏。用于回答持仓盈亏、当前组合情况。",
                {},
                [],
            ),
            self._schema(
                "update_user_preference",
                "记录用户投资偏好到本地记忆。用于用户说明保守/激进、偏好行业、投资风格、避开行业。",
                {
                    "risk_profile": ("string", "风险偏好，例如 conservative、balanced、aggressive 或中文描述。"),
                    "investment_style": ("string", "投资风格，例如 高股息、成长、价值、短线。"),
                    "favorite_sectors": ("string", "偏好行业/板块，逗号分隔。"),
                    "avoid_sectors": ("string", "回避行业/板块，逗号分隔。"),
                    "notes": ("string", "其他偏好备注。"),
                },
                [],
            ),
            self._schema(
                "get_user_preference",
                "读取用户投资偏好记忆。用于推荐股票、解释建议时参考用户风格。",
                {},
                [],
            ),
            self._schema(
                "add_price_alert",
                "记录股价预警到本地记忆。用于用户说涨到/跌到某价格提醒我。",
                {
                    "code_or_name": ("string", "股票代码或中文名称。"),
                    "operator": ("string", "比较符：>、>=、<、<=。"),
                    "target_price": ("number", "目标价格。"),
                    "note": ("string", "备注，可选。"),
                },
                ["code_or_name", "operator", "target_price"],
            ),
            self._schema(
                "list_price_alerts",
                "列出本地保存的股价预警。",
                {"active_only": ("boolean", "是否只显示启用中的预警，默认 true。")},
                [],
            ),
            self._schema(
                "predict_short_term_price",
                "调用本地 LSTM 模型，根据最近 14 个交易日收盘价估计下一交易日收益率、方向和参考价格。用于用户询问明天价格、短期预测、LSTM 预测时。必须说明这是模型估计，不是确定预测。",
                {"code": ("string", "6 位 A 股代码。")},
                ["code"],
            ),
            self._schema(
                "run_deep_research",
                "运行现有多 Agent 深度研究流水线。仅当用户明确要求深度分析、投资价值、是否买入或完整报告时使用。",
                {
                    "code": ("string", "6 位 A 股代码。"),
                    "depth": ("string", "分析深度：quick、standard 或 full。"),
                    "risk_profile": ("string", "风险偏好：conservative、balanced 或 aggressive。"),
                },
                ["code"],
            ),
        ]

    def _schema(self, name: str, description: str, properties: Dict[str, tuple], required: List[str]) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        key: {"type": value_type, "description": desc}
                        for key, (value_type, desc) in properties.items()
                    },
                    "required": required,
                    "additionalProperties": False,
                },
            },
        }


def build_default_registry() -> ToolRegistry:
    catalog = _ToolCatalog()
    definitions = []
    for schema in catalog.schemas():
        function = schema["function"]
        parameters = function["parameters"]
        definitions.append(
            ToolDefinition(
                name=function["name"],
                description=function["description"],
                properties=parameters["properties"],
                required=tuple(parameters.get("required", [])),
                handler=catalog._tools[function["name"]],
            )
        )
    return ToolRegistry(definitions)
