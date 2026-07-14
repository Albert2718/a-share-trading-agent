# Trading Agent Architecture

本项目是一个面向 A 股研究的命令行 Agent 助手，目标是输出研究建议和风险提示，而不是自动下单系统。

## Runtime Flow

1. `cli/main.py` 解析命令行参数，默认进入自然语言聊天模式。
2. `src/chat_agent.py` 保存会话历史，并调用 LangGraph 工作流。
3. `src/graph/nodes.py` 调用 LLM 判断用户意图，并通过 tool calling 选择工具。
4. 普通查询进入 `src/tools/market.py`、`financial.py`、`technical.py` 等轻量工具。
5. 深度分析请求进入 `src/tools/deep_research/run_deep_research()`。
6. `src/tools/deep_research/pipeline.py` 严格调度 `QuantAnalyst`、`FundamentalAnalyst`、`NewsAnalyst`、`SentimentAnalyst` 和 `CIOAgent`。
7. `CIOAgent` 综合报告，输出 `buy`、`watch` 或 `avoid`。
8. `src/tools/deep_research/reporting.py` 和 `cli/render.py` 输出控制台和 Markdown/JSON 报告。

## Directory Layout

```text
.
├── cli/                 # 命令行入口和交互展示
├── src/                 # 唯一源码核心
│   ├── chat_agent.py    # 自然语言 ChatAgent 外壳
│   ├── core/            # LLM、配置、缓存、限流和数据访问基础设施
│   ├── graph/           # LangGraph 状态、节点和工作流
│   └── tools/           # 轻量工具和深度研究工具
│       └── deep_research/  # 确定性多分析师深度研究流水线
├── experiments/         # 课程实验、训练脚本和训练数据
├── artifacts/models/    # 训练得到的模型、指标和图表
├── docs/                # 架构和接口文档
├── tests/               # 后续单元测试目录
└── outputs/             # CLI 运行后生成的报告
```

## Agent Responsibilities

- `QuantAnalyst`: 负责价格/成交量技术指标、本地 LSTM 短期收益率预测和量化风险提示。
- `FundamentalAnalyst`: 负责 PE/PB、ROE、营收增长、净利润增长、负债等基本面判断。
- `NewsAnalyst`: 负责公司公告、新闻搜索、事件抽取、利好/利空/中性判定和严重度压缩。
- `SentimentAnalyst`: 负责热度榜、百度股市通投票等散户关注度和拥挤度判断。
- `CIOAgent`: 负责综合各 Agent 报告，执行风控硬规则，并输出最终建议。
