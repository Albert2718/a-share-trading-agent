# A 股多 Agent 研究助手

这是一个面向 A 股研究的命令行 Agent 项目，用 LangGraph 编排自然语言交互，并结合 AKShare、Tavily、OpenAI-compatible LLM 和本地 LSTM 模型生成研究报告。项目用于课程实验和研究辅助，不构成投资建议。

## 功能概览

- 自然语言聊天入口：识别用户意图并调用行情、财务、技术、筛选和个人记忆工具。
- 单股深度分析：由量化、基本面、新闻、情绪和 CIO Agent 生成 `buy`、`watch` 或 `avoid` 建议。
- 批量筛选：支持 watchlist 或热门股票池分析。
- 本地缓存与限流：AKShare 数据经统一数据访问层读取，减少重复请求。
- 报告输出：CLI 运行结果保存为 Markdown 和 JSON。

## 目录结构

```text
.
├── cli/                 # 命令行入口、交互提示和控制台渲染
├── src/                 # 项目核心源码
│   ├── chat_agent.py    # 自然语言聊天 Agent 外壳
│   ├── core/            # 配置、缓存、限流、LLM 和本地记忆
│   ├── graph/           # LangGraph 状态、节点、工具注册和工作流
│   └── tools/           # 行情、财务、技术、筛选、预测和深度研究工具
├── experiments/         # 课程实验脚本、Notebook 和训练数据
├── artifacts/models/    # 训练得到的模型、指标和图表
├── docs/                # 架构、API、展示材料和课程文档
├── tests/               # 后续测试目录
├── .env.example         # 环境变量模板
└── run_agent.py         # CLI 启动脚本
```

本地生成目录不会提交到 Git：`outputs/` 存放运行报告，`data/cache/` 存放 AKShare/Tavily 缓存，`data/memory/` 存放用户运行时状态，`tmp/` 存放临时渲染和编译结果。

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
```

## 文档

- `docs/architecture.md`: 项目架构和运行流程。
- `docs/apis.md`: 数据源、API Key 和边界规则。
- `docs/pre.md`、`docs/pre/`: 课程展示材料。

## GitHub 上传前检查

提交前确认 `.env` 未被加入 Git，并避免提交 `outputs/`、`data/cache/`、`data/memory/`、`tmp/`、`__pycache__/` 等本地生成物。
