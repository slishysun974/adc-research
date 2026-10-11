# EXP-061：静态主辅失配的必要长期配对

执行[已批准计划§5](../../docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md)，接续EXP-060。八个原静态条件、五新种子、Q3／Q1.10／Q22单层与原百万实际学习预算，共80条路径。30条匹配路径仅作新种子的同源参考。前两级flash/CDAC，末级8位TI-SAR；不改原门、步长、位宽或训练终点。

[专用协议](protocol.json)冻结同状态观测、同观测状态及交互的四格评分、学习相关量读出／选门恒等式和原有限状态矩诊断，推导见[主辅理论§12](../../docs/theory/DUAL_PATH_EFFECTIVE_THRESHOLDS_AND_PHASES_V1.md)。当前辅路参数为原声明机制假设，不是芯片提取。静态四点仅生成选中观测，推定转换时长不能称全部真实执行转换；动态必须另行逐转换推进历史。

仓库根目录执行（PowerShell 7）：

```powershell
$env:PYTHONPATH='src;.'
$env:OPENBLAS_NUM_THREADS='1'
./experiments/exp_061_static_auxiliary_million/run.ps1 -Output D:/ADC/artifacts/runs/EXP_061/preflight_v1 -Preflight
python -m experiments.exp_061_static_auxiliary_million.verify artifacts/runs/EXP_061/preflight_v1
./experiments/exp_061_static_auxiliary_million/run.ps1 -Output D:/ADC/artifacts/runs/EXP_061/million_v1 -PreflightPath D:/ADC/artifacts/runs/EXP_061/preflight_v1
python -m experiments.exp_061_static_auxiliary_million.verify artifacts/runs/EXP_061/million_v1
python -m experiments.exp_061_static_auxiliary_million.analyze artifacts/runs/EXP_061/million_v1 --prepare
./experiments/exp_061_static_auxiliary_million/score.ps1 -Output D:/ADC/artifacts/runs/EXP_061/million_v1
python -m experiments.exp_061_static_auxiliary_million.analyze artifacts/runs/EXP_061/million_v1
```

加速物理源为本实验C#函数，数字读出／更新复用冻结EXP-059；新加速源先逐条对原平台与独立有理数数字合同核对。预检全路径重放，长训练按预定40窗口／路径核对；全部检查点冻结／继续在线频谱码另作独立重放。保存全部后半段状态、十块统计、门／基函数／共同支持及同状态后级残差；不把固定评价矩阵或四格平方交叉称作八状态因果分解。各目录拒绝覆盖，源码须与预检一致，失败保留。原平台、在线Gu与RTL保持。
