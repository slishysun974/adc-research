# ADC课题阶段汇报备注

## 01_cover

本课题研究未知残差放大器非线性下的数字后台校准。Gu提供架构与算法基线。汇报按已经确认的七个研究模块组织，科学证据截至2026-10-15。一般未知增益完整理论、新算法公平优胜及真实芯片适用性尚未完成。

来源：D:/ADC/docs/PROJECT_CHARTER.md；D:/ADC/docs/STATUS.md；D:/ADC/docs/reports/ADVISOR_PROGRESS_REPORT_OUTLINE_2026-10-16.md。

## 02_objective

当前主问题是学习信息怎样形成实际系数历史、留下哪些输出误差，以及同数字信息和表示还允许改善多少。现有有限场景的来源解释已经形成阶段交付。平台的模拟真值和理想输入只用于离线评价。下一步重点是具体信息条件是否足以评价有益方向，随后还要区分算法发现方向与从同初态达到、保持。

来源：D:/ADC/docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md；D:/ADC/docs/STATUS.md。

## 03_modules

模块一至三提供平台、条件理论和实现基础。模块四解释信息及目标，模块五解释学习过程，模块六评价完整后台输出，模块七用受控对照检查误差来源与改善空间。七模块是研究分类，四阶段是推进路线，不用模块数量衡量阶段完成度。

来源：D:/ADC/docs/reports/PROJECT_STRUCTURE_AND_RESEARCH_REVIEW_2026-10-16.md。

## 04_signal_chain

图只概括行为模型的信号与信息关系。前级主残余送后级CDAC，辅助路径用于后级Flash判决。内部数字接口是两级symbol、末级centered code和两级dither tag。主辅静态或动态关系属于各配置的明确假设。图没有表达完整芯片时钟、模拟开关及全部前景校准。数字算法不读取理想输入、真实模拟曲线或离线目标。后级数字校正结果会参与前级局部重构及学习。

来源：D:/ADC/simulink_adc/README.md；D:/ADC/docs/reports/RESEARCH_MODULE_01_PLATFORM_V1.md；D:/ADC/docs/stages/03_gu_baseline/ONLINE_INFORMATION_BOUNDARY_AUDIT_V1.md。

## 05_platform_evidence

EXP-003对4096个理想码中心检查重构、单调性和缺失码。非理想控制将正确重构与不可纠正、过载及裁剪分开。Simulink独立实现覆盖23组、82,343次转换。数字及学习记录数值相等，模拟浮点量按预定容差验收。成果是声明行为条件内的平台可靠性，真实器件和未公开内部时序仍需额外证据。

来源：D:/ADC/docs/reports/STAGE1_PLATFORM_ACCEPTANCE_V1.md；D:/ADC/simulink_adc/VALIDATION.md；D:/ADC/simulink_adc/adc_behavioral.slx。

## 06_prediction_method

把各级阈值反算到ADC输入端，可以划分判决与最终码不变的输入区间。一个码可能对应多个区间，需合计码宽。给定正弦时可计算跨界时刻、连续周期谱或有限采样码。连续周期谱与有限记录谱有不同口径。范围传播需覆盖所有允许分支，不能只检验几条端点轨迹。早期分段一次模拟传输是可精确核对的特例，不由数字PWL推得。

来源：D:/ADC/docs/reports/RESEARCH_MODULE_02_PREDICTION_V1.md；D:/ADC/docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md。

## 07_prediction_results

EXP-015在四类固定条件、262,144个未参与构建的测试输入上核对最终码与可纠正状态。EXP-016核对18条有限记录、589,824个平台样本的码及评分。EXP-038的人工静态扫描控制给出较宽条件性频谱界限。严格数值覆盖与较窄物理约束分别判断。现有扫描并非Cadence或硅后实测。

来源：D:/ADC/docs/reports/experiments/EXP_015_STAGE2_STATIC_TRANSFER_V0_1.md；D:/ADC/docs/reports/experiments/EXP_016_STAGE2_STATIC_SPECTRUM_V0_1.md；D:/ADC/docs/reports/experiments/EXP_038_CERTIFIED_SPECTRUM_V1.md。

## 08_fixed_point

本候选前后级各四个斜率，PWL段间偏移由之前各段累计构成。后级先校正，再重构前级局部量并处理dither副本。Q3为数据保留3个二进制小数位，Q1.10为接口保留10小数位，Q22为内部更新累加精度。EXP-013的10小数位累加器控制中有效更新都舍入为零，提高内部精度才能保存小更新。接口暂时不变不表示隐藏状态已经停止。

