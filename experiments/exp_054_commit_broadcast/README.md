# EXP-054：共享系数的合并、提交和广播

固定四条相位0学习样本和原步长，复用EXP-050的24格物理记录，比较窗口合并、每路舍入、逐条立即生效和延迟一窗口广播。没有新增模拟转换。原Gu窗口核心和RTL保持；新增候选只接收数字样本。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_054_commit_broadcast.run artifacts/runs/EXP_054/timing_v1_r2
python -m experiments.exp_054_commit_broadcast.verify artifacts/runs/EXP_054/timing_v1_r2
python -m experiments.exp_054_commit_broadcast.compare artifacts/runs/EXP_054/timing_v1_r2
```

运行目录必须不存在。初次`timing_v1`保留离线诊断接口列表／元组断言失败；正式`r2`修复类型转换，协议与数值合同未改。

[固定协议](protocol.json)、[解析条件](../../docs/theory/SHARED_BANK_COMMIT_AND_BROADCAST_CONDITIONS_V1.md)及[结果报告](../../docs/reports/experiments/EXP_054_COMMIT_BROADCAST_V1.md)。这些是已见记录的时序敏感性检查，不能作为新算法独立留出验收。
