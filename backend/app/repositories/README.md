# 数据访问层

Repository 只封装数据库读写与所有权过滤，不调用 LLM、AKShare 或 Celery。服务层通过 Repository 组合业务流程，避免 API 路由直接拼接 SQL。

Repository 不拥有事务提交权：写方法只执行 `flush()`；HTTP 请求由数据库依赖统一提交或回滚，Worker 的阶段性事务由对应 Service 明确提交。

- `memory_repository.py`：长期记忆的查询、upsert 和删除。
- `knowledge_repository.py`：上传文档、索引状态和 chunk 映射。
- `tool_action_repository.py`：原子抢占并完成 Agent 待确认写操作。
- `outbox_repository.py`：业务事务内持久化待投递 Celery 事件。

所有用户数据查询都必须携带 `user_id`；Qdrant 检索使用相同的用户隔离条件。
