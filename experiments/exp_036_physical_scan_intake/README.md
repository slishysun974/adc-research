# EXP-036：三路静态扫描数据的接入验证

验证外部扫描资料如何进入现有三路范围传播。输入配置由生成的 `manifest.json` 固定：两个**人工合成**条件，三条平滑三次传输，126 条建立记录和 120 条独立留出。它不获取 Cadence 数据，不改变在线校准或 RTL。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_036_physical_scan_intake.run artifacts/runs/EXP_036/scan_intake_v1
python -m adc_research.evaluation.physical_scan_package artifacts/runs/EXP_036/scan_intake_v1/synthetic/manifest.json --output artifacts/runs/EXP_036/scan_intake_v1/cli_audit.json
python -m unittest discover -s tests -v
```

验收器检查三路／条件／单位／文件摘要／独立留出及全域斜率的声明。网格范围使用原始字符串的精确有理数，先计入输入电压误差，再建立连续范围；只在连接现有浮点传播器时把端点向外转换。物理前提需要独立审查，报告不会自动认证其真实性。

实验另将两个条件的范围取并集，与独立逐样本 stage／SAR 平台核对 256 条判决和冻结单位系数最终码。特意注入一条范围明确分离和一条仅部分重叠的留出，分别报告 `contradiction` 与 `inconclusive`，均不能接入后续传播。

输出包含 `summary.json`、`intake_audit.json`、`static_connection.json`、正向包 `synthetic/` 和两个负向包。全部文件写 ADC 的 EXP-036 产物目录，真实来源数据包由单独只读入口处理。详细字段见[数据协议](../../docs/stages/02_end_to_end_theory/STATIC_SCAN_PACKAGE_PROTOCOL_V1.md)，结果与限制见[报告](../../docs/reports/experiments/EXP_036_PHYSICAL_SCAN_INTAKE_V1.md)。
