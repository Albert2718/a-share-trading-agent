# 后台任务

Celery Worker 消费深度研究、文档索引和 Outbox Dispatcher 任务；Celery Beat 定期触发 Dispatcher。API 只在 SQLite 事务中创建 `outbox_events`，不会在提交前直接调用 `.delay()`。

研究和文档消费者会先原子抢占业务记录。重复消息只允许一个消费者从 `pending/queued` 进入 `running/processing`，从而避免重复报告和重复索引。

Celery Worker 处理不应阻塞 HTTP 请求的工作：

- `research.run`：运行多 Agent 深度研究。
- `knowledge.index`：解析上传文档、递归切块、生成中文 Embedding 并写入 Qdrant。

任务只接收稳定 ID，业务数据从 SQLite 重新读取。当前保持单 Worker，降低 SQLite 并发写锁风险。
