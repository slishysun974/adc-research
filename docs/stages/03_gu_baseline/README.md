# 阶段三：Gu 算法基线与分析

本阶段用阶段二理论分析Gu的gated-LMS数字PWL校准，建立浮点、定点及硬件候选基准。最后成果、开放问题与下一执行只看[STATUS](../../STATUS.md)，方法与优先级只看[主线计划](../../RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md)。本页定位研究／实现资料，不另维护进展日志。

先读[Gu综合评价](../../reports/GU_ALGORITHM_EVALUATION_V1.md)：原文原理与测量、项目候选合同、学习统计、输出／跟踪、资源及缺口分别评价。D-126—128基线闭环和D-132本批有限验收保持，不等同整个阶段二／三、芯片复刻或同成本PPA完成。当前继续误差机制、校正能力及按需条件分析，新算法设计仍暂缓。

## 来源、合同与实现

| 内容 | 入口 | 可支持范围 |
|---|---|---|
| 架构与码制 | [规格索引](../../specifications/README.md)、[总线／双路径来源审计](DIGITAL_BUS_AND_DUAL_PATH_SOURCE_AUDIT_V1.md)、[候选接口](DIGITAL_INTERFACE_CANDIDATE_A_V1.md) | 公开结构、自行补足和未公开细节分开，不声称芯片逐位复现 |
| 在线可见信息 | [信息边界审计](ONLINE_INFORMATION_BOUNDARY_AUDIT_V1.md) | 原配置来源修订及数字样本合同；真值／目标只离线使用 |
| 抽取与更新时序 | [抽取要求](DECIMATION_INFORMATION_REQUIREMENTS_V1.md)、[同步记录协议](DIGITAL_EXTRACTION_TRACE_PROTOCOL_V1.md) | 测量抽取不确定学习统计／广播；逐转换与120槽窗口候选分开 |
| 软件与评分 | [校准入口](../../../src/adc_research/calibration/README.md)、[评分入口](../../../src/adc_research/evaluation/README.md) | 正式源码与专用实验协议分开，oracle不进入更新 |
| 定点、RTL及综合 | [RTL入口](../../../rtl/README.md)、[精确更新算术](CANDIDATE_A_EXACT_UPDATE_ARITHMETIC_V1.md)、EXP-026／030—035、[多拍整改](../../reports/RTL_MULTICYCLE_TIMING_2026-10-16.md) | 原逐转换Artix-7失败；多拍Zynq的100 MHz结果及接收速率单列，均不实现120槽窗口聚合合同 |

## 按研究问题追溯实验

全部对象、专用定义、报告／理论和本地运行由[实验报告索引](../../reports/experiments/README.md)定位，不从历史报告的“下一项”选择任务。

| 问题 | 实验与理论入口 | 复用时注意 |
|---|---|---|
| 基础原理、标量统计、静态两级与定点 | EXP-055—059；[标量统计](../../theory/MILLION_SAMPLE_SCALAR_MEAN_NOISE_AND_QUANTIZATION_V1.md)、[定点理论](../../theory/STATIC_FIXED_POINT_ERROR_AND_LEARNING_V1.md) | 平均位置、波动、表示与量化分别判断；早期局部不利方向以EXP-055之后的解释核查 |
| 主辅／比较器失配与学习支持 | EXP-060—064；[主辅阈值理论](../../theory/DUAL_PATH_EFFECTIVE_THRESHOLDS_AND_PHASES_V1.md) | 短合同和必要有限长记录均按原条件复用，支持增加不保证收益 |
| 幅度切换与动态历史 | EXP-065—068；[跟踪条件](../../theory/EXCITATION_AND_CONSTRAINED_STABILITY_V1.md)、[四路窗口历史](../../theory/FOUR_LANE_WINDOW_DYNAMIC_LEARNING_V1.md) | 已完成指定有限路径，完整状态承接不可省略；没有一般动态／PVT覆盖 |
| 学习率、启动、恢复与频率／时间排序 | [EXP-069](../../reports/experiments/EXP_069_GU_LEARNING_RATE_V1.md)、[EXP-070](../../reports/experiments/EXP_070_GU_LEARNING_RATE_SWITCH_V1.md)、[EXP-071](../../reports/experiments/EXP_071_COHERENT_FREQUENCY_PREFLIGHT_V1.md) | 保留全部种子、末端／原判据失败；确认已消费，full120多30倍学习观测 |
| 正常位置、持续更新、级反馈及门通道 | [EXP-072](../../reports/experiments/EXP_072_NORMAL_STATE_INTERVENTION_V1.md)、[EXP-073](../../reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md)、[EXP-074](../../reports/experiments/EXP_074_LEARNING_SIGNAL_GATE_INTERVENTION_V1.md)；[两级理论§16—19](../../theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md) | 固定初态／保持值／连接／期限的因果关系；同旧字损失与真实未来传播分别报告 |
| 相位、滤波、目标方向及提交候选的历史准备 | EXP-049—054、NG-24—28；[理论索引](../../theory/README.md)、[计划历史](../../reports/STATIC_FIXED_POINT_PLAN_HISTORY_2026-10-11.md) | 原失败与成本保持，不恢复旧候选优化，不按已见分数选规则 |

理论归入阶段二问题文档，由原证据表登记；实验核对Gu合同，Gu评价集中解释优点／限制，阶段含义和解释演变归入[综合分析](../../reports/RESEARCH_SYNTHESIS_2026-10-10.md)。专用入口在`experiments/`，原始产物在`artifacts/runs/`，只读补分析可复用原实验，不为理论成果补造EXP。

新增适用轴须有具体预测、用途和预算；真实数据、新算法和目标工艺PPA仍按另外的方向讨论。用户已按D-145单独授权本轮多拍RTL时序整改，实际验收以STATUS与整改报告为准；其他硬件方向仍须另定范围。真实位宽、随机源、时序和芯片物理条件继续作为公开证据缺口，不能由候选实验填成硅真值。
