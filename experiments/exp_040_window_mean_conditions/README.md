# EXP-040：窗口均值、门控余量与相位条件

只读复用 EXP-039 的六组原始记录与完整聚合轨迹，不改变算法、曲线、训练长度或运行产物。每个窗口在旧导出系数上形成未舍入的解析均值与灵敏度，检查门／选择段余量，独立重算 Q3 相关量，并枚举 30 个相位的请求。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_040_window_mean_conditions.run artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_040/mean_v1
python -m experiments.exp_040_window_mean_conditions.audit_phase_reliability artifacts/runs/EXP_040/mean_v1
python -m unittest discover -s tests -p test_window_mean_map.py -v
```

输入必须先完成 EXP-039。读取前检查来源源码、原始数字记录和方法产物摘要；文件只读。输出六份窗口分析 JSON 和 `summary.json`，数值以有理数字符串保存，矩阵状态顺序为“第二级四系数、第一级四系数”。结果中的 `full_eight_state_contraction_certified_windows` 只指未舍入参考均值映射在开邻域内的局部充分条件，不能解释为 Q22 算法的总体收敛证明。

分析包括全部 960 个窗口及 115200 次已存在转换；它们同时含训练与持续在线正弦两阶段。相位重放均固定在完整聚合路径的窗口开始系数，避免把选择统计量和不同训练状态混合。输出含有限记录的相位方差、请求反号、整数均值误差界、保护门数及实际有限变化核对。

相位可靠性辅助脚本只读上述结果，核对非零相关均值的单侧二阶矩方向界并保存 `phase_reliability.json`；条件概率只来自一个假设的均匀独立相位选择，不解释为真实芯片失效概率。它不修改源实验，也不运行新的随机相位算法。

推导见[理论记录](../../docs/theory/WINDOW_MEAN_AND_GATE_MARGIN_CONDITIONS_V1.md)，结果见[报告](../../docs/reports/experiments/EXP_040_WINDOW_MEAN_CONDITIONS_V1.md)。矩阵按数字基函数解析推导，不从 ADC 物理模型拟合，也不宣称有限记录相关量是真实损失梯度。
