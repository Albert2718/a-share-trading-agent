# 系统架构

## 架构结论

项目采用前后端分离的模块化单体：React 负责交互，FastAPI 负责认证与业务 API，`src/agents/chat` 拥有唯一 LangGraph 对话 Agent，SQLite 保存结构化业务数据，Redis/Celery 执行后台任务，Qdrant 保存用户文档向量。

```text
React
  -> FastAPI ChatService
  -> src/agents/chat/LangGraphChatAgent
       ├─ READ 工具 -> 行情 / 持仓 / Memory / RAG
       ├─ CONFIRM_WRITE -> tool_actions -> SQLite
       └─ BACKGROUND -> Job + outbox_events
                            -> Celery Beat / Redis / Worker
                            -> ResearchOrchestrator
```

## 目录所有权

```text
backend/                 FastAPI、SQLAlchemy、工具策略、Celery 与 Web 业务适配
frontend/                React + TypeScript 聊天工作台
src/agents/chat/         唯一 StateGraph、Agent 节点、Tools 节点和系统提示词
src/research/            后台复合研究流水线、领域模型与五类研究角色
src/tools/               Agent 工具入口以及行情、新闻、模型等可复用能力
src/evaluation/          固定股票池预测与结算引擎
scripts/                 每日 20 股评测等独立运维脚本，不包含 Agent
data/                    SQLite、上传文件、模型和运行缓存
evaluation/              评测协议、冻结股票池与不可变运行结果
ref/                     只读外部参考项目，不参与构建和运行
```

## 唯一 Agent

`src/agents/chat/workflow.py` 构建项目唯一 `StateGraph`，执行顺序为 `chat_agent -> tools -> chat_agent`。FastAPI 加载最近会话与结构化 Memory，再通过 `BoundToolExecutor` 将登录用户上下文绑定到后端 `ToolSpec`；`backend/app/agent_runtime` 只负责工具定义和安全策略，不再拥有第二套图。

`ResearchOrchestrator` 不是第二个顶层聊天 Agent，而是 `research_submit` 触发的后台复合工具；它调度 Quant、Fundamental、News、Sentiment 和 CIO，并将结果保存为研究报告。

## 数据与事务

- SQLite：用户、会话、消息、持仓、Memory、研究任务、报告、文档元数据、确认操作和 Outbox。
- Qdrant：用户文档 chunk 向量及 `user_id`、`document_id`、`stock_code`、`source_type`、页码等检索 payload。
- Redis：Celery Broker 和适合短期复用的数据缓存，不作为业务事实来源。
- 文件系统：`data/uploads` 保存原始用户文档，`data/models` 保存本地模型缓存。

Repository 只负责查询、写入与 `flush()`；FastAPI 请求或 Worker 统一提交事务。研究与索引事件和业务数据在同一事务写入 Outbox，避免数据库成功但消息丢失。

## Memory 与 RAG

结构化 Memory 保存 `profile`、`preference`、`constraint` 和 `watchlist`，经用户确认写入 SQLite，并在后续对话中注入系统上下文。持仓必须进入 `positions`，不能混入 Memory。

用户文档经过文本提取、递归 chunk、BGE 中文 Embedding 和 Qdrant upsert；查询时按 `user_id` 过滤并返回来源。财报、公告、新闻、分析文章和个人笔记共用一套索引，通过 `source_type` 元数据区分和过滤。当前默认支持 PDF、Markdown 和 TXT，扫描 PDF 暂不包含 OCR。

## 完整数据流

### 1. 网页启动、认证与公共事务边界

```text
main.tsx.createRoot()
  -> App
  -> AuthPanel
  -> api.register()/api.login()
  -> client.request()
  -> auth.register()/auth.login()
  -> AuthService
  -> UserRepository
  -> SQLite
  -> JWT + User -> App.auth
```

登录后，`App.refresh()` 并发调用任务、持仓、Memory 和文档列表接口；每个受保护请求都先经过 `get_current_user()` 解码 JWT，并由 `get_db_session()` 在路由成功后统一 `commit()`、异常时统一 `rollback()`，Repository 自身只做查询、`add()` 和 `flush()`。

