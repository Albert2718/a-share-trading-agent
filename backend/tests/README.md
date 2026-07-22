# 后端测试

这里存放 FastAPI、服务层、Repository、Celery、SQLite 和 Qdrant 集成测试。单元测试应替换外部 LLM、Embedding、向量库与行情源；集成测试使用独立测试数据目录，不能读取真实 `.env` 中的 Key。

当前测试使用临时 SQLite 文件，覆盖认证、用户隔离、LangGraph 多轮工具、持仓幂等确认、Transactional Outbox 以及 Research/Knowledge 消费者幂等性。运行方式：

```powershell
$env:PYTHONPATH = "$PWD;$PWD\backend"
conda run -n trading-agent python -m pytest backend/tests -q
```
