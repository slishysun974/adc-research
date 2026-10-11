# 阶段三：Gu 算法基线

本阶段用阶段二理论分析并验证Gu的gated-LMS数字PWL校准，建立浮点、定点和硬件候选基准。当前状态看 [STATUS](../../STATUS.md)，下一阶段方法看 [已批准计划](../../RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md)。本页只维护资料位置与范围。

当前先读[Gu算法综合评价报告](../../reports/GU_ALGORITHM_EVALUATION_V1.md)。报告已交付，用户按D-115／116继续Gu学习率与收敛研究，当前方法见计划§13.5及[EXP-069](../../../experiments/exp_069_gu_learning_rate/README.md)。新算法寻找后置；以下入口保留详细来源和历史成果，不据旧“下一项”提前推进候选。

## 研究与实现入口

| 内容 | 入口 | 最强解释 |
|---|---|---|
| 完整客观评价 | [Gu综合报告](../../reports/GU_ALGORITHM_EVALUATION_V1.md) | 原理、公开测量、候选边界、学习统计、输出／跟踪、硬件及开放事项的集中评价；不等于芯片全复现 |
| 在线信息边界 | [代码审计](ONLINE_INFORMATION_BOUNDARY_AUDIT_V1.md) | 算法只接收允许的数字样本；历史配置来源问题须保留 |
| 芯片总线与候选接口 | [总线来源审计](DIGITAL_BUS_AND_DUAL_PATH_SOURCE_AUDIT_V1.md)、[候选接口](DIGITAL_INTERFACE_CANDIDATE_A_V1.md) | 公开结构与自行补足分别标记，不称逐位芯片复现 |
| 抽取与提交时序 | [抽取信息要求](DECIMATION_INFORMATION_REQUIREMENTS_V1.md)、[同步记录协议](DIGITAL_EXTRACTION_TRACE_PROTOCOL_V1.md) | 测量抽取率不确定学习器保留的统计量或广播时刻 |
| 统一输出与定点候选 | 实验索引中的EXP-023—027、030—032 | 指定记录与数值合同内的性能／逐码核对 |
| 通用综合与等价算术 | EXP-034／035及 [精确算术说明](CANDIDATE_A_EXACT_UPDATE_ARITHMETIC_V1.md)、[RTL入口](../../../rtl/README.md) | 有通用逻辑结构结果，尚无目标工艺面积、频率、功耗或真实四路硬件 |
| 长期基础控制 | [EXP-055](../../reports/experiments/EXP_055_MODEL_DITHER_AUDIT_V1.md)、[EXP-056](../../reports/experiments/EXP_056_MILLION_SCALAR_STATISTICS_V1.md)、[EXP-057](../../reports/experiments/EXP_057_STATIC_TWO_STAGE_MILLION_V1.md) | 原理／标量／静态两级结果分层；长期定点见EXP-059、静态主辅失配见EXP-061，必要有限动态长期见EXP-068 |
| 静态定点预检 | [EXP-058](../../reports/experiments/EXP_058_STATIC_FIXED_PREFLIGHT_V1.md)、[局部合同与推导](../../theory/STATIC_FIXED_POINT_ERROR_AND_LEARNING_V1.md) | 码域、门保护、完整端点和短提交通过；不等于百万定点稳态或芯片位宽 |
| 静态定点长记录 | [EXP-059](../../reports/experiments/EXP_059_STATIC_FIXED_MILLION_V1.md)、[均值／协方差推导](../../theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md) | 150条定点百万路径、固定后级有限矩和输出控制完成；八状态整体归因／平稳分布与物理适用性仍开放 |
| 独立主辅静态预检 | [EXP-060](../../reports/experiments/EXP_060_STATIC_AUXILIARY_PREFLIGHT_V1.md)、[分支／学习推导§8—11](../../theory/DUAL_PATH_EFFECTIVE_THRESHOLDS_AND_PHASES_V1.md) | 抵消与条件零相关、失配第三门条件及完整短提交核对；不是长期失配性能或芯片结论 |
| 必要静态失配长记录 | [EXP-061](../../reports/experiments/EXP_061_STATIC_AUXILIARY_MILLION_V1.md)、[观测／状态／选门交叉§12](../../theory/DUAL_PATH_EFFECTIVE_THRESHOLDS_AND_PHASES_V1.md) | 80条预定路径及全部冻结／在线评分完成；共同支持不作收益验收，动态／一般八状态分布仍开放 |

