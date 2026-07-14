# Data And API Boundaries

## Configuration

配置优先级为 `.env`、用户目录配置、系统环境变量。常用配置项如下：

- `TAVILY_API_KEY`: Tavily 搜索新闻使用。
- `LLM_API_KEY` 或 `OPENAI_API_KEY`: OpenAI-compatible LLM 调用使用。
- `LLM_BASE_URL` 或 `OPENAI_BASE_URL`: 兼容 OpenAI 协议的服务地址。
- `LLM_MODEL_ID` 或 `NEWS_AGENT_MODEL`: News/CIO 使用的模型名。
- `AKSHARE_CACHE_TTL`: AKShare 默认缓存时间，单位秒。

## External Sources

- `AKShare`: 行情、估值、财务指标、个股新闻、热度和百度投票数据。
- `Tavily`: 最近新闻搜索，主要服务 `NewsAnalyst`。
- `OpenAI-compatible LLM`: 新闻事件压缩和 CIO 最终结构化决策。
- `Local LSTM`: 本地 `artifacts/models/mymodel.pt`，作为 `QuantAnalyst` 的短期收益率预测工具。

## Stability Rules

- 所有 AKShare 请求必须经过 `DataAccessLayer`，并使用缓存和限流。
- 新闻文本不能直接传给 CIO，必须先在 `NewsAnalyst` 内压缩为 `EventCard`。
- LLM 不负责计算技术指标或财务比率，只负责文本理解和综合推理。
- CIO 的 LLM 输出必须经过硬规则校验，例如重大负面新闻一票否决。

