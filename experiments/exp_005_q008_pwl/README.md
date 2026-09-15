# EXP-005：Q-008 PWL 幅值码、连续性与端点

## 研究问题

Gu 的 4-slice unsigned-magnitude PWL 公式如何映射到本项目的 10-bit
第一阶段后端码和 8-bit SAR 后端码？累计 offset 是否在任意斜率下保持
连续？两补码负满量程的绝对值多出一个端点时，行为模型应如何显式处理？

## 来源与假设

- 论文明确给出：10-bit 第一阶段后端只取正半轴 9-bit 幅值码，2-bit
  slice selector、7-bit local code，`b0=128`；
- 论文明确给出 `b_n=b0*sum(k_i)` 和对负码取绝对值校正；
- `b0=32` 是第二级放大器直接使用未缩放 8-bit SAR centered code 时，由
  7-bit 常规幅值字段推导出的行为值；若硅实现先统一缩放，需产生新配置；
- 负满量程默认采用“最后一段连续延伸一个码点”，同时保留 reject 策略，
  不冒充未公开的 bit-true 逻辑。

## 运行

```powershell
$env:PYTHONPATH = "src"
python experiments/exp_005_q008_pwl/run.py --run-id <unique-run-id>
```

运行产物写入 `artifacts/runs/EXP_005/<run-id>/`，脚本拒绝覆盖已有 run。
