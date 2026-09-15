# EXP-009：自适应门限 gated-LMS 与高段可辨识性

本实验先验证 Gu 等式 (5)-(7) 的浮点系数提取原语，再讨论两级联合更新。
第一系数使用全部样本；第 `i>1` 个系数只在校正后输出幅值超过由前序系数
形成的动态下门限时更新。实验不使用上门限，因为论文指出这会在一对 dither
输出跨越门限时反转样本次序。

对当前两组合成 PWL truth 分别使用两类输入：

- `nominal_residue`：校准 dither 扣除后的 residue 半幅为 `0.5`；
- `expanded_residue`：合成半幅为 `0.85`，只用于提供高段持续激励。

普通 1-bit 校准 dither 的放大器输出等效幅度固定为 `+/-0.125`。本实验不把
论文讨论的 `+/-0.25/+/-0.75` 2-bit large-signal linearization dither 混入，
也不声称 `expanded_residue` 是硅上 mismatch 或 timing-skew 的统计分布。

为在有限运行时间内把可辨识性和随机梯度方差分开，本实验的每个随机基值
连续施加一对顺序随机的 `+d/-d` 样本。它是方程级 antithetic probe，不是
论文四路硬件 PRNG/decimate-by-30 调度的复刻；真实随机调度留给两级集成实验。

运行：

```powershell
$env:PYTHONPATH='src'
python experiments/exp_009_adaptive_gated_lms/run.py --run-id <unique-run-id>
```
