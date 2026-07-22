# A 股智能投研 Agent

一个以自然语言交互为核心的 A 股全栈研究平台。用户可以在网页中查询行情、管理持仓、保存长期偏好、检索自己上传的资料，并发起多角色深度研究；所有对话能力由一套 LangGraph Agent 统一编排。

> 本项目用于软件工程、Agent 架构和量化研究实验，不构成任何投资建议。

## 项目能力

- **自然语言投研**：通过聊天查询股票行情、历史走势、持仓、Memory 和知识库内容。
- **Tool Calling**：LLM 根据用户表达选择受控工具，前端同步展示规划、调用过程和结构化结果。
- **安全写入**：新增持仓和长期记忆不会由模型直接落库，必须经过用户确认且具备幂等保护。
- **深度研究**：量化、基本面、新闻、情绪和 CIO 五类研究角色协作生成单股报告。
- **RAG 知识库**：上传 PDF、Markdown 或 TXT 后进行文本提取、Chunk、BGE Embedding 和 Qdrant 检索。
- **结构化 Memory**：把投资偏好、约束、画像和关注列表保存到 SQLite，并注入后续对话。
- **异步任务**：深度研究和文档索引通过 Transactional Outbox、Redis 与 Celery 可靠执行。
- **每日 20 股评测**：以冻结股票池记录下一交易日预测、结算真实涨跌并生成累计报告。

## 技术架构

项目采用前后端分离的模块化单体。`src/agents/chat` 是唯一顶层对话 Agent；深度研究是独立领域流水线，不是第二个聊天 Agent。

```text
React + TypeScript
        │  HTTP / SSE
        ▼
FastAPI ── JWT ── ChatService
        │
        ▼
LangGraphChatAgent
        ├── READ 工具 ───────── 行情 / 持仓 / Memory / RAG
        ├── CONFIRM_WRITE ───── SQLite 待确认操作
        └── BACKGROUND ──────── Job + Transactional Outbox
                                      │
                                      ▼
                               Redis + Celery Worker
                                      │
                         ┌────────────┴────────────┐
                         ▼                         ▼
                ResearchOrchestrator       文档 Chunk / Embedding
                         │                         │
                         ▼                         ▼
                      SQLite                    Qdrant
```

### 核心技术

| 层级 | 技术 | 职责 |
| --- | --- | --- |
| 前端 | React、TypeScript、Vite | 聊天工作台、SSE 流式输出、Markdown 和工具结果卡片 |
| API | FastAPI、Pydantic | 认证、业务接口、事务边界和 Agent 接入 |
| Agent | LangGraph、OpenAI-compatible LLM | 对话状态、Tool Calling、结果总结和失败降级 |
| 业务数据 | SQLite、SQLAlchemy、Alembic | 用户、会话、持仓、Memory、任务、报告和 Outbox |
| 向量检索 | Qdrant、BGE Embedding | 用户文档 Chunk、向量索引和按用户隔离的 RAG |
| 后台任务 | Redis、Celery | 深度研究、文档索引和 Outbox 派发 |
| 市场数据 | AKShare、Tavily | A 股行情、财务数据和新闻搜索 |

## 目录结构

```text
.
├── backend/             # FastAPI、SQLAlchemy、Alembic、Celery 与 Web 工具适配
├── frontend/            # React + TypeScript 网页工作台
├── src/
│   ├── agents/chat/     # 项目唯一 LangGraph 对话 Agent
│   ├── research/        # 可复用的多角色深度研究流水线
│   ├── tools/           # 行情、新闻、LSTM 与深度研究工具入口
│   ├── core/            # 配置、LLM、缓存、限流和数据访问
│   └── evaluation/      # 固定 20 股预测、结算与报告引擎
├── scripts/             # 独立运维入口，例如每日 20 股评测
├── evaluation/          # 评测协议、冻结股票池与本地运行结果
├── lstm_training/       # 课程 LSTM 训练代码与模型产物
├── tests/               # Agent、工具、研究和评测测试
├── docs/                # 产品需求、系统架构、文件职责和路线图
├── images/              # 产品视觉参考
└── docker-compose.yml   # 本地全栈开发编排
```

逐文件职责见 [项目结构](docs/project-structure.md)，完整调用链见 [系统架构](docs/architecture.md)。

## 快速开始

### 1. 准备环境

需要安装：

- Docker Desktop（包含 Docker Compose）
- Git
- 可用的 OpenAI-compatible LLM API Key
- Tavily API Key（新闻搜索需要；不使用新闻能力时可暂不配置）

克隆项目并创建本地配置：

```powershell
git clone https://github.com/Albert2718/a-share-trading-agent.git
Set-Location a-share-trading-agent
Copy-Item .env.example .env
```

至少填写以下配置：

