# 应用层

`app` 是 FastAPI 应用的组合根。它把 API 路由、认证、数据库模型、业务服务、Agent 适配器与后台任务连接起来。

唯一 LangGraph 工作流位于项目根目录的 `src/agents/chat/`；`agent_runtime/` 只保留登录态工具定义、执行策略和 FastAPI 上下文适配，不再维护第二套图。持仓与长期记忆写入只会生成持久化确认动作；研究任务通过 Outbox 进入 Celery。

这里不放行情抓取或研究规则本身：这些能力由项目根目录的 `src/` 继续提供，并通过 `services/` 中的适配层被调用。
