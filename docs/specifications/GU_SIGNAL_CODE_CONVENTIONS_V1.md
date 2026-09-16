# Gu ADC 信号、码制与重构约定 v1

> 状态：行为级接口冻结  
> 适用配置：`gu_behavioral_v1`

## 1. 信号域与拓扑

每一级主信号输入采用半开区间 `-1 <= x < 1`。候选物理映射为
`x=2*v_diff/VFS_diff_pp`，其中 `VFS_diff_pp=1 V`，所以一个归一化单位
对应 0.5 V differential。

三级静态路径固定为：

```text
sampled input -> stage-1 flash/CDAC
stage-1 main residue -> stage-2 CDAC
stage-1 auxiliary residue -> stage-2 flash decision
stage-2 main residue -> 8-bit TI-SAR
```

因此 Q-007 的主/辅增益差折算到第二级 flash 判决坐标，不施加到第一级
输入 flash。

## 2. 前级量化、CDAC 与 residue

两个前级使用相同候选表：

```text
thresholds = [-7/8,-5/8,-3/8,-1/8,1/8,3/8,5/8,7/8]
symbols = [-4,-3,-2,-1,0,1,2,3,4]
a(q) = q/4
x_next = 4*(x_main-a(q)+d)
```

区间为左闭右开，等于阈值时进入高索引状态。`region_index`、物理 symbol
和内部二进制编码是不同概念；v1 不声明硅内部二进制编码。

双路径判决采用 `x_aux=rho*x_main+o_aux`。量化器在 `x_aux` 上判决，CDAC
和 residue 始终使用 `x_main`。阈值折算到主路径坐标为
`B=(t+theta-o_aux)/rho`。

## 3. dither

正 dither symbol 定义为在放大前 residue 求和点加正值；数字端减去对应
正数字副本。启用数字 PWL 校正时，应先完成该级校正再局部扣除其 dither；
不启用数字 PWL 时，按第 4 节的未校正式直接扣除。模拟放大传输与数字 PWL
校正是两个不同对象。

- 默认 profile：`d=+/-1/32`，第一级/第二级数字副本为 64/16；
- 替代 profile：`d=+/-1/64`，数字副本为 32/8。

每次运行必须记录 profile 名，不能只写“1/16 FS”。物理 PRNG bit 标签
不进入 v1 行为语义。

## 4. 后端与重构

后端为 8-bit offset-binary midrise 量化器：raw code `0...255`，centered
code `c3=raw-128`，输入区间 `[-1,1)`。理想 TI 通道归属为
`channel_id=sample_index mod 4`。

未扣 dither、未启用数字 PWL 校正的 centered 重构为：

```text
C = 512*q1 + 128*q2 + c3.
```

此时扣除对应 dither 数字副本后加 2048，得到最终 `0...4095` 输出。在
理想、无过载条件下，`D1=2048*d1`、`D2=512*d2` 为整数，数字减法恰好
抵消模拟注入量。启用两级数字 PWL 校正时则须按
`f2(c3) -> +128*q2 -> -D2 -> f1 -> +512*q1 -> -D1 -> +2048`
的局部顺序处理，不能先把两级数字副本合并到最末端。重构必须
保留逐级权重项、未扣 dither 码、数字副本、扣除后 centered 码、裁剪前
输出和最终码。

## 5. overload 与 correctable

以下事件分别记录：

- 主输入越过本级可表示域；
- 辅助判决坐标越过其名义分析域；
- 放大后 residue 越过下一级可表示域；
- SAR 输入越界；
- 最终数字输出裁剪。

`correctable=False` 表示主信号信息路径发生过载或最终裁剪。辅助坐标单独
越界不自动表示信息丢失；若它导致错误状态并进一步造成 residue 过载，
则仍会由主路径事件判为不可纠正。

## 6. 最小完整 trace

trace 至少包含 sample index/input、两级 main/aux input、region/symbol、
CDAC 名义/mismatch/dither 分项、放大前/后 residue、主输入及 residue
overload、SAR channel/raw/centered code，以及全部数字重构分项。

任何更改阈值表、dither profile、路径映射、权重或端点语义的工作都必须
产生新配置 ID；旧运行不得静默继承。
