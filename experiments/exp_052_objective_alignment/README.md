# EXP-052：正常轨迹的更新方向与最终码目标

固定[协议](protocol.json)后，复用EXP-051的24格正常单位初值记录及四点baseline候选路径。每窗口固定更新前后级和其他前级系数，用实际前级raw码确定数字PWL基函数。目标码只用于离线诊断；在线候选学习器不读取它。四点固定相位和120条窗口提交是明示研究设定，不称Gu芯片原文调度。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_052_objective_alignment.run artifacts/runs/EXP_052/alignment_v1
```

分析连续系数下的精确二次目标变化，并在同一120条数字观测上用实际Q1.10导出、Q3舍入及最终整数码核对。它只刻画局部冻结窗口，不代表状态更新后重新运行整个闭环。结果见`docs/reports/experiments/EXP_052_OBJECTIVE_ALIGNMENT_V1.md`。
