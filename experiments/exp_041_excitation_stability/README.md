# EXP-041：数字激励与受约束稳定性

只读复用 EXP-039 的数字记录及完整聚合轨迹、EXP-040 的解析均值矩阵。计算两级连续数字学习输出的 Gram 矩阵及精确零空间，检查固定坐标子空间是否封闭，并计算相邻八窗口的解析转移乘积。另在共同单位系数上比较输入／dither 相同、历史模型不同的数字分布和相关量。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_041_excitation_stability.run artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_040/mean_v1 artifacts/runs/EXP_041/excitation_v2
python -m unittest discover -s tests -p test_window_excitation.py -v
```

输出目录必须尚不存在；复跑请使用新的 EXP_041 子目录。两份来源摘要、原始数字记录、完整聚合轨迹、EXP-040 分析及其源代码先检查摘要，结束后再次检查已读取的来源。在线算法、训练长度和原始产物均不变，没有 Cadence 调用。

输出包括六份窗口／连续块／分阶段方向分析、四份共同参考下的历史配对分析及 `summary.json`。矩阵顺序固定为后级四系数、前级四系数；预先固定全八方向、低段四方向 `{0,1,4,5}`、可能直接更新的五方向 `{0,1,2,4,5}`。全部相邻八窗口块分别位于训练或在线正弦阶段，不跨阶段、不筛选块。

精确有理数用于秩、零空间、转移乘积、Gram 正定下界和经验总变差。矩阵来自数字基函数的解析式；正定下界由精确 LDLᵀ 校验，没有拟合模拟灵敏度。单位系数的相关量利用合法域内 `P(r)=r` 独立计算。

`linearized_product_strictly_contracts` 只表示这个封闭坐标子空间的转移乘积无穷范数小于 1；还须查看 `all_open_cells_regular`。边界窗口只作固定掩码诊断。即使全部窗口正规，这仍不是共同邻域不变、未来持续激励或 Q22 总体收敛证书。

当前正式结果为 `excitation_v2`；早期 `excitation_v1` 有配对检查计数的元数据笔误，已由 v2 修正。详细解释见[推导](../../docs/theory/EXCITATION_AND_CONSTRAINED_STABILITY_V1.md)与[报告](../../docs/reports/experiments/EXP_041_EXCITATION_STABILITY_V1.md)。
