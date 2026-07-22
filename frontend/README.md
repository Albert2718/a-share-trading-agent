# 网页端

本目录是项目的 React + TypeScript 网页工作台。它只通过 FastAPI API 读取和写入数据，不能直接访问 SQLite、Qdrant、Redis、`.env` 或项目根目录的研究文件。

当前版本以自然语言聊天为主界面，研究、持仓、任务、结构化 Memory 与 RAG 知识库从左侧导航进入独立工作区。聊天请求由后端 LangGraph Runtime 处理，前端流式展示 Agent 执行过程、结构化工具结果和需要用户确认的写操作；聊天输入框随多行内容自动增高，研究报告默认渲染为中文可读视图。

测试命令为 `npm test`，生产类型检查与构建命令为 `npm run build`。
