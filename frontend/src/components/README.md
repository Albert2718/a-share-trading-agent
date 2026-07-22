# 可复用界面

这里存放页面级组件共用的界面；它们只通过 `api/client.ts` 与后端通信。

- `AuthPanel.tsx`：注册和登录。
- `ResearchPanel.tsx`：提交异步研究任务。
- `JobTable.tsx`：展示任务状态和进度。
- `PositionForm.tsx`：录入或更新用户持仓。
- `ChatPanel.tsx`：对话式 Agent、乐观消息、SSE 增量回复、安全 Markdown/GFM 渲染与工具确认卡。
- `ReportModal.tsx`：研究报告详情弹窗。
- `ToolWorkspace.tsx`：由左侧导航进入的深度研究、持仓和任务工作区。
- `MemoryPanel.tsx`：查看、覆盖写入和删除长期记忆。
- `KnowledgePanel.tsx`：分类上传文档、观察 chunk 状态、执行 RAG 并展开来源。
