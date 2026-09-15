# EXP-010：两级浮点自适应 PWL 集成

> 状态：平衡块调度行为基线通过；硬件 PRNG/抽取调度尚未关闭  
> 架构配置：`gu_behavioral_v1`  
> PWL truth：`gu_gate_d_static_v0_1`  
> 正式运行：`artifacts/runs/EXP_010/two_stage_adaptive_v1_20260915`

## 1. 结论

EXP-009 的自适应下门限 gated-LMS 已按既定嵌套顺序接入完整两级 pipeline：

```text
stage2 raw -> PWL2(k2-bank) -> subtract Dd2 -> stage1 raw
stage1 raw -> PWL1(k1-bank) -> subtract Dd1 -> final centered code
```

每一级 LMS 只观察自己的局部 PWL 输出减去本级 dither 副本，不把本级粗量化
符号码加入门控幅值。当前实现把该选择标为行为假设，因为论文 Fig. 18 明确
给出逐级校正顺序，但未公开全部内部 LMS 总线位级图。

在 64 个平衡训练 epoch、每个 epoch 覆盖 4096 个输入码中心和四种双 dither
组合的条件下，两级各更新 1048576 次。自适应校正把全链 MAE 从
`5.40430` 降到 `0.33633` code，改善 `16.07x`；最大误差从 `12` 降到
`1.70249` code，物理过载为 0。已知 truth oracle 的 MAE/最大误差分别为
`0.23018/0.63520` code，因此自适应结果已恢复主要误差，但尚未达到结构
表达能力上限。

## 2. 两级更新定义

二级局部学习输出为：

```text
Dout,2 = PWL2(backend_centered_code) - Dd2
```

它与第二级粗符号合成第一级 raw code。一级局部学习输出为：

```text
Draw,1 = 128*q2 + Dout,2
Dout,1 = PWL1(Draw,1) - Dd1
```

最终 centered code 再加入 `512*q1`。两个系数 bank 都用当前样本校正时的旧
状态计算 gate/update；新状态从下一样本开始生效。

归一化步长按本级 raw-code 满量程平方缩放：

```text
mu_code = mu_normalized / code_full_scale^2
```

这样 `Dd*Dout` 从归一化坐标换到 512/128 code 坐标时保持同一平均更新尺度。

## 3. 正式结果

| 模式 | MAE (code) | 最大误差 (code) | 端点饱和 | 物理过载 |
|---|---:|---:|---:|---:|
| unity coefficients | 5.40430 | 12.00000 | 20 | 0 |
| two-stage adaptive | 0.33633 | 1.70249 | 4 | 0 |
| known-truth oracle | 0.23018 | 0.63520 | 3 | 0 |

| 级 | oracle `k1..k4` | adaptive `k1..k4` | gate counts `k1..k4` |
|---|---|---|---|
| stage1 | 1.08, 0.94, 1.03, 0.95 | 1.07753, 0.94730, 1, 1 | 1048576, 485587, 0, 0 |
| stage2 | 0.92, 1.06, 0.98, 1.04 | 0.91546, 1.06879, 0.99853, 1 | 1048576, 554038, 10718, 0 |

`k1/k2` 的最大绝对误差为一级 `0.00730`、二级 `0.00879`。一级 `k3/k4`
没有任何有效更新；二级 `k3` 的 gate fraction 只有约 `1.02%`，`k4` 仍为
0。因此最大码误差和 oracle 差距不能解释为“算法整体未工作”，而应拆成：

- 低段系数已经收敛到接近 oracle；
- 高段缺乏持续激励；
- 末级 SAR 量化使去相关目标与连续 inverse 的最小码误差目标并不完全相同。

## 4. 去相关固定点与 oracle 不同

对同一 16384 点评估块，平均 dither-output 乘积为：

| 模式 | stage1 `mean(Dd*Dout)` | stage2 `mean(Dd*Dout)` |
|---|---:|---:|
| unity | -64.5000 | 3.40625 |
| adaptive | 0.78911 | 0.16497 |
| oracle | -0.07666 | -0.53141 |

自适应显著降低了自身观测上的相关性，但 oracle 在量化级联中不严格零相关，
尤其是第二级。这不是连续 inverse 错误：EXP-006 已证明连续求逆达到机器精度；
它表明 backend 量化、门控和离散输入会改变随机梯度的固定点。后续不能只用
`E[Dd*Dout]≈0` 宣称码域性能最优，也不能只用系数对 oracle 的偏差否定 LMS。

## 5. 调度和证据边界

训练使用每个 epoch 全覆盖并打乱的 4096 码中心 × 四种 dither 组合，保证
有限样本中的 dither 平衡。这是一项两级算法集成基线，不是：

- 四路 750 MHz 真实 PRNG 序列；
- decimate-by-30 的硬件更新时序；
- 11-bit 系数和全链 3 fractional-bit 的位真实现；
- outer-slice convergence 或 2-bit linearization dither 的证明。

下一实验应使用独立随机 PRNG，比较逐样本、每 30 样本抽取和块相关估计，
同时报告每段有效更新数、系数均值/方差、相关残差、MAE 和最大误差。第四段
仍必须保持冻结，除非另有受控持续激励。