来源：D:/ADC/docs/reports/RESEARCH_MODULE_03_IMPLEMENTATION_V1.md；D:/ADC/docs/reports/experiments/EXP_013_FIXED_LMS_ACCUMULATOR_V1.md；D:/ADC/docs/reports/GU_ALGORITHM_EVALUATION_V1.md §4。

## 09_hardware

单级、两级冻结系数和逐转换在线RTL有各自有限功能核对。等价整数约分减少粗糙宽算术的实现冗余，不改变算法规则。Artix-7原基线2548 LUT、184 FF、4 DSP、0 BRAM，100 MHz约束下WNS=-50.309 ns，WHS=-0.079 ns。此结果未满足时序。现有RTL逐转换提交，尚未实现后期120槽窗口聚合。两份旧电路汇报验收JSON缺失，保留不可复算范围。FPGA资源不能换算为ASIC面积或3 GS/s芯片实现能力。

来源：D:/ADC/docs/reports/CIRCUIT_REVIEW_VIVADO_RESULTS_2026-10-11.md；D:/ADC/rtl/README.md；D:/ADC/docs/reports/RESEARCH_MODULE_03_IMPLEMENTATION_V1.md。

## 10_observation

EXP-020构造两条严格单调的人工静态传输。16,384条训练记录未访问差异区间，因此五字段与最终码相同。另一条8,192点正弦记录有2个最终码不同。小差异足以否定这批有限训练对该记录的唯一确定性，但不提供芯片误差大小或继续观测无效的证据。原数值反例未启用数字PWL。后续完整历史反例和已知正弦条件在各自定义下分别成立，不能互换。

来源：D:/ADC/docs/reports/experiments/EXP_020_UNKNOWN_GAIN_IDENTIFIABILITY_V1.md；D:/ADC/docs/reports/RESEARCH_MODULE_04_INFORMATION_V1.md。

## 11_objective_gap

EXP-022固定其他系数、同一三次模拟曲线及同一训练码中心记录，只扫描第一级第一系数。相关零点k=1.0100002332432263，MAE=0.9206832062468951。MAE最小点k=1.0026077433840184，MAE=0.6570116136496067。图按模块报告舍入。此处评价未裁剪浮点输出的平均绝对误差，不与后期整数MSE混合。原参考状态有8条裁剪，但排除这些记录的控制仍保留目标差异。这个固定记录对照不证明完整八系数闭环已到达该相关根。

来源：D:/ADC/artifacts/runs/EXP_022/frozen_v2_20261001/summary.json，datasets.training_code_centers；D:/ADC/docs/reports/experiments/EXP_022_K1_OBJECTIVE_AUDIT_V1.md。

## 12_capability

分别定义观测、表示与策略集合。当前字固定映射的误差下限只适用于其函数集合。较好的固定系数说明表示可达某离线结果，构造依赖目标，不证明同初态在线可达到。局部相关统计可区分系数变化也不足以保证与最终损失目标相容。可信正弦条件能认证一个给定方向，与算法自己发现该方向分别判断。现有结果没有证明Gu全部数字统计或完整历史都不足。

来源：D:/ADC/docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md；D:/ADC/docs/reports/RESEARCH_MODULE_04_INFORMATION_V1.md；D:/ADC/docs/STATUS.md。

## 13_sampling

本项目窗口候选在120个转换中保持旧系数输出，末尾统一提交。point30采用首四字，其原始相关和乘30。full120采用全部120字，相关和乘1，固定分母120。这是明确候选，芯片真实聚合与广播未完全公开。乘30在适当条件下对齐平均尺度，但未增加观测量。独立同方差条件下可推估计方差比例，真实门控、相位和反馈不自动满足独立性。动态状态在全部转换推进，未采用转换不能跳过。

来源：D:/ADC/docs/reports/RESEARCH_MODULE_05_LEARNING_V1.md；D:/ADC/docs/theory/FOUR_LANE_WINDOW_DYNAMIC_LEARNING_V1.md；D:/ADC/simulink_adc/README.md。

## 14_scalar_learning

EXP-056为明确的单级、单斜率、无记忆控制。无量化时，增益0.975的正确逆增益约1.025641，与解析均值和长记录相容。固定步长仍导致持续波动。小摆幅和直流量化控制的相关平衡为1.024，更多全样本降低波动但不消除均值偏差。量化误差可能与dither相关。三个现象依赖不同条件，不能直接套用为完整两级系统的统一时间常数或稳态保证。

来源：D:/ADC/docs/reports/experiments/EXP_056_MILLION_SCALAR_STATISTICS_V1.md；D:/ADC/docs/theory/MILLION_SAMPLE_SCALAR_MEAN_NOISE_AND_QUANTIZATION_V1.md。

