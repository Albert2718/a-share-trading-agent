# 项目结构与核心文件职责

## 顶层目录

```text
Project/
├─ frontend/          React + TypeScript 网页端
├─ backend/           FastAPI、SQLite、Celery、Qdrant 适配层
├─ src/               与传输层无关的 Agent、研究、行情和评测核心
├─ scripts/           可直接运行的运维入口
├─ evaluation/        20 股评测协议、冻结股票池和本地结果
├─ lstm_training/     课程 LSTM 的训练脚本、模型和实验产物
├─ tests/             共享核心的单元测试
├─ docs/              产品、架构、结构和路线文档
├─ data/              SQLite、上传文件、缓存与模型缓存（运行数据）
├─ handoffs/          按工作范围保存的阶段性交接文档
├─ images/            产品视觉参考图
├─ outputs/           本地生成的临时报告
└─ ref/               只读外部参考项目，不参与构建和运行
```

## 根目录核心文件

- `README.md`：给开发者提供项目定位、运行方式、目录入口和常用命令。
- `docker-compose.yml`：编排 Web、API、Worker、Beat、Redis 和 Qdrant 六个本地服务。
- `.env.example`：声明运行项目所需的环境变量模板，不保存真实密钥。
- `requirements.txt`：安装 `src/` 研究与评测核心所需的 Python 依赖。
- `pytest.ini`：把根目录回归测试限定在本项目测试集，隔离 `ref/` 参考代码和运行缓存。

## 前端 `frontend/`

- `src/main.tsx`：加载全局样式和霞鹜文楷字体，并把 React 应用挂载到页面根节点。
- `src/App.tsx`：维护登录态和工作台级数据，组织聊天主区、Memory、知识库、工具侧栏与报告弹窗。
- `src/api/client.ts`：集中定义前后端 DTO，并通过统一 `request()` 封装 API 地址、JWT、JSON/FormData 和错误处理。
- `src/components/AuthPanel.tsx`：提供注册与登录表单，并把认证结果交回 `App`。
- `src/components/ChatPanel.tsx`：加载会话、流式发送自然语言消息、自动调整多行输入高度，并处理持仓/Memory 的确认操作。
- `src/components/AgentExecution.tsx`：把实时 Agent 状态和持久化工具结果渲染为执行时间线及行情、持仓、RAG、Memory、研究任务卡片。
- `src/components/ToolWorkspace.tsx`：承载从左侧导航进入的深度研究、持仓和研究任务工作区。
- `src/components/ResearchPanel.tsx`：通过结构化表单提交单股深度研究任务。
- `src/components/PositionForm.tsx`：通过结构化表单新增或更新持仓。
- `src/components/JobTable.tsx`：展示后台研究任务状态并提供报告入口。
- `src/components/ReportModal.tsx`：把持久化研究结果转换成中文结论、证据、风险、Analyst 指标和个人上下文视图，并折叠保留原始载荷。
- `src/components/MemoryPanel.tsx`：查看、创建、修改和删除结构化长期记忆。
- `src/components/KnowledgePanel.tsx`：上传、查询和删除用户文档，并展示 RAG 来源。
- `src/styles.css`：定义登录页、聊天工作台、工具侧栏、详情页和响应式布局的全部视觉样式。
- `vite.config.ts`：配置 Vite 开发服务器、React 插件以及 `/api` 到 FastAPI 的代理。
- `vitest.config.ts`：配置 jsdom 前端测试环境和测试初始化文件。
- `package.json`：声明前端依赖以及 `dev`、`build`、`test` 命令。

## 后端 `backend/app/`

### 应用与基础设施

- `main.py`：创建 FastAPI 应用、安装 CORS、注册所有路由并提供健康检查。
- `core/config.py`：从环境变量读取数据库、Redis、Qdrant、Embedding、上传和 JWT 配置。
- `core/database.py`：创建异步 SQLAlchemy Engine/Session，并统一控制请求事务提交和回滚。
- `core/security.py`：负责密码哈希校验以及 JWT 的创建和解析。
- `api/dependencies.py`：把数据库 Session 和经过 JWT 校验的当前用户注入路由函数。
- `models/domain.py`：集中定义用户、会话、消息、持仓、Memory、知识文档、任务、报告、确认动作和 Outbox 的 ORM 模型。

