# EXP-005：Q-008 PWL 幅值码、连续性与端点

> 状态：Q-008 行为级通过；bit-true 内部缩放仍未决  
> 架构配置：`gu_behavioral_v1`  
> 正式运行：`artifacts/runs/EXP_005/q008_v1_20260915`

## 1. 结论

Gu 的 4-slice PWL 校正先对有符号 raw code 取绝对值，再把常规幅值字段
分为 2-bit `D_MSB` 和剩余 `D_LSB`。对第 `n` 段：

```text
D_LSB,cal = k_n * D_LSB
b_n = b0 * sum(k_i, i=1..n)
D_out = sign(D_raw) * (b_n + D_LSB,cal).
```

累计 offset `b_n` 使前一段上端与后一段下端严格相接。斜率系数不仅校正
段内斜率，还通过累计 offset 影响所有更高幅值段。

论文对第一级 residue 的 10-bit 后端明确说明：正半轴使用 9-bit 幅值码，
前 2 bit 选 4 段，余下 7 bit 为 local code，因此 `b0=128`。OJSSCS
数字引擎段也明确写出 10-bit range、第二级权重和 `b0=128`，与这一解释
一致。

第二级放大器由 8-bit SAR 量化。若 PWL 输入直接采用本项目的未缩放
centered SAR code `[-128,127]`，常规幅值字段为 7 bit，所以：

```text
b0 = 2^(7-2) = 32.
```

这是当前行为平台中的严格值，但不是论文逐字给出的芯片内部常数。公开
材料没有完整展示第二级 PWL 前是否存在统一码域缩放；若芯片把 8-bit
SAR 码先放大到 10-bit 计算单位，内部 `b0` 会相应改变。因此 Q-008 只能
在“未缩放 SAR centered code”接口条件下关闭。

## 2. 负满量程端点

普通 8-bit centered code 为 `[-128,127]`。正侧最大幅值 127 可由 7 bit
表示，但 `abs(-128)=128` 等于四段总宽度，不能写成 2-bit segment index
加 5-bit local code。10-bit 情况同理：`abs(-512)=512` 超出常规 9-bit
幅值字段。

论文说明负样本取绝对值校正，但没有公开该唯一端点的 bit-true 逻辑。
行为模型默认采用 `extend_last_slice`：把负满量程作为最后一段在
`D_LSB=b0` 处的连续端点，因此校正幅值为 `b0*sum(k_i)`。同时提供
`reject` 策略，使需要 bit-true 证据的运行在该点明确失败。模型不通过
静默裁剪把未知硬件选择伪装成已知。

## 3. EXP-005 结果

使用非平凡斜率 `[1.1,0.8,1.25,0.95]`，分别验证 10-bit 与 8-bit
centered code profile：

| 检查 | 数量 | 失败 |
|---|---:|---:|
| unity 系数全有符号码域恒等 | 1280 | 0 |
| 正负奇对称 | 638 | 0 |
| 已知单调 PWL 逆映射恢复 | 16380 | 0 |
| 两种 profile 的三处正/负连续边界 | 12 | 0 |

连续边界采用 `1e-9` code 的单边探针，最大输出差约 `1.25e-9`，等于探针
距离乘相应局部斜率，不是有限跳变。`-128` 和 `-512` 均进入显式连续
延伸路径；同一输入在 reject profile 中均按预期抛出错误。

新增 `calibration/pwl.py` 是浮点参考实现，不含 LMS 更新、定点舍入或
饱和。它提供 `slice_width_from_unsigned_bits`、逐样本完整分解 trace、
累计 offset 和可配置负满量程策略。

## 4. 来源层级

| 结论 | 层级 |
|---|---|
| 4-slice、2-bit selector、累计 offset 公式 | paper_reported |
| 10-bit 第一阶段后端正侧 9 bit、7-bit local code、`b0=128` | paper_reported |
| 负样本取绝对值并共用系数 | paper_reported（忽略显著偶次项时） |
| 第二级未缩放 8-bit SAR 对应 `b0=32` | derived conditional |
| `-128/-512` 连续延伸 | behavioral assumption，可证伪 |

ISSCC 论文明确把 `D_res,raw` 描述为第一阶段 residue 经 10-bit backend
量化后的码，并给出正侧 9 bit、2+7 bit 分解；演示稿确认同一结构，但
没有补充第二级内部缩放或负满量程真值表。

## 5. 适用范围与后续

Q-008 在浮点行为级关闭：`b0=128/32` 的代码单位、段边界、连续性、
符号恢复和负端点策略均已显式实现。以下内容仍未完成：

- 芯片第二级 PWL 前是否把 8-bit SAR 码缩放到公共 10-bit 单位；
- 11-bit `k_i`、10 fractional bits 和全链 3 fractional bits 的逐操作舍入；
- 正负独立系数对偶次失真的扩展；
- PWL truth amplifier 与两级校正级联、dither 扣除的完整集成。

下一实验应建立已知 PWL truth，通过“先第二级、再第一级”的数字级联检查
校正结构表达能力；此时仍不引入 LMS 估计误差。

## Sources

- Gu et al., OJSSCS 2026，Figs. 2-3、Eqs. (1)-(3)、Fig. 18 和数字引擎段；
  本地副本 `references/local/OJSSCS2026_Gu.pdf`。
- Gu et al., ISSCC 2025，Fig. 24.1.2 及正文；本地副本
  `references/local/ISSCC2025_Gu.pdf`。
- ISSCC 2025 演示稿 pp. 14-19、34-37；本地副本
  `references/local/ISSCC2025_Gu_Slides.pdf`。
