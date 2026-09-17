# EXP-008：预设模拟传输与数字校正的第 4 段可访问性

> 状态：行为级可达性审计通过；硅 linearization dither 映射仍未决  
> 架构配置：`gu_behavioral_v1`  
> 非理想配置：`gu_gate_d_static_v0_1` 的 PWL truth  
> 正式运行：`artifacts/runs/EXP_008/slice4_reachability_v1_20260915`

> 术语说明：本报告的 `truth` 是预设模拟传输，`oracle` 是已知传输下的理想逆校正；`slice occupancy` 指样本进入某分段的次数，不等于 LMS 对该分段系数的有效更新次数。见[研究文档术语约定](../../TECHNICAL_WRITING_CONVENTIONS_V1.md)。

## 1. 结论

EXP-006 中第 4 个 PWL slice 零覆盖的原因是模拟 residue 摆幅不足，而不是
一致的内部 code scaling。候选 A 无 dither 的 nominal residue output 半幅
上确界为 `0.5`；默认 preamp dither `d=1/32` 经四倍增益后只把可达半幅
扩到：

```text
R_reach = 0.5 + 4*(1/32) = 0.625.
```

两级 truth 的第 4 段分别从 `0.7625` 和 `0.74` 开始，因此默认 profile
在完整 pipeline 扫描中两级均为 0 次命中，与解析预测一致。

采用合成的 `d=5/64` probe 后，可达半幅变为 `0.8125`。4096 个输入码中心
与四种 dither 组合中，第一级/第二级 truth 的第 4 段分别命中 832/1216 次，
两级物理过载均为 0；两级 oracle 校正的最大误差仍小于 `0.65` code。

对 raw code 与 `b0` 同时进行 `2x/4x/8x` 缩放的 3840 次检查全部保持 slice
index 和归一化校正输出不变。因此，若第二级 8-bit code 被统一放大到 10-bit
内部单位且 `b0` 同比例变化，该缩放不会改变任何 PWL slice occupancy。

## 2. 解析可达性

设无 dither 的 residue output 半幅为 `R`，dither 在放大前 summing node 的
半幅为 `d`，inter-stage gain 为 `G`。输出可达幅度上确界为：

```text
R_reach = R + G*d.
```

要进入下边界为 `x3` 的第 4 段，需要严格满足：

```text
d > (x3 - R)/G.
```

同时，nominal next-stage range 为 `[-1,1)` 时，不发生 nominal overload 的
上界为：

```text
d <= (1 - R)/G = 0.125.
```

| 级 | 第 4 段下边界 `x3` | dither 下确界 | nominal-safe 上界 | 默认 `1/32` | probe `5/64` |
|---|---:|---:|---:|---|---|
| 第一级 | 0.7625 | 0.065625 | 0.125 | 不可达 | 可达 |
| 第二级 | 0.74 | 0.06 | 0.125 | 不可达 | 可达 |

等于下确界时仍不能保证命中，因为候选 A 的正向 residue 上边界是上确界而非
闭端点；实验选择 `5/64`，为有限码中心留出明确余量。

## 3. 正式运行结果

| Profile | preamp dither | 可达半幅 | stage1 truth slice4 | stage2 truth slice4 | 物理过载 | 校正 MAE / 最大误差 |
|---|---:|---:|---:|---:|---:|---:|
| behavioral default | 0.03125 | 0.625 | 0 | 0 | 0 | 0.2302 / 0.6352 code |
| controlled probe | 0.078125 | 0.8125 | 832 | 1216 | 0 | 0.2453 / 0.6400 code |

controlled probe 的第一级/第二级数字 dither 副本相应为 `160/40` code；两者
都是整数，因而本实验没有额外引入非整数副本误差。校正 block 的第 4 段命中
为 832/1280 次；第二级 correction 与 analog truth 的 64 次差异来自末级 SAR
量化后 raw code 边界，与 EXP-006 已记录的量化残差属于同一类现象。

两种 profile 的校正后最终端点事件分别为 3/4 次，均未伴随物理过载。本实验
的通过条件关注 slice 可达性、物理安全和缩放不变性，不宣称解决最终定点
舍入。

## 4. 内部码缩放为何不改变覆盖

PWL selector 为：

```text
i = floor(abs(Draw) / b0).
```

若内部统一缩放为正数 `s`，且 code 与 segment width 一致缩放：

```text
floor(abs(s*Draw)/(s*b0)) = floor(abs(Draw)/b0).
```

校正 local code、累计 offset 和最终结果都整体乘以 `s`，除以 `s` 后恢复同一
归一化输出。EXP-008 对两级完整有符号码域和三种 scale factor 共检查 3840
次，失败为 0。

因此，Q-008 中“第二级可能先缩放到公共 10-bit 计算单位”的未决信息仍影响
bit width、定点和 `b0` 的数值表示，但在自洽缩放前提下不影响模拟幅度对应的
slice occupancy。若只缩放 code 而不缩放 `b0`，那不是同一 PWL 的单位变换，
而是重新定义 segment 边界。

## 5. 证据边界

`controlled_slice4_probe` 是合成 1-bit 幅度实验，只证明“增大模拟可达幅度可
安全激活第 4 段”这一机制。它不是论文提出的 2-bit large-signal linearization
dither `+/-0.25/+/-0.75` 的实现复刻，也没有恢复 PRNG 到 CDAC 电容的开关
映射。后者仍需电路真值表或作者信息才能升级为 bit-true 模型。

当前可以关闭的是：

- 默认第 4 段零覆盖具有解析原因；
- 冗余允许范围内存在可激活第 4 段的行为级 dither 幅度；
- 一致内部 code scaling 不是覆盖缺失的解释。

下一步进入浮点到定点的 PWL 实现：11-bit `k_i`、10 fractional bits、全链
3 fractional bits，以及各操作的舍入、饱和和负满量程端点。