### HTTP 路由

- `api/routes/auth.py`：暴露注册、登录和当前用户接口。
- `api/routes/chat.py`：暴露会话读取、普通消息、SSE 流式消息和待确认工具执行接口。
- `api/routes/portfolio.py`：暴露持仓列表与手动写入接口。
- `api/routes/memory.py`：暴露结构化 Memory 的增删改查接口。
- `api/routes/knowledge.py`：暴露文档上传、删除、列表和 RAG 问答接口。
- `api/routes/research.py`：暴露研究任务创建、状态查询和报告读取接口。

### Agent 工具与业务服务

- `agent_runtime/specs.py`：定义异步工具规范、读/确认写/后台三类副作用策略和登录用户上下文绑定器。
- `agent_runtime/tools.py`：注册网页 Agent 可调用的行情、持仓、Memory、RAG 和研究工具。
- `services/chat_service.py`：组装会话历史、Memory 上下文、LangGraph 与工具，并持久化回答和确认动作。
- `services/auth_service.py`：协调用户仓储、密码安全和 JWT 完成注册登录。
- `services/memory_service.py`：把结构化 Memory 转换成系统提示词上下文并处理更新。
- `services/research_service.py`：创建研究任务和 Outbox 事件，并在 Worker 中调用共享研究核心保存报告。
- `services/knowledge_service.py`：处理上传去重、后台索引、向量检索、基于来源的回答和文档删除。
- `services/portfolio_service.py`：将持久化仓位与即时行情组合为现价、市值和未实现盈亏快照。
- `services/document_processing.py`：从 PDF/Markdown/TXT 提取文本并用递归分隔器生成重叠 chunk。
- `services/vector_store.py`：加载 BGE Embedding，并在 Qdrant 中创建、写入、过滤检索和删除向量。
- `services/outbox_service.py`：把已提交的 Outbox 业务事件可靠映射为 Celery 任务。

### 数据访问与后台任务

- `repositories/user_repository.py`：封装用户按邮箱、用户名和 ID 的查询与创建。
- `repositories/chat_repository.py`：封装会话和消息的读取、排序、写入与更新时间维护。
- `repositories/portfolio_repository.py`：封装默认组合创建、持仓列表和按股票代码 upsert。
- `repositories/memory_repository.py`：封装按用户隔离的 Memory 查询、upsert、更新和删除。
- `repositories/knowledge_repository.py`：封装文档、chunk、文件哈希去重和索引状态的数据库操作。
- `repositories/research_repository.py`：封装研究任务领取、状态更新和报告读写。
- `repositories/tool_action_repository.py`：通过原子状态更新保证确认写入只能执行一次。
- `repositories/outbox_repository.py`：封装 Outbox 事件创建、领取、成功和失败重试状态。
- `workers/celery_app.py`：创建 Celery 实例并配置 Broker、任务发现和 Beat 调度。
- `workers/tasks.py`：提供研究执行、文档索引和 Outbox 派发三个 Celery 消费入口。

### 数据契约与迁移

- `schemas/auth.py`：定义认证请求、用户响应和 Token 响应模型。
- `schemas/chat.py`：定义消息请求、消息响应和会话响应模型。
- `schemas/portfolio.py`：定义持仓写入与返回模型。
- `schemas/memory.py`：定义 Memory 创建、局部更新和返回模型。
- `schemas/knowledge.py`：定义文档、RAG 查询、来源和回答模型。
- `schemas/research.py`：定义研究任务和报告的 API 模型。
- `alembic/versions/*.py`：按时间保存 SQLite 结构演进，已有迁移只增补不回写。

## 共享核心 `src/`

### 唯一对话 Agent

- `agents/chat/workflow.py`：构建唯一的 LangGraph `StateGraph`，并以 `LangGraphChatAgent.run()` 返回统一执行结果。
- `agents/chat/nodes.py`：实现 LLM 节点、工具节点、轮次限制、异常降级和图分支判断。
- `agents/chat/state.py`：定义消息、工具调用、工具结果、待确认动作和最终回答组成的图状态。
- `agents/chat/prompts.py`：生成带 Memory 上下文、工具使用和安全约束的系统提示词。
- `agents/chat/README.md`：说明唯一 LangGraph Agent 的边界、节点流转和事件协议。