同输入全程后台参考见[EXP-062](../../reports/experiments/EXP_062_SAME_INPUT_BACKGROUND_V1.md)及[连续输出／净收益§6](../../theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md)：名义阈值30路径，全部实际输出／数字提交重放；净收益、经验稳定及平均功率分开。比较器必要长配对见EXP-064，输入切换见EXP-065／066，必要有限动态长期见EXP-068。

逐级固定比较器偏移的推导／短核对见[EXP-063](../../reports/experiments/EXP_063_STATIC_COMPARATOR_PREFLIGHT_V1.md)及[阈值理论§13](../../theory/DUAL_PATH_EFFECTIVE_THRESHOLDS_AND_PHASES_V1.md)。36路径／零偏移前缀通过，当前周期第一级四点系数恒等式已证明；60条必要同输入长配对已由[EXP-064](../../reports/experiments/EXP_064_STATIC_COMPARATOR_BACKGROUND_V1.md)完成，新增§13.7完整观测交叉与有限输出支撑，全部数字码／提交核对；开门／支持／更新不代替收益。计划5c已由[EXP-065](../../reports/experiments/EXP_065_INPUT_SWITCH_PREFLIGHT_V1.md)短预检及[EXP-066](../../reports/experiments/EXP_066_INPUT_SWITCH_TRACKING_V1.md)60条跟踪长路径完成；5d入口推导／静态退化与短预检已由EXP-067完成，必要有限动态长期已由EXP-068完成。

算法入口是 `src/adc_research/calibration/`，离线观测和评分在 `evaluation/`，实验定义在 `experiments/`，原始产物在 `artifacts/runs/`。全部编号工作见 [实验报告索引](../../reports/experiments/README.md)，解释修订见 [综合分析](../../reports/RESEARCH_SYNTHESIS_2026-10-10.md)。

动态5d入口见[EXP-067](../../reports/experiments/EXP_067_DYNAMIC_HISTORY_PREFLIGHT_V1.md)及[窗口历史§6](../../theory/FOUR_LANE_WINDOW_DYNAMIC_LEARNING_V1.md)：18短路径全物理／数字核对，零动态旧短匹配与完整历史承接通过。复位仍有当次未建立误差，四点未选槽位须推进模拟历史；该报告只承担入口短验收，后续[EXP-068](../../reports/experiments/EXP_068_DYNAMIC_BACKGROUND_V1.md)完成60必要有限动态路径及全部输出／状态核对；一般动态／八状态与芯片参数仍开放。

## 理论与实验如何配合

收敛、有效观测、有限字长和输出误差的推导归入阶段二，并由现有证据表索引；本阶段负责Gu候选的合同核对和验证。各段门、基函数和共同支持分别计数；平均位置、持续波动、最终输出及速度／资源分别评价。

百万总观测不保证高段得到信息；完整累计收益不能直接称同成本胜出；局部不利更新次数不能单独判定平均目标错误。真实位宽、随机源和时序继续待证，算法只能使用实际可见信号。新算法及工艺成本仍不在本阶段已有成果之内。

NG-22的目标条件／范围推导见[两级理论§10](../../theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md)，只读核对入口为[check_target_bounds.py](../../../experiments/exp_068_dynamic_background/check_target_bounds.py)。原180窗360矩组、全部端点／读出及433回归通过；52窗原下一提交的同旧字整数输出保持，其中45窗有效导出已经改变。目标半码盒只有离线控制职责，不判未来收益或真实停更；接续仍按STATUS研究共同相关保持方向。

