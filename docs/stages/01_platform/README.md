# 阶段一：实验平台

目标是提供可检查的逐级 ADC 信号链和不泄漏模拟真值的算法测试场。现有静态行为级候选已经验收；它不等同于 Gu 芯片逐位复刻。

- 实现：`src/adc_research/platform/`；仅在 `src/adc_research/evaluation/` 中把完整轨迹压缩成数字观测，供 `calibration/` 在线更新；统一指标在 `metrics/`。
- 规格：`docs/specifications/`；已有证据：`docs/reports/STAGE1_PLATFORM_ACCEPTANCE_V1.md`。
- 运行入口：`experiments/`；合成模拟 PWL：`configs/nonidealities/gu_gate_d_static_v0_1.yaml`。另有 `StaticCubicTruthConfig` 生成连续、严格单调的三次模拟测试曲线，用于 [EXP-021](../../reports/experiments/EXP_021_GU_CROSS_CURVE_COLD_START_V1.md)。两者均非芯片测得真值。

后续为模拟响应加入有来源的主辅路径、噪声及动态数据，并扩大平滑曲线形状与参数覆盖。训练条件和最终留出条件分开；评分代码可见真值，在线校准代码不可见真值。
