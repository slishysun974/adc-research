# EXP-033：定点在线状态范围的长记录核对

用 EXP-032 的 Q22 数字候选，每次给出两个末级中心码选择，检查逐转换状态范围在 512 点相干合成记录上的最终码与频谱界限。两种全程固定选择仅用于验证包含关系，不能代表全部可能历史的性能极值。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_033_fixed_online_box.run artifacts/runs/EXP_033/fixed_box_sine_v1/summary.json
```

结果和适用条件见 [EXP-033 报告](../../docs/reports/experiments/EXP_033_FIXED_ONLINE_BOX_V1.md)。
