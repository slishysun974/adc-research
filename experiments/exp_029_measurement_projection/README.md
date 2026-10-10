# EXP-029：单路测量输出与全速频谱的信息差

在仓库根目录运行：

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_029_measurement_projection.run
```

脚本使用固定系数、12 位整数码和**明示为示例**的“每路每 30 点取一点，再选择第 0 路”投影。它构造一对单路输出完全相同、全速频谱不同的记录。论文没有公开 30:1 抽取器的内部函数，因此脚本不复现芯片测量链。证明、数值和适用边界见[测量路径的信息边界](../../docs/theory/MEASUREMENT_PATH_INFORMATION_BOUNDARY_V1.md)。
