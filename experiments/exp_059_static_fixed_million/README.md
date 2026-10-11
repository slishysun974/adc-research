# EXP-059：静态定点逐项百万学习、状态均值与波动

接续EXP-058的局部合同，执行已批准计划T2—T5的长期静态控制。独立理论扩展复用静态两级／定点文档，实验编号不充当理论成果编号。前两级flash/CDAC，末级8位TI-SAR；在线只用数字码、dither和状态。

运行前冻结 [专用协议](protocol.json)，并复制EXP-057协议。原五条件、五种子、步长、学习预算和检查点不变。浮点原路径逐状态核对，三个新层次依次加入Q3、Q1.10、Q22。每层均同时评分连续和最终整数输出；整数输出不反馈学习。差值是顺序加入因素的条件增量。

入口（仓库根目录，PowerShell 7）：

```powershell
$env:PYTHONPATH='src;.'
./experiments/exp_059_static_fixed_million/run.ps1 -Output D:/ADC/artifacts/runs/EXP_059/preflight_v1 -Preflight
python -m experiments.exp_059_static_fixed_million.verify D:/ADC/artifacts/runs/EXP_059/preflight_v1
./experiments/exp_059_static_fixed_million/run.ps1 -Output D:/ADC/artifacts/runs/EXP_059/million_v1 -PreflightPath D:/ADC/artifacts/runs/EXP_059/preflight_v1
python -m experiments.exp_059_static_fixed_million.verify D:/ADC/artifacts/runs/EXP_059/million_v1
python -m experiments.exp_059_static_fixed_million.analyze D:/ADC/artifacts/runs/EXP_059/million_v1 --prepare
./experiments/exp_059_static_fixed_million/score.ps1 -Output D:/ADC/artifacts/runs/EXP_059/million_v1
python -m experiments.exp_059_static_fixed_million.analyze D:/ADC/artifacts/runs/EXP_059/million_v1
```

目录拒绝覆盖；预检源码指纹不变才能训练。C#仅为实验局部加速，模拟源复用冻结EXP-057，其数字函数不接收输入真值。独立Fraction实现核对每个预定探针的读出、门、基函数、相关和与提交；原平台和原定点校正器另核对。150条新定点路径不声称逐次独立重放全部长记录。每条point路径仅生成选中的静态观测，未生成的转换槽位报告为推定时长；没有动态历史。

固定评价矩阵的均值／协方差恒等式使用完整后半段前级有效状态；逐状态直接核对和两级共同变化评分使用预定200状态子集。有限增量恒等式核对边界项，不检验总体稳态或白噪声。所有种子、失败和裁剪保留，不以性能改善作为实施通过门。原生产Gu／平台／RTL不修改，不扩展主辅失配、动态或新算法。
