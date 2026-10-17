# EXP-056：百万量级静态单斜率统计检查

按[接续计划](../../docs/reports/MILLION_SAMPLE_PLAN_HISTORY_2026-10-10.md)先执行静态线性与量化对照，尚不进入非线性、两级、定点或动态。

[协议](protocol.json)在统计结果产生前冻结。每条四点路径100万学习观测、25万提交、推定3000万转换时长；完整累计同转换时长学习3000万条，并保留约100万条学习观测的检查点。5个种子、宽／窄／直流输入、理想／floor后端、单位／偏差增益，共120条标量控制路径。

仅生成静态独立学习观测；推定转换时长不等于执行了完整ADC平台。单斜率更新只使用观测raw与已知dither，输入与真实增益仅在后台生成和离线评分中出现。10位后端、步长和窗口是明示控制条件，不称Gu芯片事实。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_056_million_scalar_statistics.run artifacts/runs/EXP_056/million_v1
python -m experiments.exp_056_million_scalar_statistics.verify artifacts/runs/EXP_056/million_v1
python -m experiments.exp_056_million_scalar_statistics.plot artifacts/runs/EXP_056/million_v1
```

输出保存全部逐窗口状态、相关和、后段十块统计和预定检查点的冻结／在线相干正弦评分。先核对原LMS与SAR端点，再运行长记录；系数越界、过载或加速数值条件失效时停止并保留产物。

本次正式运行和独立核对完成，全部120条统计门及362项回归通过。见[研究报告](../../docs/reports/experiments/EXP_056_MILLION_SCALAR_STATISTICS_V1.md)。原源码冻结仍匹配；`verify.py`和`plot.py`为后续只读核对／展示入口，不改变已冻结训练结果。
