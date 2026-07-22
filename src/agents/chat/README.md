# 唯一 LangGraph 对话 Agent

本目录拥有项目唯一的顶层对话 Agent。`workflow.py` 构建 `StateGraph`，`nodes.py` 实现 LLM 与工具节点，`state.py` 定义图状态，`prompts.py` 组装包含用户结构化 Memory 的系统提示词。

网页端由 `backend/app/services/chat_service.py` 加载会话和登录态工具，再直接实例化 `LangGraphChatAgent`。`ResearchOrchestrator` 通过后台研究工具被调用，是复合研究能力而不是第二个顶层对话 Agent；命令行聊天入口不再保留。
