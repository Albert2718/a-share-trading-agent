# 业务服务层

服务层编排认证、研究任务、持仓、Memory 和 RAG。它依赖 Repository 和 Agent 适配器，但不依赖 FastAPI 的 `Request` 或 `Response` 对象，因此可以同时被 API、Celery Worker 和测试调用。

- `chat_service.py`：连接 LangGraph Runtime、持久化消息和执行幂等确认。
- `memory_service.py`：把有效长期记忆组装为 Agent 上下文。
- `document_processing.py`：文本提取和递归 chunk。
- `vector_store.py`：FastEmbed 中文向量与 Qdrant 检索。
- `knowledge_service.py`：分类上传、索引、删除、过滤检索和带引用 RAG 回答。
- `portfolio_service.py`：并发读取持仓行情并动态计算市值、未实现盈亏和收益率。
- `outbox_service.py`：把已经提交的业务事件可靠发布给 Celery。

持仓和长期记忆都必须经过确认；实时行情不能写入 Memory 或向量库。
