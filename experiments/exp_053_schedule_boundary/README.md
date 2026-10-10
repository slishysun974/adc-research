# EXP-053：抽取时序候选下的目标方向核对

只读复用EXP-050的24格、四种既有路径。对每个实际窗口使用EXP-052的同一套数字基函数、前级更新方向及最终整数码局部评分，比较结论是否取决于项目选定的相位／统计预算。四种路径都是研究候选，Gu原文未指定它们的具体抽取和提交时序。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_053_schedule_boundary.run artifacts/runs/EXP_053/schedule_boundary_v1
python -m experiments.exp_053_schedule_boundary.verify artifacts/runs/EXP_053/schedule_boundary_v1
```

固定、轮换和伪随机各选4条；完整累加使用全部120条，是不同统计／硬件预算的机制参照。结果见`docs/reports/experiments/EXP_053_SCHEDULE_BOUNDARY_V1.md`。
