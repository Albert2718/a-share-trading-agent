# Tools

本目录保存可被 LangGraph、后台任务或评测复用的能力入口。

- `deep_research.py`：深度研究薄工具，负责股票代码规范化、研究参数适配和稳定结果封装。
- `market.py`：面向网页 Agent 的实时行情与历史行情结果适配。
- `market_data.py`：封装 AKShare 数据读取。
- `news_search.py`：封装 Tavily 新闻搜索与结果清洗。
- `lstm.py`：封装课程 LSTM 模型推理。
- `utils.py`：提供代码规范化、限幅、去重和安全数值转换。

工具入口应保持轻量；复杂的深度研究业务编排归 `src/research/`，LangGraph 状态和路由归 `src/agents/chat/`。
