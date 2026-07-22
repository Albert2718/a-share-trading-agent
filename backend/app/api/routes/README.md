# API 路由

每个文件对应一个业务边界：认证、研究、持仓、聊天、长期记忆和知识库。所有用户拥有的数据查询都必须经过 `CurrentUser`，从查询条件层面实施数据隔离。

- `/memory`：结构化 Memory 增删改查。
- `/knowledge/documents`：上传、查看和删除知识库文档。
- `/knowledge/query`：执行当前用户范围内的 RAG 查询。

原文件保存到 `data/uploads`，Celery Worker 负责解析、chunk、Embedding 和 Qdrant 写入。

聊天同时保留普通 JSON 消息接口和 SSE 流式接口；网页默认使用 SSE，待确认写入仍走独立确认接口。
