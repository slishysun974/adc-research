# 阶段三：Gu 候选硬件基线

此处逐步建立 Gu 数字校准的 RTL、验证平台与综合约束。现有候选 flash 入口、逐转换门控乘积、单级定点 PWL、冻结系数两级校正链、逐转换在线 Q22 更新及独立多拍版本；已有通用逻辑综合与指定FPGA时序结果，尚无四路抽取/广播 RTL 或目标工艺面积、功耗结果。硬件实际可见的总线、更新时序和论文未公开的字长细节仍须另行核对；候选设定逐项注明。

2026-10-11追加面向电路教师的[Vivado集成入口](vivado_review/REPRODUCE.md)和[实际工程报告](../../docs/reports/CIRCUIT_REVIEW_VIVADO_RESULTS_2026-10-11.md)。当时专用链在Vivado 2026.1／Artix-7建立工程、结构网表及原生图；八状态RTL与有限网表输出回放通过。2548 LUT／184 FF／4 DSP／0 BRAM，100 MHz综合时序未满足；“原候选源码未修改”是该次历史运行的状态。

2026-10-16启动的[多拍核心](two_stage_multicycle_candidate_a.sv)与[整改报告](../../docs/reports/RTL_MULTICYCLE_TIMING_2026-10-16.md)单列：当前串行除法版E39提交、40周期接收间隔，保持原递推；精确bank新增的外部提交／整数请求参数默认关闭，仍兼容原逐转换方式。当前物理验收进度及旧Artix-7未复验边界见报告。

另有按论文功能边界划分的[分段PWL](fixed_pwl_staged_candidate_a.sv)与[分段核心](two_stage_staged_candidate_a.sv)，对应段宽仅256／1024、核心默认16周期时序槽。独立请求token使无效样本仍完成；E0快照旧系数，原Q3／Q10／Q22与E39／40合同保留。测试入口为[双段宽参考控制](vivado_review/tb_staged_pwl.sv)。实际功能、单周期STA、SDF范围和失败见原整改报告第8节及STATUS，不能当作四路芯片位级复刻。

OJSSCS Fig. 14 画出前级 `D[7:0]` 原始比较器输出，而 Fig. 13 仅把 flash 方框标作 `3-bit`。当前软件使用九状态 `q=-4…4`；若 RTL 候选要用三位输入，须先明确第九状态如何处理，不能静默截断。位级接口核查见[来源审计](../../docs/stages/03_gu_baseline/DIGITAL_BUS_AND_DUAL_PATH_SOURCE_AUDIT_V1.md)。

[EXP-026](../../docs/reports/experiments/EXP_026_FIXED_POINT_FULL_CHAIN_V1.md) 已给出相同五字段记录和整数最终码规则下的 Q1.10／Q3 软件定点对照，可作未来 RTL 功能验证的数值基线。其 22/26 位更新累加器、无限宽 Python 中间整数、逐转换更新及舍入规则都是候选设定，RTL 需明确实际位宽、溢出、四路抽取和系数生效时序。

现有[八路 thermometer 到九态符号的候选适配器](flash_thermometer_adapter_a.sv)，其[逐态契约与来源](../../docs/stages/03_gu_baseline/DIGITAL_INTERFACE_CANDIDATE_A_V1.md)已写明。新增[逐转换门控相关乘积模块](gated_product_candidate_a.sv)和[定向测试平台](tb_gated_product_candidate_a.sv)：输入是已经对齐的本级 Q3 学习输出、Q3 dither 数字副本及三个 Q3 下限，输出四段门控 bit 与未舍入 Q6 乘积。`GATE_ON_EQUAL=1` 对应论文式 (7) 的 `≥`，参数为 0 时对应 Fig. 10 的 `>`；第一段始终使用有效转换。16 位有符号输入、17 位阈值和 32 位乘积是**本候选的显式容量**，不是芯片位宽证据。

这个组合模块位于抽取器之前，单独使用时不计算本级 PWL 校正输出，也不规定抽取聚合、乘积缩位、累加器、系数更新或四路广播。后续 EXP-032 已将其接到一个逐转换累加器候选；四路真实时序、综合成本仍未完成。门控测试平台在正负门限等值、最小有符号码及无效样本上检查两种比较语义；[flash 穷举测试平台](tb_flash_thermometer_adapter_a.sv)另核对全部 256 个原始八位字。两个候选模块已在 SoCLab 的 WSL Icarus 10.3 上通过上述功能检查，命令、结果与适用范围见[仿真记录](../../docs/stages/03_gu_baseline/CANDIDATE_A_RTL_SIMULATION_V1.md)。这不证明可综合性、资源成本或芯片逐位一致性。

[单级四段定点 PWL 模块](fixed_pwl_candidate_a.sv)按 Q1.10/Q3、最近偶数舍入及负满量程末段延伸，实现 EXP-012/026 的一个固定数值候选；两级宽度 1024/256 的全部合法原始码和四组系数共 `40992` 条已与软件逐项一致，见[EXP-030](../../docs/reports/experiments/EXP_030_FIXED_PWL_RTL_V1.md)。[冻结系数两级模块](two_stage_fixed_candidate_a.sv)按后级先校正、逐级扣 dither 的顺序输出最终 12 位整数码；`18432` 条数字压力向量通过，见[EXP-031](../../docs/reports/experiments/EXP_031_TWO_STAGE_RTL_V1.md)。这两个实验不包括四路抽取、在线系数更新或芯片时序。

[在线累加器模块](fixed_gated_lms_candidate_a.sv)从同次转换的学习输出与 dither 求四段门控乘积，按两级不同的精确有理数步长更新 23 位 Q22 状态；[两级连接模块](two_stage_adaptive_candidate_a.sv)使用更新前的系数给本次最终码，上升沿同时更新，下一次生效。`8263` 条连续数字记录与 Python 参考逐次一致，见[EXP-032](../../docs/reports/experiments/EXP_032_ONLINE_LMS_RTL_V1.md)。此逐转换时序与数值规则都是研究候选；工艺成本、四路抽取及芯片字对应仍开放。

[EXP-034](../../docs/reports/experiments/EXP_034_GENERIC_SYNTHESIS_V1.md)进一步在只导出最终码与有效标记的相同边界下综合两条链，得到 `4799/200629` 个通用单元；在线链保留 184 位状态。已有 Python 压力记录的最终输出经 Windows 本地网表回放通过；WSL Icarus 另已核对冻结链 RTL／网表各 18432 条及在线 RTL 8391 条。完整在线网表 HDL 仿真与全输入形式等价仍未完成，定向检查的独立范围见报告。关闭 ABC、没有目标工艺／器件及约束的单元数和拓扑深度仅是结构基准。

[专用 Q22 更新模块](fixed_gated_lms_exact_candidate_a.sv)只接受固定 `±512/±128` dither 的极性，按已证明的有效学习输出范围实现精确约分；[专用两级链](two_stage_adaptive_exact_candidate_a.sv)保留原校正器及逐转换时序。原通用 LMS 和两级模块不修改。[EXP-035](../../docs/reports/experiments/EXP_035_EXACT_UPDATE_RTL_V1.md)完成全部 173872 组 RTL 增量、饱和边界及 8263 条连续最终码／八状态核对，同流程通用单元降至 `21121`，状态仍为 184 位。这个接口不能用于任意 dither 幅值或未经重新证明的数据域，结构改善不代表工艺面积／时序／功耗。