## 15_background_method

训练后冻结评分检验某检查点系数。持续后台评分保留所有转换且继续更新，含校正与适应的共同效果。Simulink性能演示属于full120浮点训练并在检查点评分，不等于后期Q3/Q1.10/Q22持续后台路径。后期实验分别看启动、后期及输入切换，保留全部种子、不利时间块和失败。页上时间条仅为方法示意，无实际预算比例。

来源：D:/ADC/docs/reports/RESEARCH_MODULE_06_BACKGROUND_PERFORMANCE_V1.md；D:/ADC/simulink_adc/PERFORMANCE_DEMO.md；EXP-062、069、070原报告。

## 16_learning_rate

EXP-069同数字流、同输出时长，仅改变共同学习率倍率。图为四样本方式后期整数MSE五种子均值。线性条件单位不更新15.827、原步长33.945、1/4步长9.288。平滑条件依次32.176、34.406、10.166码²。两组1/4均为五种子改善。数字MSE按最终整数码与理想电平比较并保留直流。该批收益不确定全局最优，也不证明持续稳定或任意输入改善。

来源：D:/ADC/docs/reports/experiments/EXP_069_GU_LEARNING_RATE_V1.md；D:/ADC/docs/reports/RESEARCH_MODULE_06_BACKGROUND_PERFORMANCE_V1.md。

## 17_recovery

EXP-070幅度0.82降0.41，完整隐藏状态和全局时刻承接。恢复定义比较承接旧状态与从新单位初值启动的路径，二者先有输出收益，再连续满足接近条件。这里表格为full120，不是上一页point30。原步长两模型末端各5/5并维持至终点。1/4线性0/5、平滑2/5。有限恢复计数不估总体失败概率；小步长后期误差更好也不能据此宣布恢复统一更快。

来源：D:/ADC/docs/reports/experiments/EXP_070_GU_LEARNING_RATE_SWITCH_V1.md；D:/ADC/docs/reports/RESEARCH_MODULE_06_BACKGROUND_PERFORMANCE_V1.md。

## 18_intervention

本批主要研究原both_smooth，种子202610621—625，倍率1及1/4，两个已保存起点，评价[128,136)八块。活动bank重算自身门、请求、Q22状态和输出。原静态数字源不依赖改变的数字系数，使同源未来对照成立。保持级、切断学习连接、混合学习数值与门来源，均有明确定义。代数删除旧历史项与重新传播未来干预分别判断。后级进入前级数字学习的关系，不等于模拟前级不会影响后级。

来源：D:/ADC/docs/reports/experiments/EXP_072_NORMAL_STATE_INTERVENTION_V1.md；D:/ADC/docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md；EXP-074—077原报告。

## 19_sampling_effect

EXP-075保持后级原隐藏状态，从各例同初态运行前级完整反馈。散点为保存的整期整数MSE，每例x为四样本、y为全样本，共20点，同轴范围0..60。全槽相对四字20/20改善并按原目标条件认证。全槽相对保持6例增损均认证，14例名义改善中一项小改善未认证。全样本30倍前级观测，不代表同成本、频谱、启动、恢复或未知输入优胜。整期均改善也不代表所有160个时间块均改善。部分点接近或重叠，未作抖动。

来源：D:/ADC/artifacts/runs/EXP_075/front_sampling_v1/results.json；D:/ADC/docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md。展示值另存sources/exp075_presentation_values.json，保留来源SHA256。

## 20_remaining_cases

六例全槽对保持增损中，4例平均位置与持续变化均不利，2例有益位置被变化抵消。平均位置为离线历史参照，不一定是合法整数状态。四坏均值处的固定连续方向2增损、2减损，平均相关量均非零且局部统计满秩，不能统一为方向错误、参数不可区分或坏根收敛。持续变化条件项包含与输出及目标的交叉，不能称为纯方差或独立物理份额。

来源：D:/ADC/docs/STATUS.md；D:/ADC/docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md §29—45；D:/ADC/docs/reports/RESEARCH_MODULE_07_ERROR_MECHANISMS_V1.md。

## 21_gate_case

仅种子625前缀起点、1/4的一例。原全槽MSE3.333927623；使用原未来均值构造第二门3.059911930；可见合法初态构造门3.445446290；保持3.194836766；旧离线合法系数W为1.920095347码²。均值门和初态门均重算完整前级反馈，后级保持。未来均值是离线信息。W依赖离线目标且低两初态不同，不能当同初态在线可达结果。初态门失败只否定这一具体参照，不能证明所有有益门都需未来信息。原不利块、未认证和完整成本合同失败均保留。

