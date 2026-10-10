# 阶段三：Gu 算法基线

本阶段用阶段二理论分析并验证Gu的gated-LMS数字PWL校准，建立浮点、定点和硬件候选基准。当前状态看 [STATUS](../../STATUS.md)，下一阶段方法看 [已批准计划](../../RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md)。本页只维护资料位置与范围。

## 研究与实现入口

| 内容 | 入口 | 最强解释 |
|---|---|---|
| 在线信息边界 | [代码审计](ONLINE_INFORMATION_BOUNDARY_AUDIT_V1.md) | 算法只接收允许的数字样本；历史配置来源问题须保留 |
| 芯片总线与候选接口 | [总线来源审计](DIGITAL_BUS_AND_DUAL_PATH_SOURCE_AUDIT_V1.md)、[候选接口](DIGITAL_INTERFACE_CANDIDATE_A_V1.md) | 公开结构与自行补足分别标记，不称逐位芯片复现 |
| 抽取与提交时序 | [抽取信息要求](DECIMATION_INFORMATION_REQUIREMENTS_V1.md)、[同步记录协议](DIGITAL_EXTRACTION_TRACE_PROTOCOL_V1.md) | 测量抽取率不确定学习器保留的统计量或广播时刻 |
| 统一输出与定点候选 | 实验索引中的EXP-023—027、030—032 | 指定记录与数值合同内的性能／逐码核对 |
| 通用综合与等价算术 | EXP-034／035及 [精确算术说明](CANDIDATE_A_EXACT_UPDATE_ARITHMETIC_V1.md)、[RTL入口](../../../rtl/README.md) | 有通用逻辑结构结果，尚无目标工艺面积、频率、功耗或真实四路硬件 |
| 长期基础控制 | [EXP-055](../../reports/experiments/EXP_055_MODEL_DITHER_AUDIT_V1.md)、[EXP-056](../../reports/experiments/EXP_056_MILLION_SCALAR_STATISTICS_V1.md)、[EXP-057](../../reports/experiments/EXP_057_STATIC_TWO_STAGE_MILLION_V1.md) | 原理／标量／静态两级结果分层；长期定点和主辅失配／动态待加入 |

算法入口是 `src/adc_research/calibration/`，离线观测和评分在 `evaluation/`，实验定义在 `experiments/`，原始产物在 `artifacts/runs/`。全部编号工作见 [实验报告索引](../../reports/experiments/README.md)，解释修订见 [综合分析](../../reports/RESEARCH_SYNTHESIS_2026-10-10.md)。

## 理论与实验如何配合

收敛、有效观测、有限字长和输出误差的推导归入阶段二，并由现有证据表索引；本阶段负责Gu候选的合同核对和验证。各段门、基函数和共同支持分别计数；平均位置、持续波动、最终输出及速度／资源分别评价。

百万总观测不保证高段得到信息；完整累计收益不能直接称同成本胜出；局部不利更新次数不能单独判定平均目标错误。真实位宽、随机源和时序继续待证，算法只能使用实际可见信号。新算法及工艺成本仍不在本阶段已有成果之内。
