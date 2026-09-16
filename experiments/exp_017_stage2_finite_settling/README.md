# EXP-017：阶段二一阶有限建立基线

本实验验证首个动态状态模型：每一级当前静态 residue 是建立目标，实际 residue
在一个放大相位后保留固定比例的前一样本误差。理论侧对周期输入求唯一循环稳态，
参考平台侧则从留出初值逐样本预热后再记录，两者实现相互独立。

正式验证包含静态极限、论文主路径 `11 GHz/100 ps` 锚点，以及较短相位和较低
带宽两组研究压力条件；输入覆盖两个幅度和两个相干频点。本实验只验证一阶状态
理论与参考平台的一致性，不声称论文已公开足够信息来唯一识别芯片瞬态模型。

运行：

```powershell
$env:PYTHONPATH = "src"
python experiments/exp_017_stage2_finite_settling/run.py --run-id <run-id>
```

正式问题定义和模型边界见
`docs/specifications/STAGE2_FINITE_SETTLING_SPEC_V0_1.md`。
