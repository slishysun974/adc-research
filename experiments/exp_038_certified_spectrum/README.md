# EXP-038：最终整数码范围的有理数频谱认证

用显式余项和向外舍入，验证从已覆盖的最终整数码到有限记录 SNDR/SFDR 的数值包含关系。保留 Gu Q22 在线算法与已有 RTL。本实验只有人工资料。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_038_certified_spectrum.run artifacts/runs/EXP_038/certified_v1
python -m unittest discover -s tests -p test_certified_spectral_bounds.py -v
```

实验包括两组记录：原 EXP-033 的 512 点人工数字集合，以及复用 EXP-036 扫描合同、EXP-037 精确判决的新 128 点有理数正弦输入。后者的输入按 `round_even(10^12*(3/25)*sin(2*pi*7*n/128))/10^12` 固定，两级 dither 和在线更新合同沿 EXP-037。这不是重算原斜坡实验的 ADC 单音指标。

`*_records.json` 保存整数码与输入／来源，`*_certificate.json` 保存每根中点谱线的功率范围、码扰动后的功率范围、功率比及分贝范围，端点全部为有理数字符串或显式无穷标记。`*_endpoints.json` 保存两条验证轨迹的点值证书；`summary.json` 保存来源摘要和向外舍入的六位小数显示。近似 NumPy 分数单独标明，不作为数值包含证明。

认证入口只接收整数码端点，拒绝浮点码。默认 72 位二进制小数精度；内部整数可任意长。直接 DFT 的复杂度为 `O(N²)`，适用于当前短记录核对，尚不是长记录认证 FFT。

理论与结果见[推导](../../docs/theory/CERTIFIED_FINITE_RECORD_SPECTRUM_V1.md)和[报告](../../docs/reports/experiments/EXP_038_CERTIFIED_SPECTRUM_V1.md)。输入范围没有可信物理覆盖时，数值认证仍不能证明芯片性能。
