# EXP-073：单级更新与后级进入前级学习的因果分离

固定原平滑五种子、两倍率、两起点及[128,136)，新增仅前级／仅后级完整路径，另定义后级输出正常而前级学习使用保持后级的连接切断。全部合同、预测与预算见[协议](protocol.json)，证明见[两级NG-40](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md#17-ng-40单级学习干预及后级进入前级学习的因果分离)，结果见[实验报告](../../docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md)。

原数字字静态前馈，与校准系数独立；新更新仅读数字五字段及自身Q22。目标只进入离线评分。连接切断和bank保持是专用因果诊断，不能冒称Gu或新的在线算法，额外shadow读出／状态成本未做硬件验收。

原冻结流程在正式实验目录登记前运行`run.py prepare --out <新记录目录>`，随后`run`与`verify_analyze`。本对象已完成，当前prepare拒绝编号重复，run拒绝完成目录覆盖；无需重跑原记录。需要复算时先复制完整原记录到新的专用目录，使用复制记录中的`frozen_run.py verify_analyze --out <复制目录>`，保留新核对日志和计数；不要在原冻结目录覆盖验收。原源码／协议与全部数据位于`artifacts/runs/EXP_073/bank_feedback_v1/`。

保存历史的请求／门／参数差只读分析入口为[analyze_feedback.py](analyze_feedback.py)。先以`prepare --out <新分析目录>`冻结来源、对象和控制，再运行`analyze`；已有分析目录拒绝覆盖。最终v2及初v1索引拒绝均在`artifacts/research/rear_to_front_requests_20261013_v1/`与`..._v2/`保存；本文原未来路径不重跑。后续学习输入通道的完整干预属于独立EXP-074，不能拿该四角请求分析替代。

前级自主增损的固定驱动／自身响应及实际平均位置／变化见[报告§9](../../docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md#9-前级自主增损的固定驱动状态响应与实际参数变化)、[NG-46／两级§24](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md#24-ng-46前级固定状态驱动自身响应与实际变化的损失关系)。[analyze_front_history.py](analyze_front_history.py)只核对保存的原20前级路径，以冻结初态请求分开有限均值、中心化驱动和状态响应，再按完整Gram与目标交叉恢复原损失；不传播新学习。

模块`experiments.exp_073_bank_feedback_intervention.analyze_front_history`用`prepare --out <新目录>`及`analyze --out <同目录>`，需`$env:PYTHONPATH='src;.'`且拒绝覆盖。初v1大整数保护拒绝和正式v2分别在`artifacts/research/front_forcing_response_20261013_v1/`、`..._v2/`保存；正式20份2048×24矩及指纹可复用，预算和失败另记。

[analyze_front_position.py](analyze_front_position.py)在独立冻结后，以实际2048窗平均导出和逐窗变化作连续差参照，只补缺少的保持后级数字基函数矩。模块同样使用`prepare`、`analyze`、新目录及上述PYTHONPATH，记录在`artifacts/research/front_position_variation_20261013_v1/`。平均参照使用未来记录，只作离线损失分析，不是合法整数均值读出、初始化或在线能力保证；已有数据足够时不重复读出。

[analyze_front_timescales.py](analyze_front_timescales.py)复用实际请求／导出与旧损失，将变化分成原八块均值迁移、块内中心化变化，保留两个加入顺序和全部交叉，另核对平均位置输出矩与实际移动状态请求矩。使用同样的`prepare`／`analyze`及新目录，正式只读结果在`artifacts/research/front_block_migration_20261014_v1/`，见[报告§10](../../docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md#10-块均值迁移块内变化与平均位置矩的只读补证)。保存的两基函数和逐窗Gram／保持投影支持后续复用；分块参照不提供新的在线观测或物理噪声归因。

[analyze_front_block_requests.py](analyze_front_block_requests.py)把原块内实际请求分成输出前线性均值驱动、中心化请求累计及真实中心化导出误差；复用上一轮基函数，不执行PWL／门／请求或学习。使用`prepare`、在新目录完成独立有理中心化控制后再`analyze`，正式记录在`artifacts/research/front_centered_requests_20261014_v1/`，见[报告§11](../../docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md#11-实际块内请求的线性移动中心化累计与真实导出)。新2048×8历史矩、原门计数／请求产品与两个顺序结果可复用；执行前预算计数器拒绝超限，不覆盖既有冻结运行。

[analyze_front_block_response.py](analyze_front_block_response.py)复用固定初态／实际Q22请求及旧历史矩，把中心化累计分成固定四字驱动和自身响应，保留含／不含实际线性驱动两个上下文及两个加入顺序。使用`prepare`、新目录独立中心化控制后再`analyze`；记录在`artifacts/research/front_centered_response_20261014_v1/`，见[报告§12](../../docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md#12-块内累计的固定初态驱动与自身响应)。新2048×4历史矩列／尺度在冻结协议，PWL／门／请求／学习重算0，保留全部未认证小项及预算计数。

[analyze_front_fixed_sampling.py](analyze_front_fixed_sampling.py)先把原NG-45固定角点和u0按初态／来源／时刻／尺度验收，再从原矩恢复首段全槽产品，把固定请求中心化累计拆成全槽背景、四字选样差及真实取整。使用`prepare`、`qualify`，新目录独立有理控制通过后再`analyze`；记录在`artifacts/research/front_fixed_sampling_20261014_v1/`，见[报告§13](../../docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md#13-首段固定累计中的四字选样差与全槽背景)。配对2048×6、历史2048×7矩的列／尺度和分阶段预算在冻结协议；原第二低段和所有交叉保留，PWL／门／请求／学习重算0，全槽30倍观测只作离线有理参照。

[analyze_front_sources_and_capacity.py](analyze_front_sources_and_capacity.py)将第二前级低段的固定请求分成无门背景、门筛选、选样、交互和真实取整，并把各来源接到块内累计、平均位置及块均值迁移；原两参数交叉和真实整数损失保持。`freeze --out <新目录>`冻结原20／160合同后用`analyze --out <同目录>`；[check_front_sources_and_capacity.py](check_front_sources_and_capacity.py)以`--out <同目录>`独立检查标量时间算子、历史Gram／目标投影和五字段整数映射下限。[bound_front_capacity_witness.py](bound_front_capacity_witness.py)同样用`--out`，在预定单个合法低两系数见证上补低支持精确／高支持区间上界，无候选搜索或学习。结果在`artifacts/research/front_gate_migration_capacity_20261014_v2/`，v1仅能力矩NumPy Fraction溢出失败保留；固定门缺量及见证边界分别有预算，不重复已存移动读出或政策。见[报告§14—16](../../docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md#14-前级第二低段的门乘全槽选样与联合累计)。

[analyze_fixed_learning_alignment.py](analyze_fixed_learning_alignment.py)按D-140预定的合法均值与原较好见证完成同位置学习／输出比较，以`freeze --out <新目录>`、`analyze --out <同目录>`运行；[check_fixed_learning_alignment.py](check_fixed_learning_alignment.py)用`--out <同目录>`独立Fraction查表逐字恢复输出、全窗请求／损失及旧矩加舍入余项的真连续梯度，再做预定局部一次提交。完整合同／计数在`artifacts/research/front_fixed_alignment_20261014_v2/`，v1第一个位置NumPy Fraction方向乘积溢出保留，v2只转Python整数并冻结累计预算。见[报告§17](../../docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md#17-同一合法位置的学习方向整数误差与改善空间)。首轮40主记录位置已消费，复算不得覆盖原验收或重置预算；不由全槽方向或离线见证直接传播新政策。

[analyze_low_parameter_statistics.py](analyze_low_parameter_statistics.py)在原40位置只计算两低段统计对输出基函数的矩和连续门保护半径，使用`freeze`／`analyze`／`verify --out <同目录>`；独立核对按数字字／块权重分组，不重复原成绩评分。见[报告§18](../../docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md#18-两低段统计响应满秩目标方向与有限步条件仍独立)。原运行`artifacts/research/front_low_parameter_statistics_20261014_v1/`数值完成；门乘相关产品漏计／超原限在`accounting_reconciliation.json`，原冻结源码／账目保持。当前入口已只修未来计数和零操作类别标签，源版本差在`source_correction.json`；不能用修改后的代码或计数器标志改称旧运行完整预算通过，不在原目录覆盖／重跑。

[analyze_mean_objective_discrepancy.py](analyze_mean_objective_discrepancy.py)只复用40位置A／H／相关量／真梯度，规范分开矩权重与目标相容差；读取原20请求／导出以三角权重恢复合法平均位置。依次使用`freeze --out <新目录>`、等待冻结完成、`analyze --out <同目录>`和`check --out <同目录>`；检查器使用独立两方程消元与直接输出前状态平均。见[报告§19](../../docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md#19-满秩下矩权重有下降性相容差接回实际平均位置)，完整记录在`artifacts/research/mean_objective_discrepancy_20261014_v1/`。本轮无新PWL／门／请求／评分；二元Fraction与整数历史数据操作由计数包装器执行，排除口径及汇总上限在冻结协议。原冻结未完启动拒绝／零科学成本和待冻结后同协议接续记录保持，禁止覆盖原成绩或重置历史预算。

[analyze_discrepancy_information.py](analyze_discrepancy_information.py)按原40位置将相容差分开数字常数矩与目标投影，补原基函数的目标／粗码和绝对投影，不重算主记录PWL／门／请求／成绩。依次`freeze --out <新目录>`、`analyze --out <同目录>`、`check --out <同目录>`，拒绝覆盖；独立检查以数字字分组和后级Fraction查表直接恢复数字常数矩／H，范围及目标取消另核对。见[报告§20](../../docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md#20-相容差的信息分离粗判决不足附加输入条件改变判断)，记录`artifacts/research/discrepancy_information_20261014_v1/`。粗判决外界和附加正弦条件分开，原在线信息／成本与未来收益仍未认证；禁止覆盖旧数据或重置预算。
