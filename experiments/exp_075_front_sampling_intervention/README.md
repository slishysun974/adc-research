# EXP-075：前级四字／全槽观测的有限闭环干预

原五种子、两倍率、两起点、[128,136)终点及完整Q22保持，后级保持，前级四坐标完整重算。仅新增20条原Gu full120路径，point30及双保持复用，不是同成本新算法。

具体模型、可否定预测、信息／学习成本、预检与独立核对、预算／停止见[冻结协议](protocol.json)。从根目录依次运行`python experiments/exp_075_front_sampling_intervention/run.py prepare --out <新目录>`、`run`、`verify`、`check --out <同目录>`。prepare／后续阶段拒绝覆盖，冻结数据及失败保留；禁止追加种子、期限、源或未来留出。

正式结果见[实验报告](../../docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md)及[两级§29](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md#29-四字选样的有限闭环作用与剩余能力ng-214046补证)，记录`artifacts/runs/EXP_075/front_sampling_v1/`。本对象已经完成，原目录不重跑／覆盖；完整评分、各阶段计数、源／执行指纹和160块结果可复用。20全槽−四字认证减损，6全槽−保持认证增损和1小改善未认证全部保留。原合法见证仍较好但不作为在线目标，全槽30倍观测和既有留出／成本边界保持。

[analyze_position_variation.py](analyze_position_variation.py)只复用旧固定后级基函数和本实验保存历史，分开整段平均位置、持续变化和当前读出余项，再比较原point30同定义作用。依次`freeze`、`analyze`、`check --out <新分析目录>`，拒绝覆盖；独立标量导出、direct参照残差平方、极化Gram与块目标投影核对，不重跑任何学习或新合法均值读出。见[报告§7](../../docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md#7-全槽增损的平均位置持续变化只读补分析)，记录`artifacts/research/full_front_position_variation_20261014_v1/`。全部20／160保留，1块余项未认证及汇总计数补账单列；原实际路径／失败不改，连续差参照与在线能力分开。

[analyze_mean_learning_connection.py](analyze_mean_learning_connection.py)只读既有标量矩和保存低两Q22／真实请求，连接全槽输出前均值、两种连续输出目标及三角时间权重，检查旧连续门证书能否转移。依次`freeze`、`analyze`、`check --out <新分析目录>`；计数器后续版本补全五个加法核，已完成v1冻结源／结果／账目及81800漏项补账保存，不重跑。见[报告§8](../../docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md#8-全槽平均位置如何由真实请求形成以及固定相关仍缺什么)，记录`artifacts/research/full_front_mean_learning_20261014_v1/`；唯一获旧门保护位置的相关量只在另冻小标量协议中代数转移，其余新均值的固定统计不计算。

[analyze_fixed_mean_statistics.py](analyze_fixed_mean_statistics.py)针对已预定四坏均值补同状态连续全槽C／A／b与门保护，后级Q3／原高两固定，不取新合法格点或定义Q22请求。依次`freeze`、`analyze`、`check --out <新分析目录>`，拒绝覆盖；独立数字字分组、Fraction后级／四基函数、消元和目标区间核对，字级读出／掩码产品／归约完整计费。结果见[报告§9](../../docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md#9-四坏均值处的同状态连续相关与目标方向)，记录`artifacts/research/full_front_fixed_mean_statistics_20261014_v1/`。四方向2增损／2减损并认证，原20上下文保留；该判别已完成，不重跑或按分数增加位置／期限／目标精度。

[analyze_weighted_fixed_mean.py](analyze_weighted_fixed_mean.py)只补两个预定固定下降均值的原三角时间加权相关，复用原连续均值／后级／完整源序与目标梯度，不定义新Q22参照或传播政策。依次`freeze`、`analyze`、`check --out <新目录>`，拒绝覆盖；依赖源码SHA冻结，独立数字分组保留出现数及h的整数和，再用Fraction核对向量／区间。结果见[报告§10](../../docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md#10-两个固定下降案例的原三角时间权重)，记录`artifacts/research/full_front_weighted_fixed_mean_20261014_v1/`。一例固定时间权重已翻向、一例未翻向，两例实际请求差正投影认证；原20上下文保留，判别已完成，不默认扩成全部门／状态／量化分解。

[bound_q22_request_rounding.py](bound_q22_request_rounding.py)只用旧二例剩余投影／梯度区间、每窗半Q22 LSB及原零状态裁剪条件，给相同保存历史的请求取整支持界；不读源字／目标数组或计算PWL／门／学习。依次`freeze`、`analyze`、`check --out <新目录>`，拒绝覆盖；独立逐窗权重和／梯度位移盒角点及旧向量投影核对。见[报告§11](../../docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md#11-q22请求取整的同历史支持界)，记录`artifacts/research/full_front_q22_rounding_bound_20261014_v1/`。两例排除末次请求取整独自解释剩余正合项，保留取整前实际状态／门／Q3关系；不是去掉取整后重运行政策的反馈差界。

[analyze_moving_continuous.py](analyze_moving_continuous.py)只在625前缀/1/4原导出历史上计算连续前级读出、自己的连续门及原三角累计，后级Q3／高段／源／目标不变。依次`freeze`、`analyze`、`check --out <新目录>`，拒绝覆盖；独立Fraction导出与联合数字／导出分组保留h整数和，核对差和累计自身。结果见[报告§12](../../docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md#12-同实际导出历史的连续累计与自己的门)，记录`artifacts/research/full_front_moving_continuous_20261014_v1/`。差+0.465795与累计+0.105106均认证，当前Q3／末次Q22不是该比较翻向必要条件；原状态路径的量化、门／状态关联和完整MSE仍保留，没有传播连续政策。

[analyze_fixed_gate_history.py](analyze_fixed_gate_history.py)只在同一原历史计算均值连续门掩码G_F下的移动连续累计，复用原自己的门累计，核对指定先数值后门顺序。依次`freeze`、`analyze`、`check --out <新目录>`，拒绝覆盖；控制算术独立计费，Fraction联合数字—导出分组恢复固定／保持门相关及独立区间。结果见[报告§13](../../docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md#13-均值门保持下仍负门变化对同历史翻向不可省)，记录`artifacts/research/full_front_fixed_gate_history_20261014_v1/`。保持门累计−0.310255、门变化补+0.415361至原+0.105106，全部认证；门变化对该比较翻向不可省，不证明冻结真实反馈门改善MSE。

[analyze_gate_position_quadratic.py](analyze_gate_position_quadratic.py)只用一例旧标量H／平均位移／门向量／同目标梯度盒，保留完整二次项，判同历史删门位置的连续损失。依次`freeze`、`analyze`、`check --out <新目录>`，拒绝覆盖；独立初态／删项梯度与显式交叉多项式核对，不读源、状态、目标表或传播政策。见[报告§14](../../docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md#14-完整二次位置损失支持门向量与坏位置的关系)，记录`artifacts/research/full_front_gate_position_quadratic_20261014_v1/`。原+0.069079、删项−0.313531、完整门加入+0.382610码²均认证；κ̄−t是连续代数参照，非合法整数读出或冻结门反馈均值。
