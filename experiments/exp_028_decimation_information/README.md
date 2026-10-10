# EXP-028：抽取边界的信息与门限等值审计

运行：在仓库根目录设置 `PYTHONPATH=src` 后执行 `python -m experiments.exp_028_decimation_information.run`。结果写入 `artifacts/runs/EXP_028/frozen_v1_20261003/summary.json`。脚本读取 EXP-025 已冻结的曲线 A、训练序列与候选架构，但把两级数字系数保持为 1，只统计前 4096 次本地学习输出恰好等于高段下限的次数；另打印两个无需模拟模型的两点信息损失反例。

结果摘要见[实验报告](../../docs/reports/experiments/EXP_028_DECIMATION_INFORMATION_V1.md)，证明和取证要求见[抽取边界的信息审计](../../docs/stages/03_gu_baseline/DECIMATION_INFORMATION_REQUIREMENTS_V1.md)。原文式 (7) 用 `≥`，Fig. 10 用 `>`；本实验计算冻结系数时等值样本对相关和的贡献，没有重跑另一种门限下的在线训练，也不识别芯片抽取器。它不能用于修改 EXP-025 的原始结果。
