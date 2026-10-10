# EXP-037：有理数静态链与 Q22 在线码范围

用明确的人工扫描验证从原始有理数电压到数字观测、在线累加器和最终整数码的包含关系。复用 EXP-036 的扫描公式与误差合同、EXP-032 的定点数字配置；不获取电路数据，也不修改在线校准规则。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_037_rational_static_online.run artifacts/runs/EXP_037/rational_v1
```

运行产物仅写本实验的 `artifacts/runs/EXP_037/`，生成 `synthetic/` 来源包、逐转换 `records.json` 和带源码／数据摘要的 `summary.json`。来源包在范围计算中只读。128 次转换、两条固定人工条件轨迹的判决／最终码／八状态逐次核对；另检查 771 组边界点。输入序列、dither 和初始状态在脚本中预先固定。

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -p test_rational_static_reachability.py -v
```

结果、边界反例及物理／频谱限制见[报告](../../docs/reports/experiments/EXP_037_RATIONAL_STATIC_ONLINE_V1.md)。精确端点类型检查不能认证任意外部回调；外部范围的内部算术与物理覆盖仍须审查。没有真实四路时序或数值认证的频谱结论。
