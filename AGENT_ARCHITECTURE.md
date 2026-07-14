# Agent 架构设计

状态：已确认  
日期：2026-07-14

## 目标

项目只保留一个顶层聊天 Agent。深度研究作为聊天 Agent 可调用的复合工具，对内继续保留量化、基本面、新闻、情绪和 CIO 五个研究角色。

本次重构必须满足以下要求：

- `python run_agent.py chat`、`analyze`、`screen`、`cache` 和 `config` 的用户行为保持不变。
- 删除旧的 `src.graph.*` 和 `src.tools.deep_research.*` 内部导入路径，不提供兼容转发模块。
- `src.core` 不得依赖 `src.tools` 或 `src.agents`。
- 研究角色只负责分析与决策，外部数据、模型和 LLM 调用通过明确接口注入。
- 单个研究角色失败时，其余角色仍能完成分析，CIO 根据可用报告生成保守结论。

## 当前问题

当前聊天 Agent 位于 `src/graph`，研究 Agent 位于 `src/tools/deep_research`，两套 Agent 缺少统一的所有权边界。`src/core/llm.py` 从深度研究工具目录导入 LLM 客户端，而该客户端又从 `src.core` 读取配置，形成 `core -> tools -> core` 的反向依赖。

此外，聊天节点直接访问 OpenAI SDK 客户端内部属性，工具注册表同时维护函数映射和大段 Schema，研究角色内部直接完成 AKShare、Tavily、LLM 和模型调用。这些关系使模块难以独立测试，也使目录名称不能准确表达职责。

## 目标结构

```text
src/
├── agents/
│   ├── chat/
│   │   ├── agent.py
│   │   ├── workflow.py
│   │   ├── nodes.py
│   │   ├── state.py
│   │   ├── prompts.py
│   │   └── tool_catalog.py
│   └── research/
│       ├── tool.py
│       ├── orchestrator.py
│       ├── analysts/
│       │   ├── quant.py
│       │   ├── fundamental.py
│       │   ├── news.py
│       │   ├── sentiment.py
│       │   └── cio.py
│       ├── schemas.py
│       ├── prompts.py
│       └── reporting.py
├── core/
│   ├── llm.py
│   ├── config.py
│   ├── cache.py
│   ├── data_access.py
│   ├── memory.py
│   └── rate_limiter.py
└── tools/
    ├── definitions.py
    ├── registry.py
    ├── market_data.py
    ├── news_search.py
    ├── lstm.py
    ├── market.py
    ├── financial.py
    ├── technical.py
    ├── screening.py
    ├── personal.py
    ├── macro.py
    └── market_scanner.py
```

## 依赖方向

允许的主要依赖方向为：

```text
CLI -> agents.chat -> agents.chat.tool_catalog
                              |          |
                              |          +-> tools.registry + light tools
                              |
                              +-> agents.research.tool
                                          |
                                          v
                                agents.research.orchestrator
                                          |
                                          v
                              research analysts -> tools/core

tools -> core
agents -> tools/core
core -> Python 标准库和第三方 SDK
```

禁止以下依赖：

- `core -> tools`
- `core -> agents`
- 普通业务工具通过 `tools.__init__` 间接加载全部工具
- 研究分析器直接访问 OpenAI SDK 客户端内部属性
- 聊天节点直接调用某个具体行情或研究实现

## 核心接口

### LLMClient

`src/core/llm.py` 完整拥有 OpenAI-compatible 客户端实现，对外提供：

- `chat_with_tools(messages, tools, temperature=0)`：返回统一的聊天响应和工具调用信息。
- `structured(system_prompt, user_payload, schema, temperature=0, max_tokens=900)`：返回结构化字典或 `None`。

调用方不得访问 `.client`、SDK Response 或其他实现细节。配置继续通过 `src.core.config.load_config()` 读取。

### ToolDefinition 与 ToolRegistry