### 后台深度研究

- `tools/deep_research.py`：作为 Agent 可调用的薄工具入口，把单股参数适配成研究流水线调用。
- `research/orchestrator.py`：依次协调量化、基本面、新闻、情绪与 CIO，并让单角色失败可降级。
- `research/schemas.py`：定义候选股票、分析上下文、各分析报告和最终决策的数据结构。
- `research/prompts.py`：保存新闻分析与 CIO 决策使用的 LLM 提示词。
- `research/utils.py`：提供报告时间格式以及跨研究/评测共用的密钥和 URL 脱敏。
- `research/analysts/quant.py`：用历史行情、技术指标和可选 LSTM 信号生成量化评分。
- `research/analysts/fundamental.py`：用估值与财务指标生成基本面评分和风险。
- `research/analysts/news.py`：采集公告、新闻和 Tavily 结果并提炼事件影响。
- `research/analysts/sentiment.py`：根据市场热度、资金和价格行为生成情绪评分。
- `research/analysts/cio.py`：综合四类报告与风险偏好生成最终 `buy/watch/avoid` 决策。
- `research/README.md`：说明研究流水线不是第二个对话 Agent，以及它与工具、Worker、评测的调用边界。

### 基础能力与工具

- `core/config.py`：只从项目 `.env` 和进程环境读取研究核心配置。
- `core/llm.py`：统一封装 OpenAI-compatible 普通对话、结构化输出和 Tool Calling。
- `core/cache.py`：在本地文件缓存外部数据，并记录抓取时间和缓存元数据。
- `core/rate_limiter.py`：按外部端点限制调用频率。
- `core/data_access.py`：把缓存、限流、在线加载和失败回退组合成统一数据读取入口。
- `tools/market_data.py`：封装 AKShare 的候选股、实时行情、日线、估值、财务和市场情绪数据。
- `tools/market.py`：把行情数据整理成适合网页 Agent 返回的稳定字典结构。
- `tools/news_search.py`：通过 Tavily 搜索股票新闻，并在结果中去除凭据。
- `tools/lstm.py`：加载课程模型并根据收盘价窗口生成参考收益率信号。
- `tools/utils.py`：提供股票代码规范化、数值安全转换、限幅和去重工具。
- `tools/README.md`：说明工具入口的轻量职责以及与 Agent、Research 流水线的分层关系。

### 固定 20 股评测

- `evaluation/runner.py`：校验收盘时间和数据完整性，结算到期预测并并发生成当日 20 股预测。
- `evaluation/stock_pool.py`：从沪深 300 按行业、历史长度和流动性选择并冻结 20 股池。
- `evaluation/market.py`：为评测提供交易日、沪深 300 成分、行业和不复权历史行情。
- `evaluation/forecasting.py`：组合截止时点安全的研究证据、LLM 观点和 LSTM 参考信号形成预测。
- `evaluation/settlement.py`：用目标交易日真实收盘价生成 Outcome，并识别复权异常和待结算记录。
- `evaluation/metrics.py`：计算方向命中率、价格误差和覆盖率等指标。
- `evaluation/storage.py`：以不可覆盖 JSON 和哈希链保存预测与结果，防止事后改写。
- `evaluation/reporting.py`：从预测与结果重建 JSON/Markdown 汇总报告。
- `evaluation/models.py`：定义股票池、证据、预测、结果和指标的不可变数据模型。
- `evaluation/calendar.py`：计算给定日期后的下一交易日。
- `evaluation/prompts.py`：定义评测 LLM 的输出约束与结构化 Schema。

## 独立入口与数据目录

- `scripts/run_evaluation.py`：提供 `daily` 和 `report` 两个固定 20 股评测命令，完全独立于已删除的 CLI。
- `evaluation/protocol.md`：定义不可回填、截止时间、结算方式和报告口径。
- `evaluation/stock_pool.json`：保存首次选择后冻结的 20 只股票，保证跨日可比性。
- `lstm_training/train_lstm_model.py`：完成课程 LSTM 数据切窗、训练、验证、选参、绘图和模型保存。

`__init__.py` 只声明 Python 包或集中导出稳定接口，目录内 `README.md` 解释局部实现约束，测试文件与被测模块一一对应，因此不再逐项重复列出。
