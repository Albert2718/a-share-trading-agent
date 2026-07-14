FORECAST_SYSTEM_PROMPT = """你是评测系统中的结构化预测器。你只能使用用户消息中提供的、在截止时间前可验证的研究证据，不得补充外部事实或猜测缺失数据。

量化报告中的 LSTM 预计收益已被刻意移除。不要推测、重建或引用 LSTM 结果；评测系统会在结构化研究预测完成后单独加入固定权重的 LSTM 辅助预测，防止重复计权。

请输出研究证据支持的预计收益率、收益率区间、置信度、公司趋势、行业趋势、核心逻辑、催化因素和风险。收益率使用小数表示。所有结论必须能由给定证据直接支持。"""


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
            "core_thesis": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 5,
            },
            "catalysts": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 5,
            },
            "risks": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 5,
            },
        },
        "required": [
            "expected_return",
            "interval_low_return",
            "interval_high_return",
            "confidence",
            "company_trend",
            "industry_trend",
            "core_thesis",
            "catalysts",
            "risks",
        ],
    },
}
