# 离线评估，不是运行时校准输入

`fixed_window_state_bounds.py`在原四路完整聚合合同下冻结旧系数范围，先求全窗口相关和范围再一次提交，按实际次序包含全部八状态和最终码。它不同于逐转换`fixed_online_state_bounds.py`，只覆盖给定数字记录／初始状态范围；证明及高段基函数支撑诊断见[EXP-044推导](../../../docs/theory/ORDERED_WINDOW_STATE_AND_HIGH_SLOPE_PROPAGATION_V1.md)。

`observations.py` 从完整 ADC 平台轨迹只提取算法允许读取的数字信号。`oracle.py` 可读取合成模拟 PWL 真值，计算理想反函数系数，供**离线比较**使用。`scoring.py` 在事后读取模拟过载标记。训练脚本还可利用预设测试输入计算误差和写报告。

这些信息不能反向决定正在运行的校准系数、分段宽度、门控阈值或更新步长。测试者知道的模拟曲线不代表芯片内数字逻辑知道它。

`window_trajectory_diagnostics.py`先从实际窗口结果与数字样本重建门、段支撑和选样，再在独立离线入口读取理想整数码，精确分解目标／误差相关和及Q22舍入／裁剪差。它还报告相同旧状态下完整与点抽取的差，不能把误差相关量称为最终码梯度，也不向在线核心提供目标。见[EXP-049](../../../docs/reports/experiments/EXP_049_NORMAL_START_CLOSED_LOOP_V1.md)。

`online_code_reachability.py` 在离线评估中枚举短记录的可能五字段观测及候选 Gu 在线状态。它要求调用方事先证明观测集合覆盖所声明的物理条件；枚举结果不进入运行时校准器，也不证明芯片总线或长期性能。

`digital_extraction_trace.py` 读取外部提供的逐转换**数字**记录，检查转换对齐、四路相位与块内系数冻结，并比较 `≥`/`>` 两种未舍入门控相关和。它不会从最终码反推内部总线或真实抽取规则；输入格式和有限记录结论见[取证协议](../../../docs/stages/03_gu_baseline/DIGITAL_EXTRACTION_TRACE_PROTOCOL_V1.md)。

`physical_scan_package.py` 只读接入三路静态模拟扫描包，检查来源摘要、单位、条件和独立留出，将输入误差按外部斜率界计入网格范围。它使用精确有理数并提供向外转换的浮点适配，区分覆盖、矛盾和不确定；不会认证来源／物理前提，也不改变在线算法。格式及数值边界见[扫描协议](../../../docs/stages/02_end_to_end_theory/STATIC_SCAN_PACKAGE_PROTOCOL_V1.md)。

`rational_path_envelope` 提供不转浮点的归一化扫描范围；`static_online_reachability.py` 的 `propagate_rational_static_fixed_online_codes` 要求模拟输入及架构端点均为有理数，再接整数观测／Q22 状态与最终码。自定义回调内部精确性仍须审查。该范围止于整数码，不能认证 FFT／分贝或物理条件，见[推导与范围](../../../docs/theory/RATIONAL_STATIC_TO_FIXED_CODE_BOUNDS_V1.md)。
