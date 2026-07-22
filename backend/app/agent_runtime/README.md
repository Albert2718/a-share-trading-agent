# Web Agent 工具适配层

本目录不是第二个 Agent 大脑，只负责把登录用户、Repository 和工具执行策略绑定到 `src/agents/chat/LangGraphChatAgent`。

工具分为读取、需要确认的写入和后台任务三类。LLM 只能提出工具调用；持仓和长期记忆必须先生成 `tool_actions` 记录，再由用户确认。研究任务与文档索引通过 Transactional Outbox 投递给 Celery。

唯一的 `StateGraph`、Agent 节点、Tools 节点和循环上限都位于根目录 `src/agents/chat`；网页是唯一自然语言入口，命令行聊天端已经移除。
