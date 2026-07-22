# Research 流水线

本目录是与 Web、Celery 和 LangGraph 解耦的深度研究领域核心，不是第二个对话 Agent。

## 文件职责

- `orchestrator.py`：串联量化、基本面、新闻、情绪和 CIO 汇总，并隔离单分析器失败。
- `schemas.py`：定义研究上下文、分析报告、股票决策和最终报告。
- `prompts.py`：保存研究专用的结构化输出提示词。
- `utils.py`：提供时间格式、敏感信息脱敏和安全转换。
- `analysts/`：实现五类专业分析器；这些类只生成研究证据或结论，不管理对话状态。

## 调用边界

LangGraph 不直接导入本目录，而是调用 Web 工具 `research_submit` 创建后台任务；Worker 最终通过 `src/tools/deep_research.py` 进入本流水线。固定 20 股评测可以直接复用 `ResearchOrchestrator`，不依赖 FastAPI 登录态。
