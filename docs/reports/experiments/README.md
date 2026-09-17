# 实验报告

本目录只保存经过审查的实验设计、结果摘要、结论和限制。原始运行产物及大规模数据保存在 `artifacts/runs/`。

## 当前报告

- `EXP_001_002_GATE_AB_HYPOTHESIS_A_V0_1.md`：候选 A 的 residue 覆盖、联合冗余窗口和 Gate A/B 验收。
- `EXP_003_GATE_C_HYPOTHESIS_A_V0_1.md`：候选 A 的三级理想链、双 dither 数字抵消和 Gate C 验收。
- `EXP_004_Q007_DUAL_PATH_MARGIN_V1.md`：双路径增益/offset 的联合冗余余量、反例和 Q-007 行为级关闭。
- `EXP_005_Q008_PWL_CODE_CONTINUITY_V1.md`：4-slice PWL 的 `b0=128/32`、累计连续性和负满量程端点审计。
- `EXP_006_TWO_STAGE_PWL_TRUTH_V1.md`：两级静态 PWL truth、oracle 反函数、局部 dither 扣除顺序及量化残差审计。
- `EXP_007_GATE_D_STATIC_NONIDEALITIES_V1.md`：四类静态非理想的独立开关、零值恒等、trace 隔离与组合顺序验证。
- `EXP_008_PWL_SLICE4_REACHABILITY_V1.md`：第 4 个 PWL slice 的解析/穷举可达性，以及一致内部码缩放的不变性审计。
- `EXP_009_ADAPTIVE_GATED_LMS_IDENTIFIABILITY_V1.md`：论文 gated-LMS 的自适应下门限、分段有效更新次数及高段可辨识性审计。
- `EXP_010_TWO_STAGE_ADAPTIVE_PWL_V1.md`：两级局部 LMS 观测、嵌套自适应校正、码域改善和量化后固定点差异。
- `EXP_011_RANDOM_UPDATE_SCHEDULES_V1.md`：两个独立伪随机序列、逐样本/按 30 抽取/分块平均相关更新的收敛与稳态方差比较。
- `EXP_012_FIXED_POINT_PWL_V1.md`：11-bit Q1.10 系数、Q3 校正数据通路、舍入规则、最终整数码和中间位宽审计。
- `EXP_013_FIXED_LMS_ACCUMULATOR_V1.md`：Q1.10 系数接口与 LMS 更新累加器分离、累加器小数位数扫描及更新量化审计。
- `EXP_014_GATE_E_METRICS_V1.md`：均匀斜坡 DNL/INL、相干单音 FFT、理想链验证及 PWL 校正前后趋势核对。
- `EXP_015_STAGE2_STATIC_TRANSFER_V0_1.md`：独立区间传播预测器、码密度、静态非理想留出验证及冗余失效输入测度；非单调条件的累计 DNL 已勘误解释。
- `EXP_016_STAGE2_STATIC_SPECTRUM_V0_1.md`：正弦相位闭式积分、有限相干复频谱、动态指标留出验证及连续/有限记录误差分解。
- `EXP_017_STAGE2_FINITE_SETTLING_V0_1.md`：一阶 residue 状态、精确周期稳态、静态极限及频率/幅度/建立强度留出验证。
- `EXP_018_STAGE2_BOUNDARY_SENSITIVITY_PHASE1_V0_1.md`：单阈值连续谱线边界导数的手算、平台和独立积分差分第一验证门。
- `EXP_019_DUAL_PATH_SETTLING_V0_1.md`：独立辅路静态边界、前馈三状态周期建立、旧约简退化条件及物理证据边界。
