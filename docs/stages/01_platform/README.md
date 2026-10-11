# 阶段一：实验平台

目标是提供可检查的逐级 ADC 信号链和不泄漏模拟真值的算法测试场。现有静态行为级候选已经验收；它不等同于 Gu 芯片逐位复刻。

- 实现：`src/adc_research/platform/`；仅在 `src/adc_research/evaluation/` 中把完整轨迹压缩成数字观测，供 `calibration/` 在线更新；统一指标在 `metrics/`。
- 规格：`docs/specifications/`；已有证据：`docs/reports/STAGE1_PLATFORM_ACCEPTANCE_V1.md`。
- [Simulink 可视化入口](../../../simulink_adc/README.md)：独立浮点行为 `.slx`、逐级信号与校准反馈。23组、82343次转换与原 Python 的记录信号逐样本数值相等；见 [验收](../../../simulink_adc/VALIDATION.md)。不含定点／RTL或新的物理证据。
- [校准前后性能演示](../../../simulink_adc/PERFORMANCE_DEMO.md#减小非线性及学习率后的结果)：最新静态 full120 百万次转换、频谱／系数／信号图及完整 Python 核对；终点 SNDR 45.2334→61.4768 dB，数字记录全相等、模拟差在容差内。注明与论文测量条件的差异，不升级芯片复现结论。
- 运行入口：`experiments/`；合成模拟 PWL：`configs/nonidealities/gu_gate_d_static_v0_1.yaml`。另有 `StaticCubicTruthConfig` 生成连续、严格单调的三次模拟测试曲线，用于 [EXP-021](../../reports/experiments/EXP_021_GU_CROSS_CURVE_COLD_START_V1.md)。两者均非芯片测得真值。

后续为模拟响应加入有来源的主辅路径、噪声及动态数据，并扩大平滑曲线形状与参数覆盖。训练条件和最终留出条件分开；评分代码可见真值，在线校准代码不可见真值。
