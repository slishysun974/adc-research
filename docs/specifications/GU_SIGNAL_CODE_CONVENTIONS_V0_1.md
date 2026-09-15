# Gu ADC 信号、码制与重构约定 v0.1

> 状态：接口约定草案；不声称复原了论文未公开的电路码表  
> 目标：在缺失细节仍可见的前提下，固定软件中的单位、边界和数据流

## 1. 设计原则

首版平台采用“归一化数值域 + 可替换码表”。归一化约定可以立即固定；Gu 芯片的 flash/CDAC 真值表保持为配置输入，不在实现中暗藏一种未经证实的标准流水线假设。

任何运行必须同时记录：

- `architecture_config_id`；
- `assumption_set_id`；
- 输入、噪声和 mismatch 的随机种子；
- 模式（理想、已知参数校正、自适应后台校准）；
- 是否启用饱和、动态建立、dither 和通道 mismatch。

## 2. 归一化信号域

定义每一级名义输入归一化变量 `x_l`，满量程区间统一为：

```text
-1 <= x_l < 1
```

左端包含、右端不包含，以消除端点双重归属。物理电压换算写为：

```text
x = 2 * v_centered / VFS_pp
```

这里的 `VFS_pp` 是该节点的满量程峰峰值。Gu 文献给出输入满量程 1 Vpp，但没有在现有文字中消除单端/差分歧义，因此 `VFS_pp=1 V` 只作为来源值保存；所有首版正确性测试在归一化域完成。

## 3. 量化器接口

每个量化器由显式配置定义：

```text
thresholds = [t_0, ..., t_(K-2)]
output_symbols = [q_0, ..., q_(K-1)]
```

约定：

- `thresholds` 严格递增；
- 区间采用 `[lower, upper)`；恰好等于阈值时进入较高索引区间；
- 量化器返回 `region_index` 和 `output_symbol`，两者不得混为一谈；
- 超出名义范围时同时返回 `overload_low/high` 标志，是否饱和由配置决定；
- 第一级和第二级的 `thresholds/output_symbols` 在证据未闭合前为必填假设，不由“3-bit”自动生成。

这一边界规则属于软件可复现约定，不是论文报告的硬件比较器在零噪声下的物理定律。

## 4. CDAC 与残差接口

每级 CDAC 由码相关重构表定义：

```text
dac_levels[q] = a_l(q)
dither_levels[d] = delta_l(d)
```

静态残差的一般形式为：

```text
e_l = x_l - a_l(q_l) + s_dither * delta_l(d_l)
x_(l+1) = f_amp_l(e_l)
```

理想放大器为 `f_amp_l(e) = G_l * e`，其中前两级 `G_l=4`。`s_dither` 的电路极性、`a_l(q)` 的精确权重和 dither 开关表当前未公开，必须来自命名假设集；dither 关闭时该歧义不会影响理想静态链验证。

非理想扩展按固定次序组合，避免不同模块重复施加同一误差：

```text
quantizer threshold/aux-path error
    -> CDAC code and element mismatch
    -> residue input
    -> amplifier gain/nonlinearity/finite settling/noise
    -> next stage input
```

## 5. 数字码表示

通用 N-bit 后端量化器同时保留：

- `raw_unsigned`：`0 ... 2^N-1`；
- `centered_code`：由配置中的零点和缩放得到；
- `normalized_code`：映射回 `[-1, 1)` 的分析值。

不得默认 Gu 芯片内部一定使用 offset binary、two's complement 或某一种 thermometer-to-binary 编码。位级实现必须由配置中的 `encoding` 字段显式启用。

论文的 4-slice PWL 说明应表示为独立的“幅值码分解”接口：

```text
abs(raw_code) = b0 * D_MSB + D_LSB
D_LSB_cal = k[D_MSB] * D_LSB
b_n = b0 * sum(k_i, i=1..n)
output = sign(raw_code) * (D_LSB_cal + b[D_MSB])
```

具体符号位、零点、最大正/负码和饱和规则未明确前，不进入 bit-true 基线。浮点参考校正器先用于验证分段连续性和算法方向。

## 6. 数字重构

最终重构不硬编码成位移表达式，而由逐级权重表组合：

```text
y_raw = W1[q1] + W2[q1, q2] + W3[q1, q2, q3]
```

对名义 radix-4、两级各贡献 2 个有效位的候选实现，可以把上式约化为逐级 radix 重构；但在 flash/CDAC 码等价类完成审计前，这只是待验证推导，不能标记为 `paper_reported`。

重构模块必须输出：

- 未裁剪高精度码；
- 最终 12-bit 码；
- 饱和标志；
- 使用到的逐级权重；
- 冗余等价类标识。

## 7. 逐样本 trace 最小字段

```text
sample_index, time_s, input_normalized
stage1.main_input, stage1.aux_input, stage1.region, stage1.code
stage1.dac_value, stage1.dither, stage1.residue_preamp, stage1.residue
stage2.main_input, stage2.aux_input, stage2.region, stage2.code
stage2.dac_value, stage2.dither, stage2.residue_preamp, stage2.residue
backend.channel_id, backend.region, backend.raw_code
digital.preclip_code, digital.output_code, digital.saturated
redundancy.class_id, redundancy.correctable
```

校准模式再增加 `k_i`、`b_i`、门控状态、dither 数字副本、校正前后码和系数更新事件。

## 8. 第一版假设集的命名规则

论文未给出的选择必须放入独立文件并使用显式 ID，例如：

```text
gu_static_hypothesis_a_v0_1
```

假设集至少包含 flash 阈值、输出符号、CDAC 电平、dither 极性、逐级重构权重、端点规则和物理电压解释。假设一旦改变，必须产生新 ID；旧运行不得静默继承新含义。

