# EXP-069：同一数字流下Gu学习率与有限收敛行为

接续D-115及现有计划§13.4，检验标量学习率结论在两级Q3／Q1.10／Q22候选中能保留多少。它是新的数字闭环学习实验，按EXP-068之后编号；上一轮标量解析核对保留原位置，不改写为新ADC实验或搬动冻结资料。

只改变两级全部步长的共同倍率1/4、1/2、1、2，门、选样、分段、数据精度、初值和120槽同时提交保持EXP-062。原始观测不受数字校正系数影响，因此复用EXP-062三个已见静态模型、五个原种子、原同输入正弦的完整数字流；每档形成自己的旧状态读出、门和后续更新，绝不沿用原算法的系数／门轨迹。真实输入及模拟参数仅进入离线评分和原平台探针。

[协议](protocol.json)先冻结预算、全部倍率、指标、经验判据和失败保留方式。32窗口预检包括倍率1，与原EXP-062完整前缀精确一致；其余倍率逐项对正式Q22更新及独立有理数核对。预检同源通过后，三新倍率各运行两方法、三模型、五种子，共90条7864320槽数字闭环路径；倍率1的30条结果只读复用。完整累计每级多30倍学习量，绝不称同成本比较。原ADC观测流不重生，但新学习量和新输出均计入。

```powershell
$env:PYTHONPATH='src;.'
pwsh -File experiments/exp_069_gu_learning_rate/run.ps1 -Output D:/ADC/artifacts/runs/EXP_069/preflight_v1 -Preflight
python -m experiments.exp_069_gu_learning_rate.verify artifacts/runs/EXP_069/preflight_v1
pwsh -File experiments/exp_069_gu_learning_rate/run.ps1 -Output D:/ADC/artifacts/runs/EXP_069/background_v1 -PreflightPath D:/ADC/artifacts/runs/EXP_069/preflight_v1
python -m experiments.exp_069_gu_learning_rate.verify artifacts/runs/EXP_069/background_v1
python -m experiments.exp_069_gu_learning_rate.analyze artifacts/runs/EXP_069/background_v1
```

保存每次转换各档最终整数码、每窗八个Q22整数、逐块门／基函数／共同支持／相关和、零请求／非零和舍零／隐藏改变／导出改变及饱和。原单位输出、倍率1状态和输出由冻结EXP-062文件承担，使用数据先核对原交付指纹，前后保持。新目录拒绝覆盖，失败与全部种子保留。

对应理论仍在原[标量学习率§7—14](../../docs/theory/MILLION_SAMPLE_SCALAR_MEAN_NOISE_AND_QUANTIZATION_V1.md)及原两级／定点文档；本实验不证明一般八状态平稳分布、芯片实际步长或独立曲线留出，不设计新算法。实验报告保存于既有`docs/reports/experiments/`，原始结果在`artifacts/runs/EXP_069/`。
