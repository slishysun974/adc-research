# EXP-031：两级冻结系数 Gu 候选 RTL 对照

先生成数字参考向量，再在仓库根目录使用 Icarus Verilog 10.3 仿真。生成器只调用现有数字参考模型，不读取模拟增益真值。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_031_two_stage_rtl.generate_vectors artifacts/runs/EXP_031/candidate_a_default_dither/vectors.txt
```

```bash
cd /mnt/d/ADC
iverilog -g2012 -s tb_two_stage_fixed_candidate_a \
  -o artifacts/runs/EXP_031/candidate_a_default_dither/cascade_tb.vvp \
  rtl/gu_baseline/fixed_pwl_candidate_a.sv \
  rtl/gu_baseline/two_stage_fixed_candidate_a.sv \
  rtl/gu_baseline/tb_two_stage_fixed_candidate_a.sv
vvp artifacts/runs/EXP_031/candidate_a_default_dither/cascade_tb.vvp \
  +VECTORS=artifacts/runs/EXP_031/candidate_a_default_dither/vectors.txt
```

结果和证据边界见[EXP-031 报告](../../docs/reports/experiments/EXP_031_TWO_STAGE_RTL_V1.md)。生成的向量、摘要和编译产物只写在 `D:\ADC\artifacts`；使用 SoCLab 的 WSL 工具时不修改其项目文件。
