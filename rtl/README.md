# 数字校准硬件实现

`gu_baseline/` 对应阶段三，`new_algorithm/` 对应阶段四。Gu 目录现有候选 flash 入口、抽取前门控乘积、冻结系数两级定点校正链及逐转换 Q22 在线更新。功能分别见[入口仿真](../docs/stages/03_gu_baseline/CANDIDATE_A_RTL_SIMULATION_V1.md)、[单级 PWL](../docs/reports/experiments/EXP_030_FIXED_PWL_RTL_V1.md)、[两级最终码](../docs/reports/experiments/EXP_031_TWO_STAGE_RTL_V1.md)与[在线系数轨迹](../docs/reports/experiments/EXP_032_ONLINE_LMS_RTL_V1.md)。[EXP-034](../docs/reports/experiments/EXP_034_GENERIC_SYNTHESIS_V1.md)又提供通用逻辑网表及有限最终码回放；没有工艺面积、功耗或最大频率结果，也未实现真实四路抽取。新算法目录仍只有任务说明。

每次比较应固定或明确报告：输入／输出码制、系数与累加器位宽、更新抽取率、目标吞吐率、时钟约束、工艺库或 FPGA 器件、综合工具与版本。先验证 RTL 与定点参考模型的逐样本一致性，再综合、检查关键路径和切换功耗。功能仿真本身只能证明逻辑行为，不能证明硬件资源更省。

面向电路教师的 Vivado 2026.1 展示工程见 [集成与复现入口](gu_baseline/vivado_review/REPRODUCE.md)及[实际验收报告](../docs/reports/CIRCUIT_REVIEW_VIVADO_RESULTS_2026-10-11.md)：原 RTL 保持，数字有限功能及综合网表回放通过；Artix-7 映射为2548 LUT/184 FF/4 DSP，100 MHz 综合估计时序未满足。生成物位于本地忽略目录，不能称为 ASIC 或 ADC 晶体管电路。

阶段三建立 Gu 基线；阶段四在同一条件下添加并比较新算法。公开论文没有给出的位级细节必须标为我们的实现假设。

2026-10-16按用户确认增加[多拍核心](gu_baseline/two_stage_multicycle_candidate_a.sv)，2026-10-17继续以串行整数除法缩短组合路径：保持原逐转换结果，E39同时提交，最短接收间隔40周期。独立FPGA评估顶层采用MMCM维持100 MHz、吞吐2.5 MS/s；RTL、同布线DCP功能网表与布局布线时序已通过，完整SDF仍未通过，当前核查延迟仿真上下文中的差异。功能、布局布线、SDF及全部失败记录见[整改报告](../docs/reports/RTL_MULTICYCLE_TIMING_2026-10-16.md)，命令见[复现入口](gu_baseline/vivado_review/REPRODUCE.md#2026-10-16多拍整改)。原Artix-7缺库未复验。

按论文功能边界的独立[分段核心](gu_baseline/two_stage_staged_candidate_a.sv)及[分段PWL](gu_baseline/fixed_pwl_staged_candidate_a.sv)保持原候选数字递推，采用旧系数快照和分段寄存器；实现范围、冻结复现及全部成功／失败仍由上述整改报告与STATUS统一维护。

分段v3当前已在两套XSim中把第221行失配定位到E17前分子／符号通路；2019.1同一失败、CVC脉冲兼容性限制及准确停止点见[整改报告第9节](../docs/reports/RTL_MULTICYCLE_TIMING_2026-10-16.md#9-第221行分子定位软件补充与跨版本核对2026-10-17)。本轮未改RTL或重做物理实现，完整SDF仍未验收。
