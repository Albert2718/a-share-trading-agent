# 开发路线

## 已完成的基础能力

- [x] FastAPI、React、SQLite、Redis/Celery、Qdrant 全栈运行链路。
- [x] 注册、登录、JWT 与不同用户的数据隔离。
- [x] Repository 无隐式提交，请求与 Worker 统一事务边界。
- [x] 持仓和 Memory 的持久化确认及数据库级幂等。
- [x] 研究与文档索引通过 Transactional Outbox 可靠投递。
- [x] 网页与旧命令行对话 Agent 合并为 `src/agents/chat` 中唯一的 LangGraph Runtime。
- [x] 将深度研究改为 `src/tools/deep_research.py` 薄工具入口，并把可复用流水线从 Agent 目录迁移到 `src/research/`。
- [x] 删除全部 CLI；每日 20 股评测迁移为独立 `scripts/run_evaluation.py`。
- [x] 删除后端重复 LangGraph 图。
- [x] 删除旧同步 ToolRegistry、本地 JSON 持仓/Memory、CLI 私有配置和未接入产品的重复工具模块。
- [x] 统一研究与评测的敏感信息脱敏实现，并补齐逐文件职责和完整数据流文档。
- [x] 结构化 Memory、文档 chunk、BGE Embedding 与 Qdrant 检索。
- [x] LLM 不可用时的规则降级路径。
- [x] 后端、研究、评测和前端关键自动化测试。

## P3：研究质量

- [x] 产品决定 `quick`、`standard`、`full` 不拆分研究流程；现有字段仅用于兼容历史任务和接口。
- [ ] 构建共享 `ResearchSnapshot`，减少 Analyst 重复请求行情。
- [x] 将筛选后的持仓、Memory 和 RAG 来源真正注入深度研究。
- [ ] 在报告中保存数据截止时间、来源、降级模块和结论失效条件。
- [ ] 为 Qdrant 增加索引版本、相似度阈值、去重和 token 预算。

## P3：聊天与前端体验

- [x] 用户发送消息后立即乐观显示，不等待 Agent 完整回答。
- [x] 增加 SSE 流式回答，并展示规划、工具开始、工具完成、等待确认、后台任务创建和结果整理事件。
- [x] 增加仅用于 Agent 回复的安全 Markdown/GFM 渲染。
- [x] 增加行情、历史走势、持仓、知识来源、Memory 和研究任务结构化卡片；完整报告继续使用独立报告视图。
- [x] 深度研究报告使用中文分区展示结论、证据、风险、失效条件、Analyst 指标和用户上下文，原始 JSON 仅作折叠调试信息。
- [x] 聊天输入框随 Shift + Enter 多行内容自动增高，达到最大高度后才出现滚动。
- [x] 研究任务轮询已与持仓、Memory、文档刷新拆分；退避策略仍待增加。
- [ ] 优化霞鹜文楷字体子集和首屏资源。
- [ ] 完成桌面与移动端的登录态视觉验收。

## P4：可观察性与部署

- [ ] 增加请求 ID、结构化日志、Readiness 和 Agent 工具追踪。
- [ ] 增加 Playwright 端到端测试。
- [ ] 增加生产 Compose、反向代理、HTTPS、限流和密钥托管说明。

## 最近验证基线

- Python 完整回归：`152 passed`（2026-07-22）。
- 前端回归与生产构建：`10 passed`，`vite build` 成功（2026-07-22）。
- Docker API 健康检查：`200 {"status":"ok"}`。
- API 容器实际加载 Agent：`src.agents.chat.workflow`。
- API/Worker 容器实际加载研究工具：`src.tools.deep_research`。
