# EXP-042：受约束相关零点与门控跳变

固定两级第三、第四段系数为单位值，精确求解前两段的有限记录相关方程。第一门恒开，其零点直线用于消元；第二门的全部交点单独计算，区分真正零点与异号跳变。先解后级，再对每个解求前级。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_042_correlation_roots.run artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_042/roots_v4
$env:MPLCONFIGDIR='D:\ADC\artifacts\tooling\matplotlib_config'
python -m experiments.exp_042_correlation_roots.plot_roots artifacts/runs/EXP_042/roots_v4
python -m unittest discover -s tests -p test_gated_correlation_roots.py -v
python -m unittest discover -s tests -p test_constrained_mean_root.py -v
```

输出目录必须尚不存在；重复求解请使用新的 EXP_042 子目录。当前正式产物是 `roots_v4`，早期目录属于开发过程。`probe.py` 为初始数字记录探查，不替代正式入口的来源摘要检查和完整证据。

读取 EXP-039 原始记录和其来源代码前检查 SHA-256，结束后复核来源不变。只读取数字字段进入求根与解析均值；理想整数码仅传入独立离线评分及目标相关量分解。没有 Cadence 调用、模拟重跑、追加训练、更新规则修改或 RTL 修改。

每组前 96 个窗口（11520 次转换）用于求根；剩余 32 个随机输入训练窗口和原 32 个在线正弦窗口分别固定根检验。本次求根不使用后两部分，但它们已在此前实验中被研究，不能称为全项目未见过的盲测。

系数顺序为后级四项、前级四项，合法连续域为每项严格在 `(0,2)`。全部孤立解保留；零区间或主方程退化显式报告。源记录的高段在原轨迹中关闭，不意味着求出的根仍保持它们关闭，因此另外检查全部八相关量和高段门。

输出六份完整扫描／根分析、`summary.json`、PNG/SVG 图及最终验收记录。扫描保存每个开区间的精确相关函数、跳点左右极限及 `≥` 值；证明只针对这个受约束问题，不能推断释放高段后也无解。

稳定分析保存全空间正规性与固定高段后子空间正规性。只有各门、选择段、合法域在整个盒中保持，且解析转移范数的统一上界小于 1，才给同一经验分布的局部收缩结论。高段等值如果沿自由方向恒成立，则按 `≥` 保持开门；不能把这种子空间结果称为全空间 Jacobian。

`virtual_120_conversion_q22_request` 把完整拟合／检验记录的冻结整数相关均值按 120 转换的步长换算为请求，仅是均值诊断。它不是实际 120 行的相关和，也不是 Q22 闭环平衡证书。离线频谱使用同一最终整数码、3840 点相干正弦、全速 3 GS/s 与第 67 基波；为浮点评估，未数值认证。

推导见[理论记录](../../docs/theory/CONSTRAINED_CORRELATION_ROOTS_AND_JUMPS_V1.md)，结论见[实验报告](../../docs/reports/experiments/EXP_042_CORRELATION_ROOTS_V1.md)。
