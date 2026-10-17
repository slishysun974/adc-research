# 理论资料入口

本页按研究问题定位推导，不维护逐轮进展或独立“下一项”。当前任务与最后实质成果见[STATUS](../STATUS.md)，研究方法见[主线计划](../RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md)。先读[未知增益完整链路框架](UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md)和[结论—证据表](STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md)；详细条件、数学状态、核对与开放事项由原文承担。

## 两条核心主线

| 问题 | 主要推导 | 配套证据与限制 |
|---|---|---|
| 正常误差、平均位置、持续变化及两级反馈 | [静态两级支持与误差投影](STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md) | §7—12条件目标／输出交互，§13—14合法参照与时间分解，§16—24正常未来／学习通道、第一响应、采样／目标矩、状态关联、评价前同字参照及前级驱动／自身响应／实际变化；§24.5—24.21定位块均值迁移／块内变化、平均位置矩、请求累计／自身响应、两低段全槽／选样／门与交叉、加权历史、整体误差及同对象能力界。NG-42—46，[EXP-072—074索引](../reports/experiments/README.md)保存有限干预，旧字效应不当未来因果份额 |
| 信息、表示与在线识别能力 | [数字观测与校正能力](OBSERVATION_CORRECTION_LIMITS_V1.md) | NG-31固定表示范围，NG-38完整历史宽输入反例，NG-39已知正弦约束、NG-43共同相位目标投影；同信息／目标／损失比较，固定映射不直接下界在线策略 |

## 学习目标、收敛与跟踪

- [百万量级标量统计、状态噪声与量化](MILLION_SAMPLE_SCALAR_MEAN_NOISE_AND_QUANTIZATION_V1.md)：原理控制、学习率、有限时间矩、输出与恢复合同；EXP-056／069／070按原预算复用。
- [两级窗口平均更新与门控条件](WINDOW_MEAN_AND_GATE_MARGIN_CONDITIONS_V1.md)：保护邻域、两级有限传播及有序周期条件；条件成立不等于实际长期根已认证。
- [数字激励、受约束更新与输入／历史变化](EXCITATION_AND_CONSTRAINED_STABILITY_V1.md)：有限激励、传播与跟踪条件；EXP-065／066幅度切换证据。
- [整数平均更新、停更与门选择](QUANTIZED_MEAN_DYNAMICS_AND_GATE_SELECTION_V1.md)：整数单元、有限像／相位集合及固定历史分区；NG-36／37与原第四窗预算停止保留。
- [原窗口次序、八状态与高段请求](ORDERED_WINDOW_STATE_AND_HIGH_SLOPE_PROPAGATION_V1.md)：真实窗口次序与有限范围，平均映射不代替原路径。
- [正常初值窗口更新与最终码影响](NORMAL_START_WINDOW_ATTRIBUTION_AND_CODE_EFFECTS_V1.md)：正常路径与局部读出方向，不能由局部反号推全期主因。
- [相关量平滑、步长与系数误差](FILTERED_STATISTICS_STEP_AND_STATE_VARIANCE_V1.md)：统计／状态方差、速度与目标偏差分开；已有候选失败保持。
- [数字基函数与目标码方向](DIGITAL_BASIS_OBJECTIVE_DIRECTION_V1.md)：离线目标交叉与有限记录关系，不向在线泄漏目标。

## 有效激励、门、抽取与实现语义

- [Dither信息与随机更新条件](DITHER_INFORMATION_AND_STOCHASTIC_UPDATE_AUDIT_V1.md)：门选择、相位统计、NG-24—26概率／输出／截止及NG-44低阶输入匹配／带状态权重关系；理想概率不认证实际PRNG。
- [主辅有效阈值、两相状态和四路抽取](DUAL_PATH_EFFECTIVE_THRESHOLDS_AND_PHASES_V1.md)：独立静态分支、失配／比较器支持和观测—状态交叉；支持增加不保证净收益。
- [四路冻结窗口与主辅历史](FOUR_LANE_WINDOW_DYNAMIC_LEARNING_V1.md)：完整三路历史、静态退化、承接、有限动态和条件资源成本；EXP-067／068已完成指定范围。
- [四点相位选择条件](FOUR_POINT_PHASE_SELECTION_CONDITIONS_V1.md)：NG-28错开／轮换候选的条件与失败边界，未升级为优选在线算法。
- [共享系数合并、提交与广播](SHARED_BANK_COMMIT_AND_BROADCAST_CONDITIONS_V1.md)：基础时序候选、舍入与版本差异，不等同芯片实际调度。
- [静态定点数值合同、误差界与学习](STATIC_FIXED_POINT_ERROR_AND_LEARNING_V1.md)：Q3／Q1.10／Q22、保护门、隐藏请求与有效导出；有限字长限制与学习波动分开。
- [单路测量输出与全速频谱的信息边界](MEASUREMENT_PATH_INFORMATION_BOUNDARY_V1.md)：EXP-029证明与测量口径，单路不能自动代表四路全速。

