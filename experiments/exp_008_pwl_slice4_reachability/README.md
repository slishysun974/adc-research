# EXP-008：第 4 个 PWL slice 可达性与内部码缩放

## 研究问题

EXP-006 的完整 pipeline 扫描只覆盖前三个 PWL slice。本实验区分两种可能：

1. 模拟 residue 摆幅不足，需要额外的大幅度激励；
2. 第二级内部码可能统一缩放，导致数字 segment 选择发生变化。

## 解析边界

候选 A 无 dither 的 nominal residue output 半幅为 `R=0.5`。若 dither 在
放大前 residue summing node 的半幅为 `d`，增益为 `G=4`，可达输出半幅
上确界为：

```text
R_reach = R + G*d.
```

对第 4 段下边界 `x3`，所需 dither 的下确界为 `(x3-R)/G`；不超过 nominal
next-stage range 的 dither 上界为 `(1-R)/G=0.125`。EXP-006 两级 truth 的
下确界分别为 `0.065625` 和 `0.06`，默认 `1/32` 不足，而合成 probe
`5/64=0.078125` 位于可达且 nominal-safe 的区间内。

## 两种路径的区分

`controlled_slice4_probe` 是行为级幅度实验。它仍使用 1-bit `+/-d`，数字
副本按当前码单位改为第一级 `+/-160`、第二级 `+/-40`。它不是论文所述
`+/-0.25/+/-0.75` 2-bit linearization dither 的硅映射，后者的 CDAC/PRNG
开关表仍未公开。

内部码缩放则用代数不变性审计：若 raw code 与 `b0` 同时乘以正比例 `s`，
则 `floor(abs(Draw)/b0)` 不变，校正输出只整体乘以 `s`。因此一致的统一码
缩放不能改变 slice occupancy；只有不同比例的阈值定义才会改变模型语义。

## 运行

```powershell
$env:PYTHONPATH = "src"
python experiments/exp_008_pwl_slice4_reachability/run.py --run-id <unique-run-id>
```

