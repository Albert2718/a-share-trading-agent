# Research 工具目录重构建议

## 结论

你的判断在职责边界上是正确的：`src/agents` 应只保留唯一的 LangGraph Agent 大脑，深度研究应通过一个工具入口供 Agent 调用。不过，不建议把当前 `src/agents/research` 的所有文件直接平铺进 `src/tools`，因为它内部包含多分析器编排、领域模型和报告合成，不只是一个简单函数。

推荐将它拆成“工具适配层 + 独立研究流水线”：

```text
src/
├─ agents/
│  └─ chat/                     # 唯一 Agent：LangGraph 状态、节点、路由与提示词
├─ tools/
│  ├─ market.py                 # 行情工具
│  ├─ news_search.py            # 新闻工具
│  └─ deep_research.py          # 深度研究的薄工具入口，只负责参数校验和调用 pipeline
└─ research/
   ├─ orchestrator.py           # 量化、基本面、新闻、情绪和 CIO 的分析编排
   ├─ schemas.py                # 研究领域输入输出模型
   ├─ prompts.py                # 研究专用提示词
   ├─ utils.py                  # 研究专用安全与转换函数
   └─ analysts/                 # 各专业分析器
```

## 为什么这样划分

1. `src/agents/chat` 才是系统唯一会决定下一步动作的 Agent。它拥有 LangGraph 状态机，并通过工具协议调用外部能力。
2. `src/tools/deep_research.py` 是 Agent 看到的工具边界。它应该保持很薄，只定义稳定的输入输出，不承载复杂业务编排。
3. `src/research` 是可被工具、Celery worker 和 20 股评测共同复用的领域流水线。把它放在 `tools` 下面会把“工具接口”和“研究实现”混在一起。
4. 当前 `src/evaluation/forecasting.py` 直接依赖 `ResearchOrchestrator`、研究 schema 和安全工具；独立的 `src/research` 可以保持这条复用链清晰。
5. Web 端的 `research_submit` 不是直接执行耗时研究，而是创建后台任务。它属于 Agent ToolSpec；Celery 再调用研究流水线。这一异步边界应继续保留。

## 当前真实调用关系

```text
LangGraphChatAgent
  → backend/app/agent_runtime/tools.py::research_submit
  → ResearchService.submit
  → Outbox / Celery
  → execute_research_job
  → src.tools.deep_research::run_deep_research
  → ResearchOrchestrator
  → Quant / Fundamental / News / Sentiment / CIO
```

因此，当前 research 在“产品行为”上已经是一个后台工具，只是核心实现的物理目录仍沿用了多 Agent 课程项目时期的命名。

## 建议迁移步骤

1. [x] 使用现有 Research 工具、分析器降级和评测测试锁定行为。
2. [x] 将 `analysts/`、`orchestrator.py`、`schemas.py`、`prompts.py`、`utils.py` 移至 `src/research/`，仅修改导入路径，不改变逻辑。
3. [x] 将原工具入口迁移为 `src/tools/deep_research.py`，作为对 `src.research` 的薄适配层。
4. [x] 修改 `backend/app/services/research_service.py`、`src/evaluation/forecasting.py` 和测试导入路径。
5. [x] 删除旧 `src/agents/research` 路径，避免新代码继续依赖旧结构。
6. [x] 已完成前端、后端、评测回归和 Docker 导入/健康烟雾测试，异步 Worker 已重启并加载新路径。

## 此轮不建议做的事

- 不把 Celery、Repository 或 FastAPI 路由移动到 `src/tools`；它们分别属于基础设施、持久化和接口层。
- 不把 ResearchOrchestrator 合并进 LangGraph 节点；否则 20 股评测会被迫依赖 Web Agent 上下文。
- 不在移动目录时同时改写研究算法；先做等价搬迁，降低回归定位难度。