### 2. 自然语言对话与 LangGraph

```text
ChatPanel.send()（先乐观显示用户消息）
  -> api.streamMessage()
  -> POST /chat/conversations/{id}/messages/stream
  -> chat.send_message()
  -> ChatService.respond()
       ├─ ChatRepository.recent_messages()
       ├─ MemoryService.context_for_user()
       ├─ build_web_tool_registry() + WebToolContext
       └─ LangGraphChatAgent.run()
            -> chat_agent_node()
            -> LLMClient.chat_with_tools_stream()
            -> should_continue()
                 ├─ end -> AgentRunResult
                 └─ tools -> tool_node()
                              -> BoundToolExecutor.execute()
                              -> AsyncToolRegistry.execute()
                              -> ToolSpec.handler
                              -> chat_agent_node() 再总结
  -> ChatRepository.add_message(user/assistant)
  -> SSE planning / tool_started / tool_completed / awaiting_confirmation
         / background_task_created / synthesizing -> Agent 执行时间线
  -> SSE token 事件 -> ChatPanel 增量显示 Markdown
  -> SQLite commit -> SSE message 事件
  -> ChatPanel 再取 conversation，并渲染持久化工具时间线和结构化结果卡片
```

`LangGraphChatAgent` 是唯一顶层对话 Agent；状态在 `AgentState` 中流转，最多允许六轮工具调用，工具结果先转成 `role=tool` 消息再交给 LLM 生成面向用户的最终回答。工具节点通过只读事件回调报告阶段、耗时和安全展示载荷，回调失败不会中断 Agent；最终 `tool_results` 随 Assistant 消息保存，因此页面刷新后执行记录和结果卡片仍然存在。LLM 请求失败时，`ChatService._fallback()` 只为持仓、持仓查询和研究提交提供可验证的规则降级，不伪造行情或研究结论。

### 3. 读取型工具

- 行情：`_market_quote()` / `_market_history()` 使用 `asyncio.to_thread()` 调用 `get_realtime_price()` / `get_daily_price()`，再经过 `AkshareMarketData`、`DataAccessLayer.fetch()`、`CacheManager` 和 `RateLimiter` 获取 AKShare 在线数据或合规缓存。
- 持仓：`_portfolio_list()` 调用 `PortfolioService.list_snapshots()`，将 SQLite 成本仓位与即时行情组合为市值和未实现盈亏；行情快照不写回数据库。
- Memory：`_memory_list()` 调用 `MemoryRepository.list_memories()`，返回已确认且有效的结构化记忆。
- RAG：`_knowledge_search()` 调用 `KnowledgeService.search()`，再由 `VectorStore.search()` 生成查询向量、按 `user_id` 和可选文档/股票过滤 Qdrant，最后把来源片段交回 LLM。

### 4. 需要用户确认的写入

```text
LLM 调用 portfolio_upsert / memory_upsert
  -> AsyncToolRegistry.execute()
  -> 发现 ToolEffect.CONFIRM_WRITE
  -> 不执行 handler，只返回 pending_action
  -> ChatService.respond()
  -> ToolActionRepository.create(status=pending)
  -> ChatPanel 显示确认按钮
  -> ChatPanel.confirm()
  -> POST /chat/.../confirm/{message_id}
  -> ChatService.confirm()
  -> ToolActionRepository.claim_pending() 原子改为 executing
  -> PortfolioRepository.upsert_position() 或 MemoryRepository.upsert()
  -> ToolActionRepository.complete()
  -> SQLite commit -> UI 刷新
```

`claim_pending()` 同时匹配 `message_id`、`conversation_id`、`user_id` 和 `pending` 状态，因此重复点击、跨用户请求或已完成动作都不会重复写入。

### 5. 后台深度研究

