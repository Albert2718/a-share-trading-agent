# 项目文档

本目录只保留长期有效的产品、架构和开发路线文档，临时问题记录与阶段性交接不在这里长期堆积。

- [产品需求](requirements.md)：产品目标、核心场景、交互要求和安全边界。
- [系统架构](architecture.md)：唯一 LangGraph Agent、FastAPI、SQLite、Celery、Qdrant 和前端的数据流。
- [项目结构](project-structure.md)：目录边界以及每个核心文件的一句话职责。
- [开发路线](roadmap.md)：已经完成的基础重构与下一阶段优化项。
- [Research 工具目录重构建议](research-tool-architecture.md)：说明为什么 Research 应作为工具暴露、核心流水线应如何独立，以及安全迁移顺序。

目录级实现说明保留在对应源码目录的 `README.md` 中；可参考的外部项目全部放在根目录 `ref/`，该目录不属于本项目运行链路。
