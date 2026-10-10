# EXP-047：好、差前级解的门控样本与目标抵消

固定EXP-046已指定的周期复位候选4／5及同一后级，不重新按性能挑选根。先只用数字码、dither和既有系数分析门控；随后在独立离线入口读取目标码，计算信号／误差分解与最小二乘参考。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_047_front_gate_sources.run artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_046/curves_v1 artifacts/runs/EXP_047/sources_v2
$env:MPLCONFIGDIR='D:\ADC\artifacts\tooling\matplotlib_config'
python -m experiments.exp_047_front_gate_sources.plot_results artifacts/runs/EXP_047/sources_v2
python -m experiments.exp_047_front_gate_sources.finalize artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_047/sources_v2
```

正式产物为`sources_v2`；`sources_v1`是增加共同raw支撑诊断之前的初算。主入口拒绝覆盖已有目录，复跑应换新的EXP_047子目录。图须实际查看，不能只凭生成成功验收。

拟合11520条、原训练后缀3840条、原正弦3840条；没有提交更新、新训练、模拟数据、Cadence或核心／RTL修改。最小二乘只在拟合部分使用理想目标码，是离线参考，不是可运行的新算法。原正弦继续冻结评分，浮点FFT未数值认证。

见[推导](../../docs/theory/FRONT_GATE_SOURCES_AND_TARGET_BIAS_V1.md)、[报告](../../docs/reports/experiments/EXP_047_FRONT_GATE_SOURCES_V1.md)及[现状说明](../../docs/reports/RESEARCH_STATUS_PLAIN_2026-10-09.md)。