```text
自然语言 research_submit 或 ResearchPanel.submit
  -> ResearchService.submit()
  -> ResearchRepository.create_job()
  -> OutboxRepository.add("research.requested")
  -> 同一 SQLite 事务 commit
  -> Celery Beat: tasks.dispatch_outbox()
  -> dispatch_pending_events()
  -> Redis Broker -> tasks.queue_research_job()
  -> execute_research_job()
  -> _build_personal_context()
       -> PortfolioRepository.list_positions()
       -> MemoryRepository.list_memories()
       -> KnowledgeService.search()
  -> _run_existing_research()
  -> run_deep_research()
  -> DeepResearchTool.run()
  -> ResearchOrchestrator.candidates_from_codes()
  -> ResearchOrchestrator.analyze()
       -> QuantAnalyst.analyze()
       -> FundamentalAnalyst.analyze()
       -> NewsAnalyst.analyze()
       -> SentimentAnalyst.analyze()
       -> CIOAgent.decide_one()/build_report()（结合个性化上下文）
  -> ResearchRepository.create_report()
  -> ResearchJob status=completed
  -> SQLite commit
  -> App 轮询 jobs -> JobTable -> ReportModal
```

每个 Analyst 通过同一个 `AkshareMarketData`/`DataAccessLayer` 访问市场数据；单个角色异常由 `_safe_analyze()` 转成 unavailable 报告，CIO 异常则生成零仓位的保守结果。Outbox 保证研究任务与事件要么同时写入，要么同时回滚。

### 6. 文档上传、Chunk、向量索引与 RAG 回答

```text
KnowledgePanel 上传文件
  -> api.uploadDocument()
  -> knowledge.upload_document()
  -> KnowledgeService.create_upload()
       -> 校验扩展名/大小/哈希去重
       -> data/uploads/{user}/{document}/ 保存原文件
       -> KnowledgeRepository.create_document()
       -> OutboxRepository.add("knowledge.index_requested")
  -> commit
  -> Beat/Outbox -> Redis -> tasks.queue_knowledge_document()
  -> KnowledgeService.index_document()
       -> parse_document()
       -> split_pages()
       -> embed_passages()
       -> VectorStore.upsert_document() -> Qdrant
       -> KnowledgeRepository.replace_chunks() -> SQLite
       -> document.status=ready
```

独立知识库问答由 `KnowledgePanel -> api.queryKnowledge() -> query_knowledge() -> KnowledgeService.answer()` 发起：`embed_query()` 生成查询向量，Qdrant 返回片段，`_answer_with_context()` 强制 LLM 只依据这些片段生成带 `[1]`、`[2]` 来源编号的答案；聊天中的 RAG 则复用同一个 `KnowledgeService.search()`，由 LangGraph 完成最终表述。

### 7. 固定 20 股预测与结算

```text
scripts/run_evaluation.py daily
  -> EvaluationRunner.run_daily()
       -> _require_after_close()/数据完整性/哈希链校验
       -> StockPoolManager.freeze()
       -> SettlementService.settle_due()
       -> _forecast_missing_kind()（最多 3 线程）
            -> EvaluationForecaster.forecast()
            -> EvaluationMarketData.raw_history()
            -> ResearchOrchestrator.analyze()
            -> LLMClient.structured()
            -> LSTMPredictor.predict_return()
            -> blend_forecast()
       -> EvaluationStorage.append_prediction()
       -> ReportBuilder.build()
  -> evaluation/{predictions,outcomes,batches,reports}
```

这条链路不经过 React、FastAPI、SQLite、Redis 或 Qdrant；它直接从 AKShare 获取截止当日收盘后的数据，先结算到期记录，再生成不可覆盖的新预测，并通过 `EvaluationStorage` 哈希链检查阻止历史结果被静默改写。

## 安全策略

- `READ` 工具可以直接执行。
- `CONFIRM_WRITE` 工具只生成持久化待确认动作，用户确认后才执行一次。
- `BACKGROUND` 工具通过 Job 与 Transactional Outbox 进入 Celery。
- JWT 只由 FastAPI 创建和验证；密钥只存在服务端环境变量。
- LLM 和工具异常转换为稳定错误，不返回密钥、请求头或内部路径。

## 实验边界

LSTM、固定 20 股预测和历史命中评测是课程实验模块，不参与网页 Agent 的主请求链路；每日评测通过 `scripts/run_evaluation.py` 独立运行。
