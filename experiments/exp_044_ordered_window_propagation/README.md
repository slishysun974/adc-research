# EXP-044：原窗口次序、高段请求与状态范围

复用EXP-039六组各160个窗口。原Gu保持八状态、Q22／Q1.10／Q3、`≥`门和120转换末尾提交。完整原轨迹逐窗核对保存结果；固定高段与交换相邻训练窗口是离线控制，不是新的Gu实现或重新模拟的输入历史。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_044_ordered_window_propagation.run artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_043/mean_v4 artifacts/runs/EXP_044/ordered_v1
python -m experiments.exp_044_ordered_window_propagation.analyze_gate_support artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_044/ordered_v1
$env:MPLCONFIGDIR='D:\ADC\artifacts\tooling\matplotlib_config'
python -m experiments.exp_044_ordered_window_propagation.plot_results artifacts/runs/EXP_044/ordered_v1
python -m experiments.exp_044_ordered_window_propagation.finalize artifacts/runs/EXP_044/ordered_v1
```

输出目录必须尚不存在，正式产物为`ordered_v1`；复跑使用新的EXP_044子目录。图生成后须实际查看；验收脚本不代替视觉检查。

初始八系数全部为单位值，状态范围固定为每坐标±1／±2048 Q22 LSB；128窗口训练、32窗口在线正弦的长度不变。两条对角角点与原中心轨迹独立回放，范围证明仍基于全部初始矩形的归纳包含。

顺序检查采用每组64对相邻训练窗口，正／反序同一起点，检查八个功能状态及同一后续窗口的冻结最终码。完整交换控制只交换训练窗口，正弦仍按原序评分。没有重排窗口内字段，也不将数字控制解释为电路输入重排。

高段控制在每次提交后把两级第三／第四状态恢复单位值，保存原请求；中间评分用原Gu低段状态与单位高段，不提交。码差按这条中间记录分成直接高段与间接低段历史项，逐转换精确相加，频谱差不作同样拆分。

`analyze_gate_support.py`按原每窗口导出值逐样本分类第三门，检查其自身基函数是否为零；两个相关和相加与原值一致，160次舍入的总残差另记录。`probe_gates.py`为开发读取，不替代正式验收。

理想目标只进入离线评分。源记录／依赖代码、结果摘要与源码指纹核对；无新模拟样本、Cadence、记录延长、原Gu或RTL修改。

见[推导](../../docs/theory/ORDERED_WINDOW_STATE_AND_HIGH_SLOPE_PROPAGATION_V1.md)及[报告](../../docs/reports/experiments/EXP_044_ORDERED_WINDOW_PROPAGATION_V1.md)。
