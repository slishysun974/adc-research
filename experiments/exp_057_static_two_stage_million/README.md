# EXP-057：静态两级及平滑非线性的百万量级检查

接续[百万量级计划](../../docs/reports/MILLION_SAMPLE_PLAN_HISTORY_2026-10-10.md)第3步。[协议](protocol.json)在训练前冻结，原Gu核心、平台及RTL保持。

5种子、5种人工静态条件、理想／8位SAR后端、四点／完整累计，共100条路径。四点每级100万实际观测、25万提交、推定3000万转换时长；完整累计每级1000080观测、8334提交、1000080转换时长。相同转换时长只比较预定2500／8334窗口，两个最终终点不是同物理时间。

编译的C#实现分别处理模拟信号链和数字校正／门控更新。量化路径学习器只使用原数字码和dither标签；连续后端属于离线控制，没有向生产五字段接口增加实数信号。每段分别记录门、基函数支持及二者同时出现的次数。

使用PowerShell编译，不需要额外工具安装。输出目录必须是新的路径，下面示例中的正式运行已经存在，不能重复覆盖。

```powershell
$env:PYTHONPATH='src'
$preflightDir='D:\ADC\artifacts\runs\EXP_057\replay_preflight_v1'
$runDir='D:\ADC\artifacts\runs\EXP_057\replay_v1'
New-Item -ItemType Directory -Path $preflightDir -ErrorAction Stop | Out-Null
Copy-Item -LiteralPath experiments/exp_057_static_two_stage_million/protocol.json -Destination (Join-Path $preflightDir 'protocol.json')
& experiments/exp_057_static_two_stage_million/native.ps1 -Output $preflightDir -Preflight
python -m experiments.exp_057_static_two_stage_million.verify $preflightDir
# 正式入口只接受成功预检且来源哈希保持的源码。
& experiments/exp_057_static_two_stage_million/run.ps1 -Output $runDir -PreflightPath $preflightDir
python -m experiments.exp_057_static_two_stage_million.verify $runDir
python -m experiments.exp_057_static_two_stage_million.analyze $runDir
python -m experiments.exp_057_static_two_stage_million.audit_support_bound $runDir
python -m experiments.exp_057_static_two_stage_million.summarize $runDir
```

保留全部逐窗口状态、预定检查点及其前32窗口的原始模拟／数字观测和提交，便于原程序核对。独立验证覆盖预定探针，没有宣称重放全部5000万模拟样本。

本轮结果与下一项见[研究报告](../../docs/reports/experiments/EXP_057_STATIC_TWO_STAGE_MILLION_V1.md)。
