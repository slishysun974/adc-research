# EXP-072：正常状态位置与后续更新的有限干预

D-136授权内的机制诊断。固定平滑场景、原五种子、两倍率、前缀120—127块与评价128—135块。原四分支／预算见[协议](protocol.json)，有限反馈和后续只读分析见[报告](../../docs/reports/experiments/EXP_072_NORMAL_STATE_INTERVENTION_V1.md)。

原冻结轨迹入口为`python experiments/exp_072_normal_state_intervention/run.py prepare`，继而`run`与`verify`。已存在目录时prepare拒绝覆盖；原运行已验收，当前接续不需重跑。

保存路径只读入口为[analyze.py](analyze.py)。从仓库根运行`python experiments/exp_072_normal_state_intervention/analyze.py prepare --out artifacts/research/normal_future_readout_20261013_v1`，继而以相同`--out`运行`analyze`；已有目录拒绝覆盖。原正式结果保存在上述目录，初始执行源码、独立核对／修正与逐配对数据全部归档；当前入口只修正请求计数标签，数值函数不变。混合bank读出没有独立更新，正弦目标外界有附加输入条件，不能当作新算法或一般在线保证。