```dotenv
LLM_API_KEY="your-api-key"
LLM_MODEL_ID="your-model-id"
LLM_BASE_URL="https://your-openai-compatible-endpoint/v1"
TAVILY_API_KEY="your-tavily-key"
JWT_SECRET_KEY="replace-with-a-long-random-string"
```

`LLM_BASE_URL` 为空时使用 OpenAI 默认地址。真实密钥只应保存在 `.env`，不要提交到 Git。

### 2. 启动全栈服务

```powershell
docker compose up --build -d
docker compose ps
```

启动后访问：

- 网页端：<http://localhost:5173>
- FastAPI 文档：<http://localhost:8000/docs>
- API 健康检查：<http://localhost:8000/health>

首次启动需要构建 Python 镜像并安装前端依赖，耗时会比后续启动更长。进入网页后先注册用户，再通过聊天或左侧工作区使用各项能力。

常用容器命令：

```powershell
# 查看服务状态
docker compose ps

# 跟踪 API 和 Worker 日志
docker compose logs -f api worker

# 重启网页端
docker compose restart web

# 停止服务；不会删除 Qdrant volume
docker compose down
```

## 主要使用场景

可以直接向 Agent 输入：

```text
分析 600519 最近的行情和风险。
我有哪些持仓？
记录我持有 100 股贵州茅台，成本价 1250 元。
以后分析时偏保守，避免高波动股票。
从我上传的财报中检索公司现金流相关内容。
对 600519 发起深度研究，并结合我的持仓和风险偏好。
```

查询类工具会直接执行；持仓和 Memory 写入会在页面上等待确认；深度研究会创建后台任务，可在“研究任务”中查看进度和报告。

## 数据流与安全边界

1. 前端将登录用户的消息通过 SSE 发送给 FastAPI。
2. `ChatService` 加载会话历史和结构化 Memory，并绑定当前用户可用的工具。
3. LangGraph 在 `chat_agent → tools → chat_agent` 图中完成工具选择和回答生成。
4. 读取工具直接返回结果；写入工具只创建待确认动作；后台工具创建 Job 和 Outbox 事件。
5. API 请求或 Worker 在统一事务边界提交 SQLite，Repository 不自行提交事务。
6. RAG 检索始终按 `user_id` 过滤，聊天、持仓、Memory、文档和报告均进行用户隔离。

运行数据默认保存在本地且不提交到 Git：

- `data/app.db`：SQLite 业务数据库
- `data/uploads/`：用户上传的原始文档
- `data/models/`：Embedding 模型缓存
- `data/cache/`：市场和新闻数据缓存
- `evaluation/predictions/`、`outcomes/`、`reports/`：本地评测结果

## 开发与测试

Python 开发统一使用 Conda 环境，避免污染系统 Python：

```powershell
conda create -n trading-agent python=3.11
conda activate trading-agent
python -m pip install -r requirements.txt
python -m pip install -r backend/requirements-dev.txt
```

运行 Python 回归测试：

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
conda run -n trading-agent python -m pytest -q
```

运行前端测试与生产构建：

```powershell
Set-Location frontend
npm install
npm test
npm run build
```

数据库结构使用 Alembic 管理。容器启动 API 时会自动执行：

```text
alembic upgrade head
```

## 每日 20 股评测

评测模块独立于网页 Agent，不经过 FastAPI、SQLite、Redis 或 Qdrant。首次运行会从沪深 300 选择并冻结 20 只股票到 `evaluation/stock_pool.json`，之后持续使用同一股票池以保证跨日可比性。

每个交易日收盘且 AKShare 数据更新后运行：

```powershell
conda run -n trading-agent python scripts/run_evaluation.py daily
```

仅重建累计报告：

```powershell
conda run -n trading-agent python scripts/run_evaluation.py report
```

评测会记录方向、预计收盘价、价格区间和置信度，并在下一交易日数据可用后结算方向命中率与价格误差。具体口径见 [评测协议](evaluation/protocol.md)。

## 文档导航

- [产品需求](docs/requirements.md)
- [系统架构与完整数据流](docs/architecture.md)
- [项目结构与核心文件职责](docs/project-structure.md)
- [开发路线](docs/roadmap.md)
- [Research 工具与领域流水线边界](docs/research-tool-architecture.md)
- [后端说明](backend/README.md)
- [前端说明](frontend/README.md)

## 当前边界

- 这是本地开发版本，尚未包含生产反向代理、HTTPS、托管密钥和公网部署方案。
- 文档解析支持文本型 PDF、Markdown 和 TXT，扫描版 PDF 暂不提供 OCR。
- `quick`、`standard`、`full` 字段仅兼容历史接口，当前统一执行同一套研究流程。
- LSTM 与固定 20 股预测属于课程评测模块，不参与网页 Agent 的主请求链路。

## License

仓库当前未声明开源许可证；未经许可，请勿将代码或生成的研究结果用于商业用途。
