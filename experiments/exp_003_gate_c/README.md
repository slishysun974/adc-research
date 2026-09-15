# EXP-003：三级理想链 Gate C

## 研究问题

在 `gu_static_hypothesis_a_v0_1` 下，两个 radix-4 前级、4 路 8-bit
TI-SAR 后端以及 `512/128/1` 数字重构能否形成确定、单调、无缺码的
12-bit 静态传输？候选 dither 的 64/16 数字副本和替代峰峰值解释的
32/8 数字副本能否逐码抵消？

## 验收条件

- 4096 个 12-bit 码中心逐码等于独立均匀量化器；
- DC 传输单调且无缺码；
- 默认 dither、两种 3% 辅助增益比和四种双 dither 符号组合全部精确；
- 替代峰峰值 dither 配置也满足对应的整数平移恒等式；
- trace 保留两级判决、CDAC、residue、SAR 通道/码和数字重构分项；
- 相同输入、配置和样本索引逐位复现。

## 运行

```powershell
$env:PYTHONPATH = "src"
python experiments/exp_003_gate_c/run.py --run-id <unique-run-id>
```

运行产物写入 `artifacts/runs/EXP_003/<run-id>/`。脚本拒绝覆盖已有 run。
