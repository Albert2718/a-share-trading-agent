# 数据库迁移

Alembic 负责 SQLite schema 的版本化演进。开发环境可由 FastAPI 在空数据库时自动建表，团队协作、测试环境和生产环境必须通过 `alembic upgrade head` 执行迁移。SQLite 结构变更使用 batch migration。

新增或修改 ORM 模型后，应生成一份新的 revision，而不是手动修改已有迁移。
