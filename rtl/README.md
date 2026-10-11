# 数字校准硬件实现

`gu_baseline/` 对应阶段三，`new_algorithm/` 对应阶段四。Gu 目录现有候选 flash 入口、抽取前门控乘积、冻结系数两级定点校正链及逐转换 Q22 在线更新。功能分别见[入口仿真](../docs/stages/03_gu_baseline/CANDIDATE_A_RTL_SIMULATION_V1.md)、[单级 PWL](../docs/reports/experiments/EXP_030_FIXED_PWL_RTL_V1.md)、[两级最终码](../docs/reports/experiments/EXP_031_TWO_STAGE_RTL_V1.md)与[在线系数轨迹](../docs/reports/experiments/EXP_032_ONLINE_LMS_RTL_V1.md)。[EXP-034](../docs/reports/experiments/EXP_034_GENERIC_SYNTHESIS_V1.md)又提供通用逻辑网表及有限最终码回放；没有工艺面积、功耗或最大频率结果，也未实现真实四路抽取。新算法目录仍只有任务说明。

每次比较应固定或明确报告：输入／输出码制、系数与累加器位宽、更新抽取率、目标吞吐率、时钟约束、工艺库或 FPGA 器件、综合工具与版本。先验证 RTL 与定点参考模型的逐样本一致性，再综合、检查关键路径和切换功耗。功能仿真本身只能证明逻辑行为，不能证明硬件资源更省。

面向电路教师的 Vivado 2026.1 展示工程见 [集成与复现入口](gu_baseline/vivado_review/REPRODUCE.md)及[实际验收报告](../docs/reports/CIRCUIT_REVIEW_VIVADO_RESULTS_2026-10-11.md)：原 RTL 保持，数字有限功能及综合网表回放通过；Artix-7 映射为2548 LUT/184 FF/4 DSP，100 MHz 综合估计时序未满足。生成物位于本地忽略目录，不能称为 ASIC 或 ADC 晶体管电路。

阶段三建立 Gu 基线；阶段四在同一条件下添加并比较新算法。公开论文没有给出的位级细节必须标为我们的实现假设。
