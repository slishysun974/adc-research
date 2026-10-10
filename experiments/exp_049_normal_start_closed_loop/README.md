# EXP-049：单位初值实际闭环与预先固定留出

先只读回放EXP-039六组记录的完整／点抽取路径，逐窗口核对旧状态、新状态、两级请求和原正弦全部整数码。前级实际Q3门下将相关量精确分成目标信号项与码误差项，再加入一次舍入和饱和差，复原实际Q22变化。理想码仅在独立离线入口进入分析。

随后按[固定协议](protocol.json)运行八组新的人工条件：两组新三次曲线参数、均匀／中心集中训练输入、复位／保持历史。种子、训练长度、正弦输入及两相参数在运行前固定，不因结果更换。每组两种方法均从单位系数开始，训练后另报告冻结终点与持续在线正弦。检查点使用相同正弦记录作离线诊断，不据其结果调整算法。

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -p test_window_trajectory_diagnostics.py -v
python -m experiments.exp_049_normal_start_closed_loop.run artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_049/closed_loop_v1
python -m experiments.exp_049_normal_start_closed_loop.verify_and_propagate artifacts/runs/EXP_049/closed_loop_v1 artifacts/runs/EXP_039/window_v1
$env:MPLCONFIGDIR='D:\ADC\artifacts\tooling\matplotlib_config'
python -m experiments.exp_049_normal_start_closed_loop.plot_results artifacts/runs/EXP_049/closed_loop_v1
python -m experiments.exp_049_normal_start_closed_loop.finalize artifacts/runs/EXP_049/closed_loop_v1
```

入口拒绝覆盖已有目录。可用`--section prior`或`--section holdout`分段复跑，另选新输出目录。协议摘要、原来源摘要和结果均保存。保留所有失败和过载；只称新的合成条件留出，不称项目盲测、芯片验证或新算法比较。

同窗口旧／新系数冻结评分仅用于检查一次更新的局部输出影响，不将更新后的状态重新提交，也不代表之后的闭环因果损失或正确梯度。后级先换、前级后换的误差平方和差满足精确相加关系，分项取决于此顺序。FFT为普通浮点评分。

独立核对另从整数商／余数实现最近偶数舍入，不调用原PWL／门／更新器，重算全部窗口的两级请求及八状态；正弦末级码逐条核对。整段正弦的训练终点／当前前后级四组合保留交互误差，不把SNDR差直接相加。图必须实际查看。结果见[报告](../../docs/reports/experiments/EXP_049_NORMAL_START_CLOSED_LOOP_V1.md)，有限记录恒等式见[推导](../../docs/theory/NORMAL_START_WINDOW_ATTRIBUTION_AND_CODE_EFFECTS_V1.md)。
