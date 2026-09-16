# EXP-016：阶段二独立静态单音频谱预测

本实验验证 `theory/static_spectrum.py` 能否只使用 EXP-015 的静态传输分段，
在不调用逐样本平台构造预测结果的条件下，独立得到连续周期傅里叶系数与有限
相干记录的复频谱、SNDR、SNR、THD、SFDR 和 ENOB。

留出验证覆盖三种输入峰值、两个互质相干频点，以及理想、轻度静态非理想和
组合 PWL 静态非理想。平台只在理论结果完成后生成外部标签；共同指标模块只把
两边各自的输出码转换为同一口径的频谱指标。

运行：

```powershell
$env:PYTHONPATH = "src"
python experiments/exp_016_stage2_static_spectrum/run.py --run-id <run-id>
```

正式问题定义和验收标准见
`docs/specifications/STAGE2_STATIC_SPECTRUM_SPEC_V0_1.md`。
