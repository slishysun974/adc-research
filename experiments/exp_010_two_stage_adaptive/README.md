# EXP-010：两级浮点自适应 PWL 集成

本实验把 EXP-009 的 gated-LMS 原语接入完整候选 A pipeline。每个样本严格
按照“第二级 PWL 与 `Dd2` 局部扣除，再形成第一级 raw code；第一级 PWL 与
`Dd1` 局部扣除”的顺序处理，并在下一样本才使用更新后的系数。

本实验采用所有 4096 个输入码中心与四个 dither 符号组合构成一个平衡训练
块，每轮随机打乱。这验证两级更新串接、门控域和系数方向，但不是论文四路
750 MHz PRNG 与 decimate-by-30 的 bit-true 调度。

运行：

```powershell
$env:PYTHONPATH='src'
python experiments/exp_010_two_stage_adaptive/run.py --run-id <unique-run-id>
```

