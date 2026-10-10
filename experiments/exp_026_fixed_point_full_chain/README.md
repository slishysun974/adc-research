# EXP-026：独立辅路全链路定点对照

沿用 EXP-025 的两条合成三次主路、独立线性辅路、四个训练种子、逐转换更新、五字段数字观测、验证与留出输入。比较浮点 Gu、将其终点系数量化后仅运行 Q1.10／Q3 校正、以及从单位系数冷启动的 22/26 小数位定点更新累加器。所有最终码采用同一最近偶数舍入和 `[0,4095]` 裁剪规则。22/26 位累加器、舍入和饱和属于候选实现，不是论文公开的芯片寄存器规格。

从仓库根目录运行：

```powershell
$env:PYTHONPATH='src'
python experiments/exp_026_fixed_point_full_chain/run.py --run-id frozen_v1
```

`--case` 与 `--seed` 可限制一次探索运行；正式结果应使用配置中的两条曲线与四个种子。程序拒绝覆盖已有输出，结果写入 `artifacts/runs/EXP_026/<run-id>/summary.json`。

正式解释见[EXP-026 报告](../../docs/reports/experiments/EXP_026_FIXED_POINT_FULL_CHAIN_V1.md)。
