# EXP-058：静态码域与定点合同预检

本实验交付已批准静态定点计划 T1／T2 的范围推导、手算边界和独立短控制。它与 EXP-057 百万浮点训练不同：本次仅固定状态评分和短窗口逐状态核对，不估计长期性能或选算法。

推导见 [静态两级支持](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md)及 [有限字长合同](../../docs/theory/STATIC_FIXED_POINT_ERROR_AND_LEARNING_V1.md)。协议在执行前保存于 [protocol.json](protocol.json)。精确数字实现独立于平台和 Gu 正式模块；模拟／理想输入只在实验入口用于生成和离线验证。

```powershell
$env:PYTHONPATH = 'src;.'
python experiments/exp_058_static_fixed_preflight/run.py artifacts/runs/EXP_058/preflight_v2
```

输出目录必须不存在。运行保存协议、源码指纹、逐组支持／误差统计、全部短路径状态和失败记录。运行后报告见 [EXP-058](../../docs/reports/experiments/EXP_058_STATIC_FIXED_PREFLIGHT_V1.md)。冻结历史 EXP-057、原 Gu／平台和 RTL 不修改。
