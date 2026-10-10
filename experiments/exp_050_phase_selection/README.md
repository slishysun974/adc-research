# EXP-050：同四点预算的相位选择

沿EXP-049正常闭环中已出现的有限选样损失，只改变四路窗口候选的相位调度。固定相位0、每窗口+1的轮换、明确32位状态的伪随机相位均每路选一条，共4条，乘积乘30；Gu门、步长、位宽、PWL及窗口提交不改。完整120条只作诊断参照。

[协议](protocol.json)在计算前固定3组新输入／dither种子及新正弦频点。24格条件共享相同数字记录作方法配对，全部从单位系数开始。两条三次曲线已在EXP-049中使用，本轮是新种子／频率验证，不称未知函数类别盲测。每种候选独立按预定门筛选，不挑最好种子或终点。

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -p test_window_phase_selection.py -v
python -m experiments.exp_050_phase_selection.run artifacts/runs/EXP_050/phases_v1
python -m experiments.exp_050_phase_selection.verify artifacts/runs/EXP_050/phases_v1
python -m experiments.exp_050_phase_selection.common_endpoint_forks artifacts/runs/EXP_050/phases_v1
$env:MPLCONFIGDIR='D:\ADC\artifacts\tooling\matplotlib_config'
python -m experiments.exp_050_phase_selection.plot_results artifacts/runs/EXP_050/phases_v1
python -m experiments.exp_050_phase_selection.finalize artifacts/runs/EXP_050/phases_v1
```

主入口拒绝覆盖原目录，失败和过载保留。每格保存人工模拟／数字记录、96条候选路径的实际相位／系数／相关和与最终码。协议、原来源和新源码摘要固定。独立核对从按位参考实现重算伪随机状态，再从独立标量PWL、门、整数请求与八状态核对全部路径。

轮换新增5位状态；伪随机新增32位以及移位异或和常数模30逻辑，不假设已有免费随机源。共享同步／广播仍是候选合同，没有新RTL或面积／时序／功耗证明。[条件推导](../../docs/theory/FOUR_POINT_PHASE_SELECTION_CONDITIONS_V1.md)区分理想独立均匀相位与实际确定调度，后者不能自动称条件无偏。

`common_endpoint_forks.py`是主结果完成后的事后诊断：全24格三种四点方法从同一固定相位训练终点进入正弦，保留各自选择状态。它不改变预定筛选结果；固定分支复现原码，全部控制码与八状态另由独立标量核对。结果见[报告](../../docs/reports/experiments/EXP_050_PHASE_SELECTION_V1.md)。图需实际查看。
