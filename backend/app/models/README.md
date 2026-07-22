# 数据库模型

本目录定义 SQLAlchemy ORM 模型。模型对应 SQLite 中的业务表，并且不包含 API 请求校验或 Agent 业务规则。

当前覆盖用户、对话、持仓、价格预警、研究任务、研究报告、结构化 Memory、知识库文档和 chunk 映射。`KnowledgeChunk` 保存文本、页码和 Qdrant point id；向量本身只保存在 Qdrant。