`ToolDefinition` 保存工具名称、说明、参数 Schema 和执行函数。`src/agents/chat/tool_catalog.py` 作为组合根，显式声明并汇总轻工具和深度研究工具；业务工具模块本身不依赖聊天协议。`ToolRegistry` 只负责：

- 输出 OpenAI-compatible 工具 Schema。
- 校验并执行工具参数。
- 将结果转换为可序列化字典。
- 将异常转换为包含工具名称和错误原因的稳定错误结果。

注册表不得主动导入具体工具，不得依赖 `src.tools.__init__` 的批量导出，也不得反向依赖 `src.agents`。

### DeepResearchTool

`src/agents/research/tool.py` 是聊天 Agent 可见的复合工具入口。公开参数保持为 `code`、`depth` 和 `risk_profile`，返回可序列化的研究报告。

CLI 的 `analyze` 和 `screen` 命令使用相同的研究编排器，避免聊天入口与命令行入口产生两套研究逻辑。

### ResearchOrchestrator

研究编排器按候选股票调度 Quant、Fundamental、News 和 Sentiment 分析器，再将四份报告交给 CIO。第一阶段保持顺序执行，以维持现有请求顺序、缓存行为和限流特征。

编排器不直接访问 AKShare、Tavily、OpenAI SDK 或 PyTorch 模型文件。所有外部能力通过构造函数注入分析器。

### 底层工具

- `AkshareMarketData`：封装行情、财务、候选股票、新闻和情绪数据访问。
- `NewsSearchTool`：封装 Tavily 请求、缓存和超时。
- `LSTMPredictor`：封装本地模型加载、特征构造和预测。
- 现有轻量工具函数继续作为聊天 Agent 的可调用能力。

## 执行流程

```text
用户消息
  -> ChatAgent
  -> LangGraph Chat Workflow
  -> LLMClient.chat_with_tools
  -> ToolRegistry
  -> DeepResearchTool
  -> ResearchOrchestrator
  -> Quant / Fundamental / News / Sentiment
  -> CIO
  -> FinalReport
  -> ToolRegistry 序列化
  -> ChatAgent 最终回复
```

直接运行 `analyze` 或 `screen` 时，CLI 从 `DeepResearchTool` 下方的同一编排入口开始，不经过聊天 LLM。

## 错误处理

- LLM 配置缺失属于明确的配置错误，由聊天节点转换为当前中文失败信息。
- 工具执行错误包含工具名称和简化错误原因，不包含 API Key、请求头或完整环境变量。
- Quant、Fundamental、News 或 Sentiment 失败时返回对应的 `status="unavailable"` 报告。
- CIO 在部分报告不可用时继续执行规则判断，并降低评分或置信度。
- 结构化 LLM 调用失败时继续使用现有规则或启发式降级路径。
- AKShare、Tavily 和本地模型继续使用现有缓存、限流和回退数据策略。

## 迁移范围

本次删除：

- `src/graph/`
- `src/tools/deep_research/`
- `src/chat_agent.py`
- `src/core/models.py` 中未使用的 `ChatTurn`

对应实现迁入 `src/agents`、`src/core` 和职责明确的 `src/tools` 模块。README 的目录结构和相关导入说明同步更新。

本次不引入异步并发、不修改研究评分规则、不修改 Prompt 内容、不改变报告字段、不更换 LangGraph 或 OpenAI SDK。

## 验收标准

- 全项目不存在 `src.graph`、`src.tools.deep_research`、`TradingAgentsLLM` 和旧工具路径引用。
- 导入 `src.core` 不会加载 `src.tools` 或 `src.agents`。
- 聊天节点不访问 LLM SDK 客户端内部属性。
- 深度研究仍执行五个研究角色，并保持现有报告结构。
- LSTM 模型继续从 `lstm_training/lstm_model.pt` 加载。
- `run_agent.py --help`、`config status` 和 `cache status` 正常运行。
- 聊天工作流、工具注册、深度研究降级和 CLI 入口拥有自动化测试。
- Python 编译、关键模块导入、现有测试和新增测试全部通过。