NG-23的相关方向／直线／根曲线及输出条件见[两级理论§11](../../theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md)，核对入口为[check_preserving_directions.py](../../../experiments/exp_068_dynamic_background/check_preserving_directions.py)。原180窗1306全部核基／1822交叉、全部定点读出及443回归通过；17离线定点方向保持原Q3相关量而整数输出变。当前相关均非零，不把同水平保持叫旧状态共同根，不当实际未来Gu收益。

计划§10.4的改进依据综合已完成，见[综合分析§21](../../reports/RESEARCH_SYNTHESIS_2026-10-10.md)及[窗口成本§7](../../theory/FOUR_LANE_WINDOW_DYNAMIC_LEARNING_V1.md)。150旧路径五项评分摘要复核，优先讨论有限选样／持续适应代价与覆盖，尚未选定新算法；当前原在线算法／RTL保持，具体在线合同及独立留出预算另行讨论。共享相关和位数不换算工艺成本，完整累计仍多30倍学习观测。

NG-24的四样本选样条件见[Dither§8](../../theory/DITHER_INFORMATION_AND_STOCHASTIC_UPDATE_AUDIT_V1.md)，只读入口为[check_lane_statistics.py](../../../experiments/exp_068_dynamic_background/check_lane_statistics.py)。180旧窗口两层共360协方差对全部不可统一排序；21600原整数码、来源与121数据核对，450回归通过。均值保持不替代低方差，独立相位未实现为在线算法；实际PRNG、输出权重和相位／同步成本仍须具体合同。

NG-25的输出权重／有效导出条件见[Dither§9](../../theory/DITHER_INFORMATION_AND_STOCHASTIC_UPDATE_AUDIT_V1.md)，只读入口为[check_selection_output.py](../../../experiments/exp_068_dynamic_background/check_selection_output.py)。两层各96窗独立连续MSE较低、84窗共同较低；实际共同相位180窗前级平均导出不同于完整一次导出，29窗连续／整数损失反号。原字／下一bank提交／有限矩及720盒端点精确，八项新控制与458回归通过，原来源／122数据保持；新增转换／训练／FFT0。评分冻结旧后级，不当原两级未来输出；在线概率、提交时序、共同目标／高阶及公平留出仍待讨论。

NG-26的因果概率／截止条件见[Dither§10](../../theory/DITHER_INFORMATION_AND_STOCHASTIC_UPDATE_AUDIT_V1.md)，只读入口为[check_selection_probabilities.py](../../../experiments/exp_068_dynamic_background/check_selection_probabilities.py)。均匀5位字模30及四次拒绝后回0两个理想概率控制，分别在原180窗产生18／15和0／0连续／整数比较反号；十项精确控制、每层64800必要补评分／1440盒端点及468回归通过，原源／数据保持。现有相位调度和随机流未改，位预算不认证随机源或截止时钟；具体源、状态承接及未来闭环仍待合同。

NG-27的完整两级四格／平方损失交互及输出矩见[两级§12](../../theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md)，只读入口为[check_joint_selection_output.py](../../../experiments/exp_068_dynamic_background/check_joint_selection_output.py)。原180窗理想均匀联合／前级13窗反号、联合／两单级之和7窗反号；原下一提交、2008800整数读出、194400有理数探针及3240盒端点精确，十项控制／478回归及原来源／122数据保持。边界／跨段保留、v1类型失败归档，新增转换／训练／FFT0；阶段含义及候选合同入口见[综合分析§25](../../reports/RESEARCH_SYNTHESIS_2026-10-10.md)，没有新算法或未来收益结论。

NG-28的四路错开候选几何／跨相位统计及合同见[相位理论](../../theory/FOUR_POINT_PHASE_SELECTION_CONDITIONS_V1.md)，只读入口[check_staggered_phases.py](../../../experiments/exp_068_dynamic_background/check_staggered_phases.py)。偏移按时间几何固定；原180窗拟议相位同旧状态相对固定0只有58负／122正，辅助方差与理想联合损失52窗反号，未升级为优选在线方案。1944000整数读出／172800有理数探针及488回归、原来源／122数据通过；无新转换／训练／FFT或候选未来状态，具体判断见[综合分析§26](../../reports/RESEARCH_SYNTHESIS_2026-10-10.md)。
