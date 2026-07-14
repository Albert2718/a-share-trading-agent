# A 股多 Agent 研究助手

这是一个面向 A 股研究的命令行 Agent 项目，用 LangGraph 编排自然语言交互，并结合 AKShare、Tavily、OpenAI-compatible LLM 和本地 LSTM 模型生成研究报告。项目用于课程实验和研究辅助，不构成投资建议。

## 功能概览

- 自然语言聊天入口：识别用户意图并调用行情、财务、技术、筛选和个人记忆工具。
- 单股深度分析：由量化、基本面、新闻、情绪和 CIO Agent 生成 `buy`、`watch` 或 `avoid` 建议。
- 批量筛选：支持 watchlist 或热门股票池分析。
- 现实性评测：固定 20 只沪深 300 股票，收盘后记录次日涨跌方向和收盘价预测。
- 本地缓存与限流：AKShare 数据经统一数据访问层读取，减少重复请求。
- 报告输出：CLI 运行结果保存为 Markdown 和 JSON。

## Agent 架构

项目只有一个顶层聊天 Agent。普通问题由它直接选择行情、财务、技术、筛选和个人记忆工具；需要完整判断时，它会调用 `DeepResearchTool`。这个重工具内部保留五个研究角色：Quant、Fundamental、News、Sentiment 分别生成报告，最后由 CIO 汇总为 `buy`、`watch` 或 `avoid`。

```text
用户输入 -> Chat Agent -> LLMClient -> Tool Registry
                                      ├── 轻量业务工具
                                      └── DeepResearchTool
                                            └── 四类分析报告 -> CIO 决策
```

`src/core` 只提供配置、LLM、缓存和数据访问等基础能力，不依赖 Agent 或业务工具。工具调用失败时会返回稳定错误信息；单个研究角色不可用时，其余角色仍会继续运行，CIO 会给出更保守的结果。

## 目录结构

```text
.
├── cli/                 # 命令行入口、交互提示和控制台渲染
├── evaluation/          # 评测协议、实现计划和冻结股票池
├── src/                 # 项目核心源码
│   ├── agents/          # 聊天 Agent 与五角色深度研究复合工具
│   ├── core/            # 配置、缓存、限流、LLM 和本地记忆
│   ├── evaluation/      # 固定股票池评测、结算、报告和 CLI runner
│   └── tools/           # 行情、财务、新闻、技术、筛选和预测工具
├── lstm_training/       # LSTM 训练脚本、训练数据、模型和评估结果
├── tests/               # Agent、工具、CLI 和降级路径测试
├── .env.example         # 环境变量模板
└── run_agent.py         # CLI 启动脚本
```

本地生成目录不会提交到 Git：`outputs/` 存放运行报告，`data/cache/` 存放 AKShare/Tavily 缓存，`data/memory/` 存放用户运行时状态，`tmp/` 存放临时渲染和编译结果，`evaluation/data/` 和 `evaluation/reports/` 存放现实性评测的本地记录与报告。`evaluation/stock_pool.json` 是首次运行冻结的 20 股股票池，可以提交以保证答辩复现。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

在 `.env` 中填写需要的 API Key：

```text
TAVILY_API_KEY=""
LLM_API_KEY=""
LLM_MODEL_ID="gpt-4o-mini"
LLM_BASE_URL=""
```

## 常用命令

```powershell
# 自然语言聊天
python run_agent.py chat

# 单股分析
python run_agent.py analyze --code 600519 --depth standard

# 批量 watchlist 分析
python run_agent.py screen --watchlist 600519,000001,300065 --top 3

# 查看或清理缓存
python run_agent.py cache status
python run_agent.py cache clear

# 查看配置状态
python run_agent.py config status

# 每个交易日收盘且 AKShare 日线更新后运行：先结算，再预测
python run_agent.py evaluate daily

# 仅重新生成累计评测报告
python run_agent.py evaluate report
```

## 现实性评测

评测入口位于 `src/evaluation`。首次运行 `python run_agent.py evaluate daily` 时，系统会从沪深 300 自动筛选 20 只不同行业、流动性较高的股票，并冻结到 `evaluation/stock_pool.json`；之后每天继续使用同一股票池，不重新抽样。

每日评测只记录下一交易日的看涨/看跌、预计收盘价、预计涨跌幅、价格区间和置信度。完整 Agent 的预测由深度研究证据生成，并与本地 LSTM 参考结果按 85%/15% 融合。系统同时保存 2026-07-14 到 2026-07-23 的阶段趋势观点，7 月 23 日收盘后可对照阶段判断。

`evaluation/data/` 中的预测和结算记录是不可覆盖 JSON，`evaluation/reports/summary.md` 和 `summary.json` 是可重复生成的本地报告。该评测不模拟买入卖出，不计算交易收益或最大回撤；7/14-7/23 结果是阶段趋势评测，不等同于长期收益证明。

## 测试

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m unittest discover -s tests -v
```
