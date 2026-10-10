# EXP-055：模型与dither统计基础核查

独立检查静态两级信号链／线性逆增益、两相静态退化、Gu两段原理级正向控制，以及正确均值更新仍有有限样本波动的标量控制。先核查模型和文献，不修改在线算法。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_055_model_dither_audit.run artifacts/runs/EXP_055/audit_v1
```

输出目录必须不存在。500万条原理样本没有量化，末段连续延伸与原文字面系数舍入差均明示；不宣称Fig.6逐字或芯片复现。芯片保真门仍未通过。

[固定协议](protocol.json)、[结果报告](../../docs/reports/experiments/EXP_055_MODEL_DITHER_AUDIT_V1.md)、[信息及随机更新推导](../../docs/theory/DITHER_INFORMATION_AND_STOCHASTIC_UPDATE_AUDIT_V1.md)。
