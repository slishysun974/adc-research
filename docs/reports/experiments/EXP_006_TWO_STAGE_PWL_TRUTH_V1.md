# EXP-006：两级已知 PWL truth 与 oracle 校正级联

> 状态：行为级通过；不代表 LMS 已收敛或定点 bit-true 已关闭  
> 架构配置：`gu_behavioral_v1`  
> 正式运行：`artifacts/runs/EXP_006/two_stage_pwl_truth_v1_20260915`

## 1. 结论

已建立两级相互独立的**合成模拟非线性 PWL 近似**、由这些已知 truth 唯一推导的浮点 oracle
系数，以及符合论文数字引擎顺序的两级校正级联：

```text
8-bit SAR centered code
  -> 第二级 PWL 校正
  -> +128*q2
  -> -Dd2 (16 code)
  -> 第一级 PWL 校正
  -> +512*q1
  -> -Dd1 (64 code)
  -> +2048
```

连续码坐标上的 truth/oracle 复合误差不超过 `5.684e-14` code。加入末级
8-bit SAR 量化后，在 4096 个输入码中心和四组 dither 符号的 16384 次检查
中，校正后 MAE 为 `0.2302` code，较未校正的 `5.4043` code 改善
`23.48` 倍；最大绝对误差由 12 code 降至 `0.6352` code。所有固定 dither
传输曲线均无负向步，且没有主信号路径或后端物理过载。码中心采样中共有
592 个相邻平步，属于末级量化后的重复样本值，不能解释为连续传输回折。

把第二级 dither 延迟到第一级 PWL 之后再扣除时，MAE 增至 `1.0257` code，
是正确顺序的 `4.46` 倍。这一错序反例证明 dither 扣除位置不是可交换的实现
细节。

## 2. Truth 与 oracle 的独立定义

每级 truth 不直接保存数字校正系数，而是用非负半轴上的两组配对边界定义：

```text
x_i = nominal linear-amplifier output edge
y_i = distorted physical-output edge
```

第 `i` 段的正向 truth 为：

```text
y = y_i + a_i * (x - x_i),
a_i = (y_(i+1)-y_i) / (x_(i+1)-x_i).
```

负半轴按奇对称扩展。Gu 的 PWL 数字块按 raw code 的 MSB 选择等宽段，所以
本实验的 `y_i` 等间隔；oracle 由配对边界反推：

```text
k_i = Delta x_i / Delta y_i
```

再按 raw/corrected code full scale 做单位换算。这样 truth 在平台层、oracle
在校准层，两者不会通过手填两套相同参数形成循环自证。

采用的两个合成 truth 均保持 `(0,0)`、`(1,1)` 端点，但段内斜率不同：

| 级 | ideal output edges | distorted output edges | 推导 oracle `k_i` | `b0` |
|---|---|---|---|---:|
| 第一级 | 0, 0.27, 0.505, 0.7625, 1 | 0, 0.25, 0.5, 0.75, 1 | 1.08, 0.94, 1.03, 0.95 | 128 |
| 第二级 | 0, 0.23, 0.495, 0.74, 1 | 0, 0.25, 0.5, 0.75, 1 | 0.92, 1.06, 0.98, 1.04 | 32 |

这些系数是用于结构可表达性验证的合成 truth，不是论文测得系数，也不应被
解释为 Gu 芯片的典型非线性。这里采用 PWL 表示模拟传输，是为了让平台
truth 可控且可求精确 oracle；论文提出的 PWL 则是量化后的**数字校正函数**。
真实模拟放大器传输无需恰好分段线性。

## 3. 两级代码代数

记 `P2`、`P1` 为第二、一级 oracle PWL，`c3` 为 8-bit SAR centered code，
`q2/q1` 为两个 flash symbol，则：

```text
c2_cal = P2(c3)
c1_raw = 128*q2 + c2_cal - Dd2
c1_cal = P1(c1_raw)
c_out   = 512*q1 + c1_cal - Dd1 + 2048.
```

第二级 `Dd2=+/-16` 必须先从合成的第一级 residue raw code 中移除，因为它
注入在第二级放大器前，不属于第一级放大器的输入输出关系。第一级
`Dd1=+/-64` 则属于第一级 PWL 所需恢复的线性分量，只能在 `P1` 后扣除。

## 4. 正式运行结果

| 指标 | 结果 |
|---|---:|
| 连续 truth/oracle 检查 | 32768 |
| 最大连续求逆误差 | `5.684e-14` code |
| 量化级联检查 | 16384 |
| 未校正 MAE / 最大误差 | `5.4043 / 12` code |
| 正确两级校正 MAE / 最大误差 | `0.2302 / 0.6352` code |
| MAE 改善倍数 | `23.48x` |
| 错序 MAE / 最大误差 | `1.0257 / 1.9152` code |
| 错序/正确顺序 MAE 比 | `4.46x` |
| 负向传输步 | 0 |
| 码中心相邻平步 | 592 |
| 物理过载 | 0 |
| 校正值越过最终端点 | 3 次，仅输入码 0/4095 |

连续求逆可以达到浮点精度，但量化级联不能逐点零误差：末级 SAR 先对失真
模拟量量化，oracle 无法恢复已丢失的子 LSB 信息。三次最终端点越界的最大
幅度小于一个 code，且只发生在理想端点码；当前以显式 clipping/saturation
事件保留。最终 3-bit fractional 定点舍入加入后，应重新审计端点规则和
码判决，不能从本实验推断 bit-true 输出。

## 5. 覆盖与限制

两级连续 truth 的四段都通过了独立反函数探针，但候选 A 的正常 residue 加
当前 1-bit dither 只在完整 pipeline 扫描中激活前三段。两级第 4 段的实际
pipeline 覆盖均为零。这不是实现失败，而是现有信号范围的可达性结果；若要
验证第 4 段的在线提取或数据通路覆盖，需要引入受控的大信号 linearization
dither、扩大目标 stimulus，或重新审查内部 code scaling。

本实验还不包含：

- LMS 系数提取、更新调度或收敛噪声；
- 11-bit 系数、10 fractional bits 和全链 3 fractional bits 的舍入；
- CDAC mismatch、阈值 offset、独立线性增益误差的组合顺序；
- 正负半轴独立系数和偶次失真；
- 第二级 PWL 前是否存在论文未公开的统一 10-bit 内部缩放。

## 6. 证据边界与下一步

OJSSCS Fig. 18 明确给出 Stage 2&3 校正在前、Stage 1 校正在后的数字引擎
顺序；Figs. 2-5 和 Eqs. (1)-(3) 支持每级 PWL 结构及“模拟加 dither、校正
后数字减”的局部顺序。论文没有给出本实验的合成 truth 参数，亦未完整公开
第二级内部缩放和定点端点逻辑。

下一步应把 PWL truth、主增益、CDAC mismatch 和阈值 offset 作为互相独立
的非理想开关接入统一配置，明确组合顺序并完成 Gate D；随后再加入定点 PWL
和 LMS，而不是用 oracle 结果代替估计算法验证。

## Sources

- Gu et al., OJSSCS 2026，Figs. 2-5、11、18，Eqs. (1)-(3)；本地副本
  `references/local/OJSSCS2026_Gu.pdf`。
- Gu et al., ISSCC 2025，Figs. 24.1.2-24.1.3；本地副本
  `references/local/ISSCC2025_Gu.pdf`。