## 相关根与成对研究的条件边界

- [受约束相关零点、跳变与局部稳定](CONSTRAINED_CORRELATION_ROOTS_AND_JUMPS_V1.md)
- [第三系数释放后的零点族](RELEASED_THIRD_ROOT_SEGMENTS_V1.md)
- [两级共同相关零点与整数请求](COUPLED_MEAN_ROOT_CURVES_AND_INTEGER_REQUESTS_V1.md)
- [前级门样本、相关抵消与目标偏差](FRONT_GATE_SOURCES_AND_TARGET_BIAS_V1.md)
- [成对dither、共同门与周期误差](PAIRED_DITHER_CANCELLATION_AND_PERIODIC_ERRORS_V1.md)

这些文档保留已证条件与反例。未到达的坏根、经验零点族、成对／锚点或多幅度准备不自动成为当前优先任务；正常路径的重要性和在线成本须另有证据。

## 从模拟范围到最终码与频谱

- [静态主辅范围的全链路传播](STATIC_MAIN_AUX_OBSERVATION_BOUNDS_V1.md)
- [有限电压网格到连续模拟包络](GRID_TO_ANALOG_ENVELOPE_V1.md)
- [在线系数可达集](ONLINE_COEFFICIENT_REACHABILITY_V1.md)
- [静态模拟范围到在线频谱的短记录连接](STATIC_ANALOG_TO_ONLINE_CODE_BOUNDS_V1.md)
- [定点在线状态的整数区间传播](FIXED_ONLINE_STATE_BOX_BOUNDS_V1.md)
- [有理数静态扫描到定点在线码](RATIONAL_STATIC_TO_FIXED_CODE_BOUNDS_V1.md)
- [有限记录最终码与性能界限](FINITE_RECORD_PERFORMANCE_BOUNDS_V1.md)
- [逐频点SFDR界限](BINWISE_SFDR_BOUNDS_V1.md)
- [最终码范围精度的反向预算](CODE_ENVELOPE_RESOLUTION_BUDGET_V1.md)
- [最终整数码到频谱的数值包含](CERTIFIED_FINITE_RECORD_SPECTRUM_V1.md)

以上结论依赖所声明的观测／状态／物理覆盖、记录及精度。可信码范围、普通FFT、数值认证和芯片性能是不同证据；范围压缩只在必要主线核查真实算不动时补。

## 历史底稿与解释演变

[旧TeX](ADC_PERFORMANCE_PREDICTION_THEORY_FRAMEWORK.tex)、[PDF](../../output/pdf/ADC_PERFORMANCE_PREDICTION_THEORY_FRAMEWORK.pdf)及[旧读者导引](STAGE2_READER_GUIDE_V1.md)是给定传输／动态假设下的条件性底稿。[无校准旧目录](uncalibrated_adc/README.md)与[校准旧目录](calibration/README.md)共同服务现阶段二；保留原路径，旧阶段编号不改变证据范围。

研究解释见[Gu集中评价](../reports/GU_ALGORITHM_EVALUATION_V1.md)与[综合分析](../reports/RESEARCH_SYNTHESIS_2026-10-10.md)，状态／方法演变见[状态历史](../reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md)与[计划历史](../reports/STATIC_FIXED_POINT_PLAN_HISTORY_2026-10-11.md)。独立理论成果按[本地流程](../../CONTRIBUTING.md)登记NG；实验负责预定核对，运行次数不替代证明。
