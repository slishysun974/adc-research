# 实验报告与结果索引

当前任务看 [STATUS](../../STATUS.md)，近期解释与主线意义看 [综合分析](../RESEARCH_SYNTHESIS_2026-10-10.md)。本页定位已有成果，实验如何组织见 [实验说明](../../../experiments/README.md)，推导见 [理论索引](../../theory/README.md)。索引收录不表示所有成果已通过芯片或一般理论验收。

先读EXP-055—057的条件和结果，再按当前任务追溯EXP-026、030—035、039—054。EXP-052—054的局部不利次数以EXP-055之后的解释修订为准；早期报告的“下一项”只代表当时安排。

## 编号成果

定义列链接实验README；证据列链接报告或已有理论证明。运行列只是本地目录定位，其中可能同时存在正式、预检和失败子目录；采用哪个运行须以报告和协议为准。数据缺失时不得声称复算。

| 编号 | 主题 | 实验定义 | 报告／推导 | 本地运行 |
|---|---|---|---|---|
| EXP-001／002 | 阶段一Gate A／B控制 | 历史组合记录 | [报告](EXP_001_002_GATE_AB_HYPOTHESIS_A_V0_1.md) | 本报告内记录 |
| EXP-003 | 三级理想链 Gate C | [README](../../../experiments/exp_003_gate_c/README.md) | [报告](EXP_003_GATE_C_HYPOTHESIS_A_V0_1.md) | [目录](../../../artifacts/runs/EXP_003) |
| EXP-004 | Q-007 双路径增益与 offset 联合余量 | [README](../../../experiments/exp_004_q007_dual_path/README.md) | [报告](EXP_004_Q007_DUAL_PATH_MARGIN_V1.md) | [目录](../../../artifacts/runs/EXP_004) |
| EXP-005 | Q-008 PWL 幅值码、连续性与端点 | [README](../../../experiments/exp_005_q008_pwl/README.md) | [报告](EXP_005_Q008_PWL_CODE_CONTINUITY_V1.md) | [目录](../../../artifacts/runs/EXP_005) |
| EXP-006 | 两级已知 PWL truth 与 oracle 校正级联 | [README](../../../experiments/exp_006_two_stage_pwl_truth/README.md) | [报告](EXP_006_TWO_STAGE_PWL_TRUTH_V1.md) | [目录](../../../artifacts/runs/EXP_006) |
| EXP-007 | 静态非理想独立开关与 Gate D | [README](../../../experiments/exp_007_gate_d_static_nonidealities/README.md) | [报告](EXP_007_GATE_D_STATIC_NONIDEALITIES_V1.md) | [目录](../../../artifacts/runs/EXP_007) |
| EXP-008 | 第 4 个 PWL slice 可达性与内部码缩放 | [README](../../../experiments/exp_008_pwl_slice4_reachability/README.md) | [报告](EXP_008_PWL_SLICE4_REACHABILITY_V1.md) | [目录](../../../artifacts/runs/EXP_008) |
| EXP-009 | 自适应门限 gated-LMS 与高段可辨识性 | [README](../../../experiments/exp_009_adaptive_gated_lms/README.md) | [报告](EXP_009_ADAPTIVE_GATED_LMS_IDENTIFIABILITY_V1.md) | [目录](../../../artifacts/runs/EXP_009) |
| EXP-010 | 两级浮点自适应 PWL 集成 | [README](../../../experiments/exp_010_two_stage_adaptive/README.md) | [报告](EXP_010_TWO_STAGE_ADAPTIVE_PWL_V1.md) | [目录](../../../artifacts/runs/EXP_010) |
| EXP-011 | 随机更新调度与稳态方差 | [README](../../../experiments/exp_011_random_update_schedules/README.md) | [报告](EXP_011_RANDOM_UPDATE_SCHEDULES_V1.md) | [目录](../../../artifacts/runs/EXP_011) |
| EXP-012 | 定点 PWL 校正数据通路 | [README](../../../experiments/exp_012_fixed_point_pwl/README.md) | [报告](EXP_012_FIXED_POINT_PWL_V1.md) | [目录](../../../artifacts/runs/EXP_012) |
| EXP-013 | Fixed-point LMS update accumulator | [README](../../../experiments/exp_013_fixed_lms_accumulator/README.md) | [报告](EXP_013_FIXED_LMS_ACCUMULATOR_V1.md) | [目录](../../../artifacts/runs/EXP_013) |
| EXP-014 | Gate E static and spectral metrics | [README](../../../experiments/exp_014_gate_e_metrics/README.md) | [报告](EXP_014_GATE_E_METRICS_V1.md) | [目录](../../../artifacts/runs/EXP_014) |
| EXP-015 | 阶段二独立静态传输预测 | [README](../../../experiments/exp_015_stage2_static_transfer/README.md) | [报告](EXP_015_STAGE2_STATIC_TRANSFER_V0_1.md) | [目录](../../../artifacts/runs/EXP_015) |
| EXP-016 | 阶段二独立静态单音频谱预测 | [README](../../../experiments/exp_016_stage2_static_spectrum/README.md) | [报告](EXP_016_STAGE2_STATIC_SPECTRUM_V0_1.md) | [目录](../../../artifacts/runs/EXP_016) |
| EXP-017 | 阶段二一阶有限建立基线 | [README](../../../experiments/exp_017_stage2_finite_settling/README.md) | [报告](EXP_017_STAGE2_FINITE_SETTLING_V0_1.md) | [目录](../../../artifacts/runs/EXP_017) |
| EXP-018 | 静态码谱的边界灵敏度，第一验证门 | [README](../../../experiments/exp_018_stage2_boundary_sensitivity/README.md) | [报告](EXP_018_STAGE2_BOUNDARY_SENSITIVITY_PHASE1_V0_1.md) | [目录](../../../artifacts/runs/EXP_018) |
| EXP-019 | 第一级独立辅路的判决与周期建立 | [README](../../../experiments/exp_019_dual_path_settling/README.md) | [报告](EXP_019_DUAL_PATH_SETTLING_V0_1.md) | [目录](../../../artifacts/runs/EXP_019) |
| EXP-020 | 有限数字观测下的增益不可辨识反例 | [README](../../../experiments/exp_020_unknown_gain_identifiability/README.md) | [报告](EXP_020_UNKNOWN_GAIN_IDENTIFIABILITY_V1.md) | [目录](../../../artifacts/runs/EXP_020) |
| EXP-021 | Gu 候选算法在未见过的模拟曲线上的冷启动 | [README](../../../experiments/exp_021_gu_cross_curve_cold_start/README.md) | [报告](EXP_021_GU_CROSS_CURVE_COLD_START_V1.md) | [目录](../../../artifacts/runs/EXP_021) |
| EXP-022 | 第一段去相关目标与码误差目标 | [README](../../../experiments/exp_022_k1_objective_audit/README.md) | [报告](EXP_022_K1_OBJECTIVE_AUDIT_V1.md) | [目录](../../../artifacts/runs/EXP_022) |
| EXP-023 | 统一全链路整数码比较 | [README](../../../experiments/exp_023_full_chain_protocol/README.md) | [报告](EXP_023_FULL_CHAIN_PROTOCOL_V1.md) | [目录](../../../artifacts/runs/EXP_023) |
| EXP-024 | 独立辅路对 Gu 全链路结果的影响 | [README](../../../experiments/exp_024_independent_auxiliary/README.md) | [报告](EXP_024_INDEPENDENT_AUXILIARY_V1.md) | [目录](../../../artifacts/runs/EXP_024) |
| EXP-025 | 独立辅路下的更新时序与随机种子 | [README](../../../experiments/exp_025_auxiliary_update_schedules/README.md) | [报告](EXP_025_AUXILIARY_UPDATE_SCHEDULES_V1.md) | [目录](../../../artifacts/runs/EXP_025) |
| EXP-026 | 独立辅路全链路定点对照 | [README](../../../experiments/exp_026_fixed_point_full_chain/README.md) | [报告](EXP_026_FIXED_POINT_FULL_CHAIN_V1.md) | [目录](../../../artifacts/runs/EXP_026) |
| EXP-027 | Gu 逐转换更新的有限长续跑 | [README](../../../experiments/exp_027_gu_long_horizon/README.md) | [报告](EXP_027_GU_LONG_HORIZON_V1.md) | [目录](../../../artifacts/runs/EXP_027) |
| EXP-028 | 抽取边界的信息与门限等值审计 | [README](../../../experiments/exp_028_decimation_information/README.md) | [报告](EXP_028_DECIMATION_INFORMATION_V1.md) | [目录](../../../artifacts/runs/EXP_028) |
| EXP-029 | 单路测量输出与全速频谱的信息差 | [README](../../../experiments/exp_029_measurement_projection/README.md) | [测量信息证明](../../theory/MEASUREMENT_PATH_INFORMATION_BOUNDARY_V1.md) | 无独立目录；见证据 |
| EXP-030 | 候选 Gu 定点 PWL 的逐码 RTL 核对 | [README](../../../experiments/exp_030_fixed_pwl_rtl/README.md) | [报告](EXP_030_FIXED_PWL_RTL_V1.md) | [目录](../../../artifacts/runs/EXP_030) |
| EXP-031 | 两级冻结系数 Gu 候选 RTL 对照 | [README](../../../experiments/exp_031_two_stage_rtl/README.md) | [报告](EXP_031_TWO_STAGE_RTL_V1.md) | [目录](../../../artifacts/runs/EXP_031) |
| EXP-032 | 逐转换在线 Gu 候选 RTL | [README](../../../experiments/exp_032_online_lms_rtl/README.md) | [报告](EXP_032_ONLINE_LMS_RTL_V1.md) | [目录](../../../artifacts/runs/EXP_032) |
| EXP-033 | 定点在线状态范围的长记录核对 | [README](../../../experiments/exp_033_fixed_online_box/README.md) | [报告](EXP_033_FIXED_ONLINE_BOX_V1.md) | [目录](../../../artifacts/runs/EXP_033) |
| EXP-034 | Gu 候选的通用逻辑综合基准 | [README](../../../experiments/exp_034_generic_synthesis/README.md) | [报告](EXP_034_GENERIC_SYNTHESIS_V1.md) | [目录](../../../artifacts/runs/EXP_034) |
| EXP-035 | Q22 更新的等价整数 RTL | [README](../../../experiments/exp_035_exact_update_rtl/README.md) | [报告](EXP_035_EXACT_UPDATE_RTL_V1.md) | [目录](../../../artifacts/runs/EXP_035) |
| EXP-036 | 三路静态扫描数据的接入验证 | [README](../../../experiments/exp_036_physical_scan_intake/README.md) | [报告](EXP_036_PHYSICAL_SCAN_INTAKE_V1.md) | [目录](../../../artifacts/runs/EXP_036) |
| EXP-037 | 有理数静态链与 Q22 在线码范围 | [README](../../../experiments/exp_037_rational_static_online/README.md) | [报告](EXP_037_RATIONAL_STATIC_ONLINE_V1.md) | [目录](../../../artifacts/runs/EXP_037) |
| EXP-038 | 最终整数码范围的有理数频谱认证 | [README](../../../experiments/exp_038_certified_spectrum/README.md) | [报告](EXP_038_CERTIFIED_SPECTRUM_V1.md) | [目录](../../../artifacts/runs/EXP_038) |
| EXP-039 | 四路窗口更新与两相主辅动态闭环 | [README](../../../experiments/exp_039_four_lane_dynamic_loop/README.md) | [报告](EXP_039_FOUR_LANE_DYNAMIC_LOOP_V1.md) | [目录](../../../artifacts/runs/EXP_039) |
| EXP-040 | 窗口均值、门控余量与相位条件 | [README](../../../experiments/exp_040_window_mean_conditions/README.md) | [报告](EXP_040_WINDOW_MEAN_CONDITIONS_V1.md) | [目录](../../../artifacts/runs/EXP_040) |
| EXP-041 | 数字激励与受约束稳定性 | [README](../../../experiments/exp_041_excitation_stability/README.md) | [报告](EXP_041_EXCITATION_STABILITY_V1.md) | [目录](../../../artifacts/runs/EXP_041) |
| EXP-042 | 受约束相关零点与门控跳变 | [README](../../../experiments/exp_042_correlation_roots/README.md) | [报告](EXP_042_CORRELATION_ROOTS_V1.md) | [目录](../../../artifacts/runs/EXP_042) |
| EXP-043 | 整数平均更新、停更与门控选择 | [README](../../../experiments/exp_043_quantized_mean_dynamics/README.md) | [报告](EXP_043_QUANTIZED_MEAN_DYNAMICS_V1.md) | [目录](../../../artifacts/runs/EXP_043) |
| EXP-044 | 原窗口次序、高段请求与状态范围 | [README](../../../experiments/exp_044_ordered_window_propagation/README.md) | [报告](EXP_044_ORDERED_WINDOW_PROPAGATION_V1.md) | [目录](../../../artifacts/runs/EXP_044) |
| EXP-045 | 第三系数释放后的局部相关目标 | [README](../../../experiments/exp_045_released_third_roots/README.md) | [报告](EXP_045_RELEASED_THIRD_ROOTS_V1.md) | [目录](../../../artifacts/runs/EXP_045) |
| EXP-046 | 两级共同零点和量化后的请求 | [README](../../../experiments/exp_046_coupled_root_curves/README.md) | [报告](EXP_046_COUPLED_ROOT_CURVES_V1.md) | [目录](../../../artifacts/runs/EXP_046) |
| EXP-047 | 好、差前级解的门控样本与目标抵消 | [README](../../../experiments/exp_047_front_gate_sources/README.md) | [报告](EXP_047_FRONT_GATE_SOURCES_V1.md) | [目录](../../../artifacts/runs/EXP_047) |
| EXP-048 | 成对dither、共同门和周期误差 | [README](../../../experiments/exp_048_paired_dither_conditions/README.md) | [报告](EXP_048_PAIRED_DITHER_CONDITIONS_V1.md) | [目录](../../../artifacts/runs/EXP_048) |
| EXP-049 | 单位初值实际闭环与预先固定留出 | [README](../../../experiments/exp_049_normal_start_closed_loop/README.md) | [报告](EXP_049_NORMAL_START_CLOSED_LOOP_V1.md) | [目录](../../../artifacts/runs/EXP_049) |
| EXP-050 | 同四点预算的相位选择 | [README](../../../experiments/exp_050_phase_selection/README.md) | [报告](EXP_050_PHASE_SELECTION_V1.md) | [目录](../../../artifacts/runs/EXP_050) |
| EXP-051 | 四点相关量平滑与小步长对照 | [README](../../../experiments/exp_051_filtered_statistics/README.md) | [报告](EXP_051_FILTERED_STATISTICS_V1.md) | [目录](../../../artifacts/runs/EXP_051) |
| EXP-052 | 正常轨迹的更新方向与最终码目标 | [README](../../../experiments/exp_052_objective_alignment/README.md) | [报告](EXP_052_OBJECTIVE_ALIGNMENT_V1.md) | [目录](../../../artifacts/runs/EXP_052) |
| EXP-053 | 抽取时序候选下的目标方向核对 | [README](../../../experiments/exp_053_schedule_boundary/README.md) | [报告](EXP_053_SCHEDULE_BOUNDARY_V1.md) | [目录](../../../artifacts/runs/EXP_053) |
| EXP-054 | 共享系数的合并、提交和广播 | [README](../../../experiments/exp_054_commit_broadcast/README.md) | [报告](EXP_054_COMMIT_BROADCAST_V1.md) | [目录](../../../artifacts/runs/EXP_054) |
| EXP-055 | 模型与dither统计基础核查 | [README](../../../experiments/exp_055_model_dither_audit/README.md) | [报告](EXP_055_MODEL_DITHER_AUDIT_V1.md) | [目录](../../../artifacts/runs/EXP_055) |
| EXP-056 | 百万量级静态单斜率统计检查 | [README](../../../experiments/exp_056_million_scalar_statistics/README.md) | [报告](EXP_056_MILLION_SCALAR_STATISTICS_V1.md) | [目录](../../../artifacts/runs/EXP_056) |
| EXP-057 | 静态两级及平滑非线性的百万量级检查 | [README](../../../experiments/exp_057_static_two_stage_million/README.md) | [报告](EXP_057_STATIC_TWO_STAGE_MILLION_V1.md) | [目录](../../../artifacts/runs/EXP_057) |

共55个编号实验目录（EXP-003—057），另有EXP-001／002组合报告。EXP-029通过现有理论文档保存证明和数值，不补造一份同义报告。

## 非编号机制工作与历史

[主辅、阈值和四路机制分析](../MAINLINE_PHYSICAL_MECHANISMS_2026-10-09.md)配套 [核算入口](../../../experiments/mainline_physical_mechanisms/README.md)与对应理论。阶段综合分析和审查位于上级报告目录，不强行编号为新实验。

旧实验的模型、留出含义、指标口径及信息边界须从原报告审查；具体成果不因新的四阶段分类而扩大。状态演变保存在 [历史快照](../PROJECT_PROGRESS_HISTORY_2026-10-10.md)。
