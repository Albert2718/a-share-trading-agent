# 运维脚本

本目录不是 CLI 产品层，只保存需要人工或定时触发的独立运维任务。

- `run_evaluation.py daily`：收盘且行情数据完整后，先结算到期预测，再生成当天固定 20 股预测。
- `run_evaluation.py report`：不生成新预测，只根据现有不可变记录重建累计报告。

所有 Python 命令使用项目指定的 Conda 环境：

```powershell
conda run -n trading-agent python scripts/run_evaluation.py daily
conda run -n trading-agent python scripts/run_evaluation.py report
```
