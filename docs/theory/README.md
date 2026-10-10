# 理论资料入口

本页按研究问题索引推导，当前任务只在 [STATUS](../STATUS.md)维护。先读 [未知增益完整框架](UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md)和 [结论—证据表](STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md)，当前方法见 [静态定点计划](../RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md)。

EXP-055—057已修订短记录局部方向的解释，并建立单斜率统计与静态两级关系。各文档的证明只在其条件内成立；门、经验均值、定点和真实在线路径不是同一个对象。成对图／锚点和未到达的坏根保留为边界资料，当前不优先扩展。

理论研究有独立成果：定义、推导、条件性定理、反例、范围关系和开放证明。按 [本地研究流程](../../CONTRIBUTING.md)记录；实验负责核对指定问题，不能用运行次数替代推导。修改结论时同步现有证据表，不新增同义清单。

## 当前统计与静态两级

- [Dither提供什么信息，为什么单次更新不保证误差下降](DITHER_INFORMATION_AND_STOCHASTIC_UPDATE_AUDIT_V1.md)
- [百万量级单斜率控制：平均学习、状态波动与量化偏差](MILLION_SAMPLE_SCALAR_MEAN_NOISE_AND_QUANTIZATION_V1.md)
- [静态两级长记录：学习门、数字表示和最终码误差](STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md)

## 观测、表示与测量信息

- [数字观测能校正多少：一般误差下限与 Gu 改进定位](OBSERVATION_CORRECTION_LIMITS_V1.md)
- [单路测量输出不能确定四路全速频谱](MEASUREMENT_PATH_INFORMATION_BOUNDARY_V1.md)

## 主辅与动态机制

- [主辅判决的有效阈值、两相状态和四路抽取](DUAL_PATH_EFFECTIVE_THRESHOLDS_AND_PHASES_V1.md)
- [四路冻结窗口与主辅历史怎样共同改变 Gu 学习](FOUR_LANE_WINDOW_DYNAMIC_LEARNING_V1.md)

## 窗口、有效观测、数值与状态传播

- [两级窗口平均更新与门控余量条件](WINDOW_MEAN_AND_GATE_MARGIN_CONDITIONS_V1.md)
- [数字激励、受约束更新与输入／历史变化](EXCITATION_AND_CONSTRAINED_STABILITY_V1.md)
- [整数平均更新的停更、周期与门控选择条件](QUANTIZED_MEAN_DYNAMICS_AND_GATE_SELECTION_V1.md)
- [原窗口次序、八状态传播与高段请求](ORDERED_WINDOW_STATE_AND_HIGH_SLOPE_PROPAGATION_V1.md)
- [正常初值窗口更新与最终码影响](NORMAL_START_WINDOW_ATTRIBUTION_AND_CODE_EFFECTS_V1.md)
- [四点相位选择的条件与实现合同](FOUR_POINT_PHASE_SELECTION_CONDITIONS_V1.md)
- [相关量平滑、步长与系数误差的条件关系](FILTERED_STATISTICS_STEP_AND_STATE_VARIANCE_V1.md)
- [数字基函数与目标码方向的有限记录关系](DIGITAL_BASIS_OBJECTIVE_DIRECTION_V1.md)
- [四路共享系数的合并、提交和广播条件](SHARED_BANK_COMMIT_AND_BROADCAST_CONDITIONS_V1.md)

## 平均根、门选择与成对边界

- [受约束相关零点、门控跳变与局部稳定](CONSTRAINED_CORRELATION_ROOTS_AND_JUMPS_V1.md)
- [第三系数释放后的相关零点族](RELEASED_THIRD_ROOT_SEGMENTS_V1.md)
- [两级共同零点、量化请求与局部稳定性](COUPLED_MEAN_ROOT_CURVES_AND_INTEGER_REQUESTS_V1.md)
- [前级门控样本、相关量抵消与校正目标偏差](FRONT_GATE_SOURCES_AND_TARGET_BIAS_V1.md)
- [成对dither的信号抵消、周期误差与所需信息](PAIRED_DITHER_CANCELLATION_AND_PERIODIC_ERRORS_V1.md)

## 覆盖范围与条件性能界限

- [主辅模拟范围到最终码：静态全链路条件传播](STATIC_MAIN_AUX_OBSERVATION_BOUNDS_V1.md)
- [从有限电压扫描到连续模拟输出范围](GRID_TO_ANALOG_ENVELOPE_V1.md)
- [在线系数状态到有限记录性能的条件性传播](ONLINE_COEFFICIENT_REACHABILITY_V1.md)
- [静态模拟范围到在线 Gu 频谱：短记录条件性连接](STATIC_ANALOG_TO_ONLINE_CODE_BOUNDS_V1.md)
- [定点 Gu 在线状态的整数区间传播](FIXED_ONLINE_STATE_BOX_BOUNDS_V1.md)
- [静态扫描到定点在线码范围的精确算术 v1](RATIONAL_STATIC_TO_FIXED_CODE_BOUNDS_V1.md)
- [有限记录的最终码与频谱条件界限](FINITE_RECORD_PERFORMANCE_BOUNDS_V1.md)
- [最终码区间的逐频点 SFDR 界限](BINWISE_SFDR_BOUNDS_V1.md)
- [最终码范围需要多窄：频谱下界的反向预算](CODE_ENVELOPE_RESOLUTION_BUDGET_V1.md)
- [最终整数码到有限记录频谱的数值包含证明](CERTIFIED_FINITE_RECORD_SPECTRUM_V1.md)

## 历史条件性底稿

[旧TeX推导](ADC_PERFORMANCE_PREDICTION_THEORY_FRAMEWORK.tex)及 [PDF](../../output/pdf/ADC_PERFORMANCE_PREDICTION_THEORY_FRAMEWORK.pdf)采用给定模拟传输／动态假设。[旧读者导引](STAGE2_READER_GUIDE_V1.md)保留最小例。它们不是一般未知增益理论的完成证据。

[无校准ADC旧目录](uncalibrated_adc/README.md)与 [校准旧目录](calibration/README.md)共同服务于当前阶段二；保留原路径用于复现，旧阶段编号不等于当前阶段。解释演变见 [综合分析](../reports/RESEARCH_SYNTHESIS_2026-10-10.md)和 [历史记录](../reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md)。
