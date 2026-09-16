# EXP-015：阶段二独立静态传输预测

本实验验证 `theory/static_transfer.py` 能否在不调用逐样本平台构造结果的条件下，
由架构参数直接得到完整输入分段、最终码、DNL/INL 和不可纠正输入宽度。

验证包括理想链、轻度静态非理想、含 PWL 的组合静态非理想，以及 EXP-004
已经发现的冗余边界失效反例。理论边界确定后，再在独立的黄金分割相位均匀网格
上调用平台进行留出比较。

运行：

```powershell
$env:PYTHONPATH = "src"
python experiments/exp_015_stage2_static_transfer/run.py --run-id <run-id>
```

正式问题定义和验收标准见
`docs/specifications/STAGE2_STATIC_PREDICTION_SPEC_V0_1.md`。
