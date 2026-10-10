# 主辅、阈值与四路时序的解析核算

这组脚本检查有公开电路连接依据的条件性推导。没有 Cadence 调用，不生成芯片曲线，不报告 ADC 性能改善。

```powershell
python -m experiments.mainline_physical_mechanisms.check_derivations
```

输出固定在 `artifacts/research/physical_evidence_20261009/mechanism_checks.json`。核对两相一阶模型的展开与历史依赖、非线性辅路的理想逐阈值修调，以及四路同相位点抽取对周期状态的覆盖。脚本中的函数和状态系数均是声明的解析示例，不是从论文识别出的真实电路参数。

推导见[理论记录](../../docs/theory/DUAL_PATH_EFFECTIVE_THRESHOLDS_AND_PHASES_V1.md)，研究判断见[本轮报告](../../docs/reports/MAINLINE_PHYSICAL_MECHANISMS_2026-10-09.md)。
