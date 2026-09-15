# EXP-007：静态非理想独立开关与 Gate D

> 状态：Gate D 行为级通过；配置为合成路径 stimulus  
> 架构配置：`gu_behavioral_v1`  
> 非理想配置：`gu_gate_d_static_v0_1`  
> 正式运行：`artifacts/runs/EXP_007/gate_d_static_v1_20260915`

## 1. 结论

flash threshold offset、CDAC code-level mismatch、线性 inter-stage gain 和
静态 PWL truth 已从理想架构配置中拆出，成为两级各自独立的非理想开关。
EXP-007 对 7 个 case 各穷举 4096 个输入码中心与 4 组 dither，共执行
114688 次完整 pipeline 检查。Gate D 的结构验收结果全部为零失败：

| Gate D 检查 | 失败/事件 |
|---|---:|
| 理想基线错误 | 0 |
| 显式全零 bundle 与禁用态数值差异 | 0 |
| 单开关 trace 泄漏 | 0 |
| 已启用效应未激活 | 0 |
| 组合代数不一致 | 0 |
| 重复运行不一致 | 0 |

增益与 PWL 同时启用时，有 16367 个 stage-sample 对“先线性增益再 PWL”与
“先 PWL 再线性增益”给出不同结果，证明两者通常不可交换，组合顺序必须是
模型契约而不能由调用代码偶然决定。

## 2. 冻结的组合顺序

当前静态行为级顺序为：

```text
auxiliary input
  -> flash threshold offsets
  -> flash decision
main input + decision
  -> CDAC nominal level + code-level mismatch
  -> analog dither at residue summing node
  -> linear inter-stage gain
  -> static PWL truth
  -> next stage
```

对应逐级代数为：

```text
B_i,eff = B_i,nom + delta_B_i
q       = Q(x_aux; B_eff)
a_q,act = a_q,nom + epsilon_q
r_pre   = x_main - a_q,act + d
r_lin   = G_act * r_pre
r_out   = T_pwl(r_lin).
```

其中 `T_pwl` 禁用时为恒等映射，`G_act` 未配置时回到名义增益。threshold
offset 只作用于辅助判决坐标，不被错误地加到主信号路径；CDAC mismatch、
dither、gain 和 PWL 分别保留独立 trace。

## 3. 单项响应

下表的“输出变化”是相对同一输入/dither 的理想基线；这些合成数值只用于
确认路径被激活，不作为芯片性能估计。

| Case | 输出码变化 | stage1/2 判决变化 | stage1/2 residue 变化 | 最大未裁剪误差 | 物理过载 | 最终饱和 |
|---|---:|---:|---:|---:|---:|---:|
| baseline disabled | 0 | 0 / 0 | 0 / 0 | 0 | 0 | 0 |
| explicit zero bundle | 0 | 0 / 0 | 0 / 0 | 0 | 0 | 0 |
| threshold offsets only | 0 | 68 / 148 | 68 / 80 | 0 | 0 | 0 |
| CDAC mismatch only | 12790 | 0 / 112 | 14336 / 15872 | 2 code | 0 | 16 |
| linear gain only | 12348 | 0 / 288 | 16384 / 16384 | 4 code | 0 | 4 |
| PWL truth only | 16076 | 0 / 512 | 16384 / 16384 | 12 code | 0 | 20 |
| all combined | 14865 | 68 / 472 | 16384 / 16384 | 12 code | 0 | 25 |

threshold-only case 虽然改变了 216 次级间判决及其 residue trace，最终码仍
全部与基线一致。这说明开关确实生效，但偏移仍位于候选 A 的数字冗余可吸收
范围内；不能仅凭最终码不变断言阈值路径没有影响。

其余单项和组合 case 出现的最终饱和都没有伴随主信号 stage 或后端 SAR
物理过载。它们是未校正数字重构在输出端附近越界后的显式 clipping 事件。
全组合 case 的 25 次饱和只涉及输入码 `0...6` 和 `4089...4095`。Gate D
验证接口语义，不把这组任意合成幅值的未校正性能作为通过条件。

## 4. 实现边界

新增 `StaticStageNonidealities`/`StaticPipelineNonidealities`，默认实例表示全部
关闭；显式零值 bundle 则使用零 threshold offset、零 CDAC error、名义增益
和 identity PWL，两者在完整扫描中数值恒等。`QuantizerResult` 现在同时保留
名义 offset、实际 offset 和 effective thresholds；放大器 trace 同时保留
名义输出坐标、实际线性增益输出坐标及 PWL segment。

命名 profile `gu_gate_d_static_v0_1` 的参数均为合成 stimulus：

- threshold offset 约为 `+/-0.0005...0.0015` normalized；
- CDAC code-level error 约为 `+/-0.0001...0.0009` normalized；
- 两级实际增益分别为 `4.04/3.96`；
- PWL truth 复用 EXP-006 的两组非均匀边界。

这些数值没有概率分布、相关性或硅测量来源，不能用于 yield、SNDR 或校准后
残差预测。

## 5. 后续

Gate D 已关闭静态平台的开关隔离和组合顺序。下一步应先审计现有信号范围
为何无法覆盖第 4 个 PWL slice，再建立 DNL/INL 与频谱协议。加入 oracle、
定点 PWL 或 LMS 时，应在当前顺序之上扩展，不能重新把物理 truth 混回理想
架构配置。

