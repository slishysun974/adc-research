# EXP-076：均值影子第二门的最小有限反馈干预

仅取625前缀／1/4、full120、原完整Q22初态与[128,136)八块。第二低段门改由原全槽连续均值逐字影子计算，学习数值／其余门／Q3与Q22及四个前级请求保持原Gu候选，后级保持。均值依赖未来历史，额外影子读出及掩码存储单独计费；这是离线诊断，未提出在线算法。

从仓库根依次运行`python experiments/exp_076_fixed_mean_gate_intervention/run.py prepare --out <新目录>`，再运行`run`、`verify`、`check --out <同目录>`。协议在prepare中冻结并保存于本目录与运行目录；全部阶段拒绝覆盖，失败前缀／预算保留，原20案例及旧实验不重跑。

原Gu两窗预检与新路径Fraction／正式读出、原bank的未改坐标及独立第二请求先通过，再完整传播。独立标量数字—导出分组重建所有输出／请求／状态和影子门；主精确相位评分与独立八块bigint残差平方核对整数MSE及原目标区间。只到这一例原终点，不按成绩修改门／模型／期限／目标精度或使用6007／8009。

定义服务[两级§37](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md#37-门加权向量接到完整连续位置损失ng-213346补证)留下的关键缺口：同历史门向量改善连续位置，是否真的能经门源替换改善未来完整整数MSE。准备、实验、核对及报告完成分别记录。

本定义已经完成，原运行目录不重跑／覆盖。结果见[报告](../../docs/reports/experiments/EXP_076_FIXED_MEAN_GATE_INTERVENTION_V1.md)与[两级§38](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md#38-均值影子第二门的有限反馈收益ng-204046补证)：整数MSE3.333928→3.059912，候选−原full的整期／8块均认证改善，候选−保持整期认证改善但前两块增损、1小块未认证保留。全路径独立重建及所有预算通过，原未来均值知识、影子成本／30倍观察和线上能力界限保持。

## 真实平均位置与剩余见证差的只读桥接

[analyze_mean_position.py](analyze_mean_position.py)只取保存的低两输出前Q22均值，复用原全期二次矩／目标梯度／整数MSE，不导入平台、学习器、PWL或逐字评分。先`prepare --out <新目录>`，再`analyze`、`check --out <同目录>`，参照、准备重试累计、预算和停止先固定。

结果见[报告§7](../../docs/reports/experiments/EXP_076_FIXED_MEAN_GATE_INTERVENTION_V1.md#7-剩余见证差主要在连续平均位置合项改善未认证)及[两级§41](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md#41-均值影子剩余差距主要在平均位置ng-213346补证)。连续平均位置差1.071278为此分解的较大作用，实际−平均合项0.073134含变化与读出量化；门源使平均位置改善0.273092，合项变化跨0。准备v1来源键失败／v2重复读取超限保留，v3累计预算及独立核对通过，不追内部纯变化／量化或新八块矩。

## 固定影子门统计与输出目标的只读转移

[analyze_fixed_shadow_statistics.py](analyze_fixed_shadow_statistics.py)只读旧JSON矩／证书，固定同一GF，在新实际均值及旧W两处转移CF和真实连续L*梯度；先`prepare --out <新目录>`，再`analyze`、`check --out <同目录>`。不执行平台读出或学习。结果与边界见[报告§8](../../docs/reports/experiments/EXP_076_FIXED_MEAN_GATE_INTERVENTION_V1.md#8-固定影子门局部下降目标方程仍不一致)及[两级§42](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md#42-固定影子门的局部下降与目标方程差并存ng-202146补证)：两处局部下降、新均值非相关根，旧非零r另以原证书复用证明连续低两目标方程不同。两位置／W隐藏请求界、独立核对和预算已完成；原记录不重跑，不扩根或反馈政策。

## 保存请求的时间权重与旧矩充分性审查

[analyze_saved_history.py](analyze_saved_history.py)调用同对象保存的冻结分析，只取已存低两Q22／请求与旧JSON，不运行ADC。依次`prepare --out <新目录>`、`controls`、`analyze`、`check --out <同目录>`；已完成原记录不得覆盖或重复运行。执行源码、三次冻结／两次资格失败和累计预算在`artifacts/research/mean_shadow_history_audit_20261015_v1/`。结果与缺量见[报告§9](../../docs/reports/experiments/EXP_076_FIXED_MEAN_GATE_INTERVENTION_V1.md#9-真实请求的三角累计与旧统计的可复用边界)及[两级§43](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md#43-真实请求恢复新均值旧汇总不足以分开新均值的时间与状态作用ng-213346补证)。旧κr固定统计可复用，新均值中心化时间／状态分离仍缺两个加权关系；明确后停止，不自动重放源字或补全矩。

## 新均值时间／状态加权量的最小补证

[analyze_history_contractions.py](analyze_history_contractions.py)只复用保存基函数、GF、原dither标记和新路径Q22，依次`prepare --out <新目录>`、`controls`、`analyze`、`check --out <同目录>`，协议先冻结且拒绝覆盖。没有新PWL／门／请求执行／学习或评分。结果见[报告§10](../../docs/reports/experiments/EXP_076_FIXED_MEAN_GATE_INTERVENTION_V1.md#10-两个加权量补齐时间权重为本例累计削弱的较大作用)及[两级§44](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md#44-新均值参照下时间权重主导固定方向到真实累计的削弱ng-213346补证)；记录`artifacts/research/mean_shadow_time_state_contractions_20261015_v1/`。两量已完成且时间主导该有限请求削弱，原记录不重跑，不扩全矩或强拆微小量化合项。

## 给定剩余方向所需信息的只读判别

[analyze_direction_information.py](analyze_direction_information.py)只用旧JSON标量，核查新平均→已有W方向所需的目标投影阈值、原正弦包含和粗q1放松范围。先`prepare --out <新目录>`，再`controls`、`main`、`independent --out <同目录>`；已完成记录`artifacts/research/mean_shadow_direction_information_20261015_v1/`不重跑／覆盖。结果及全部计数见[报告§11](../../docs/reports/experiments/EXP_076_FIXED_MEAN_GATE_INTERVENTION_V1.md#11-已有改善方向的目标投影阈值粗判决精算仍不足)。没有新数组／目标表／读出／评分／学习；给定方向的条件评价不等于发现、合法整数输出或同初态线上达到。

## 去相关目标矩与给定方向的最小条件核查

[analyze_instrument_direction.py](analyze_instrument_direction.py)只读旧JSON的门数量、AF、H及同一既有方向，依次`prepare --out <新目录>`、`controls`、`analyze`、`check --out <同目录>`，拒绝覆盖。不重建字／PWL／门／目标／路径。固定GF两工具量的方向残余已认证，实际独立性及ℓ=0未认证；有界矩控制未跨原改善阈值。见[报告§12](../../docs/reports/experiments/EXP_076_FIXED_MEAN_GATE_INTERVENTION_V1.md#12-独立性门条件与给定方向的相关工具量遗漏)／[Dither§12](../../docs/theory/DITHER_INFORMATION_AND_STOCHASTIC_UPDATE_AUDIT_V1.md#12-去相关目标项消去仍须方向信息条件ng-012122补证)。冻结记录`artifacts/research/mean_shadow_instrument_direction_20261015_v1/`，条件缺口明确后不扩其他方向或紧界。
