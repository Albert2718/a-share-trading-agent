# AGENTS.md

本文件是本项目给 Codex、Claude Code 等编码 Agent 的项目级操作规则。所有后续涉及源码、文档、JSON、配置文件的读写都必须遵守。

## UTF-8 与中文文件处理最高优先级规则

本节优先级极高，适用于所有涉及中文文件、脚本和文档的读写操作，并与事故复盘规则同级执行。

- 所有文件读写默认使用 UTF-8 编码，修改文件时不得改变原有编码、换行风格和无关内容。
- 读取含中文文件时优先使用 PowerShell 7，并显式指定 UTF-8：

```powershell
Get-Content -Raw -Encoding UTF8 -Path <path>
```

- 禁止用 PowerShell 的 here-string 管道、重定向、`Set-Content`、`Out-File` 写入含中文源码、JSON 或文档。
- 禁止用 `sed`、`awk` 处理含中文文件；需要批量处理时改用 Python 或 Node.js。
- 使用 Python 或 Node.js 脚本处理中文文件时，必须显式以 UTF-8 读写，例如 `encoding="utf-8"`。
- 不要为了修编码而整文件重写、全文件格式化或全文件字符串替换。
- 修改中文 prompt、Markdown 文档、JSON 报告模板时，优先使用 `apply_patch` 做最小变更。
- 若必须重建含中文文件，先确认文件当前内容、编码和 git diff，再执行写入，并在写入后立即用 UTF-8 方式读取验证。

## PowerShell 使用规则

- 优先使用 PowerShell 7 (`pwsh`) 作为默认终端，因为其默认 UTF-8 行为更适合中文项目。
- 如果当前 shell 是 Windows PowerShell 5.1，执行任何中文文件读写前必须显式设置 UTF-8 编码。
- 不要依赖系统默认 GBK/ANSI 编码。
- 不要把命令输出中的乱码内容复制回源码或文档。

## 项目编码风险点

- `src/tools/deep_research/prompts.py` 和 `src/graph/prompts.py` 包含中文 Prompt，必须保持 UTF-8。
- `docs/*.md` 包含中文架构文档，必须保持 UTF-8。
- `outputs/reports/*.md` 和 `outputs/reports/*.json` 是中文报告输出，必须以 UTF-8 生成。
- `.env` 可能包含 API Key，不得打印完整内容，不得提交到仓库。

## 验证要求

每次修改中文文件后，至少执行一次 UTF-8 读取验证：

```powershell
Get-Content -Raw -Encoding UTF8 -Path <changed-file>
```

如果修改了 Python 文件，还需要执行导入或语法验证。为避免旧 `__pycache__` 权限问题，可以临时禁用 pyc 写入：

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -c "import src.chat_agent; import src.tools.deep_research"
```