来源：D:/ADC/docs/reports/experiments/EXP_076_FIXED_MEAN_GATE_INTERVENTION_V1.md；D:/ADC/docs/reports/experiments/EXP_077_INITIAL_GATE_INTERVENTION_V1.md；D:/ADC/docs/STATUS.md。

## 22_history_and_space

时间权重和门状态解释不同环节。旧记录有一例固定时间权重已翻向，另一例需保留自身门变化。后级传导在指定干预下有益、有害并存，不能统一删除。原20个合法固定见证都优于新全槽，见证使用离线目标。给定方向的损失评价、实际移动请求累计、最终整数MSE和完整未来干预的结果各有合同，不合成为唯一百分比。

来源：D:/ADC/docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md §29—45；D:/ADC/docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md §77。

## 23_conclusions

四点分别总结研究基础、目标关系、持续学习评价及有限归因。课题已从实现基线进一步推进到有条件解释学习与输出误差，尚未完成一般未知增益理论或同成本新算法。软件一致性、数学条件、有限行为结果和物理适用性分别判断。

来源：D:/ADC/docs/STATUS.md；D:/ADC/docs/reports/GU_ALGORITHM_EVALUATION_V1.md §9.3。

## 24_next_question

下一研究先选择哪项实际可见信息或可信输入条件，能够把给定目标方向的评价推进为在线可判断条件。已有相关统计与已知正弦约束提供了具体比较入口，需明确仍缺少的目标信息及充分性或必要性关系。算法发现、同初态到达保持、公平成本及一般输入仍开放。此页说明研究关系，不宣称新实验、算法或硬件实施已经完成。

来源：D:/ADC/docs/STATUS.md；D:/ADC/docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md。

## 25_metrics

MAE与MSE有不同单位。EXP-022为未裁剪浮点MAE，EXP-069等为最终整数MSE。SNDR评分去除直流，以基波为参照，因此MSE排序不一定与SNDR相同。SFDR取决于最大杂散，误差总功率相同仍可有不同频率分布。EXP-062四字平滑条件平均SNDR提高0.994 dB，而MSE由32.176升34.406。还需区分先平均dB、先平均功率，以及同观测量与同转换时长。

来源：D:/ADC/docs/specifications/ADC_METRICS_PROTOCOL_V1.md；D:/ADC/docs/reports/experiments/EXP_062_SAME_INPUT_BACKGROUND_V1.md；模块四、六。

## 26_gu_mapping

原文公开数字PWL、累计偏移、dither相关和后级先校正。11位系数含10小数位以及数据保留3小数位有原文来源。Q22内部累加、具体步长、最近偶数舍入、饱和及120槽提交属于项目候选。原文四路750 MHz抽取30，片内相关量保留、聚合及系数广播尚未完全公开。静态三次曲线、部分主辅假设及动态参数均不是芯片提取结果。

来源：D:/ADC/docs/reports/GU_ALGORITHM_EVALUATION_V1.md §4；D:/ADC/docs/specifications/GU_ARCHITECTURE_EVIDENCE_V1.md；D:/ADC/docs/stages/03_gu_baseline/DIGITAL_BUS_AND_DUAL_PATH_SOURCE_AUDIT_V1.md。

## 27_evidence_index

页码固定，七模块与正文一一对应。每页备注保存解释与主要来源。理论、实验报告和原始记录各有不同职责。当前进展以STATUS为准，旧实验报告中的下一项仅代表历史安排。完整入口为D:/ADC/docs/README.md和D:/ADC/docs/reports/PROJECT_STRUCTURE_AND_RESEARCH_REVIEW_2026-10-16.md。

来源：D:/ADC/docs/README.md；本目录README.md；D:/ADC/docs/reports/experiments/README.md。

## 28_limits

保留原未认证项、预算与资料边界。EXP-075及旧补分析的门产品漏账或超限、EXP-077完整成本合同失败不能由数值关系核对改写为全部验收通过。原全槽对保持的一项整期小改善仍跨目标范围。Gu确认2003/4001已消费，未来6007/8009未生成评分。旧电路两份JSON缺失，100 MHz失败，工艺PPA未完成。未来均值、目标和合法见证为离线参照，不进入原Gu在线算法。有限完成不等于阶段二三整体完成。

来源：D:/ADC/docs/STATUS.md“必须保留的失败、未认证与边界”；D:/ADC/docs/reports/RESEARCH_MODULE_07_ERROR_MECHANISMS_V1.md；D:/ADC/docs/reports/CIRCUIT_REVIEW_VIVADO_RESULTS_2026-10-11.md。
