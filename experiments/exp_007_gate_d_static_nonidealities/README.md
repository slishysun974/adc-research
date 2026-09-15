# EXP-007：静态非理想独立开关与 Gate D

## 研究问题

验证 flash threshold offset、CDAC code-level mismatch、线性主增益和静态
PWL truth 是否可以独立启停、零值是否退化为理想链、每个效应是否进入正确
trace 字段，以及组合时是否遵守固定物理顺序。

## 固定顺序

```text
auxiliary input
  -> flash threshold offsets
  -> CDAC decision and code-level mismatch
  -> analog dither injection at residue summing node
  -> linear inter-stage gain
  -> static PWL truth
  -> next stage
```

阈值 offset 只移动辅助判决边界；CDAC mismatch 改变被主路径相减的模拟重构
值；dither 在放大前相加；线性增益先于 PWL shape。最后两项通常不可交换，
因此实验另行统计“PWL 后再施加线性增益”的反事实差异。

## 验收边界

Gate D 在本实验中只关闭接口和组合语义：

- 基线与显式全零 bundle 必须数值恒等；
- 单开关 case 的 trace 只能出现该效应，不能泄漏到其他字段；
- 全组合 case 必须逐样本满足固定的 residue/gain/PWL 代数；
- 重复运行必须逐对象一致；
- 合成非理想导致多少错码、端点饱和或过载只作为响应观测，不作为“结构
  是否正确”的替代判据。

配置数值是为激活路径而选的合成 stimulus，不代表 Gu 芯片统计分布或校准后
残差。oracle、定点和 LMS 均不在本实验范围内。

## 运行

```powershell
$env:PYTHONPATH = "src"
python experiments/exp_007_gate_d_static_nonidealities/run.py --run-id <unique-run-id>
```

