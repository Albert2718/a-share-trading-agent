# 后端服务

本目录是全栈项目的 Python 后端，使用 FastAPI 提供 HTTP API，SQLite 保存业务数据，Qdrant 提供向量检索，Redis 与 Celery 处理深度研究和文档索引任务。

`app/` 是应用代码；`alembic/` 存放数据库迁移；`Dockerfile` 定义 API 与 Worker 共用的运行镜像。

开发环境由项目根目录的 `docker-compose.yml` 统一启动。现有根目录 `src/` 中的 Agent 代码仍被复用，但不会再直接承担 API、用户数据或任务管理职责。
