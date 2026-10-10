# EXP-030：候选 Gu 定点 PWL 的逐码 RTL 核对

本实验只验证固定系数、单级四段校正模块与既有 Python `correct_fixed` 的数字等价。两级 Q3 分段宽度为 1024/256，系数为 11 位 Q1.10；采用最近偶数舍入、先求系数和再舍入偏移、负满量程延伸末段。规则均属明确的候选设定。

在仓库根目录生成全部合法输入码和少量非法端部的预期结果，再用 Icarus 10.3 仿真：

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_030_fixed_pwl_rtl.generate_vectors artifacts/runs/EXP_030/candidate_a_q3_q10/vectors.txt
```

```bash
cd /mnt/d/ADC
iverilog -g2012 -s tb_fixed_pwl_candidate_a \
  -o artifacts/runs/EXP_030/candidate_a_q3_q10/pwl_tb.vvp \
  rtl/gu_baseline/fixed_pwl_candidate_a.sv \
  rtl/gu_baseline/tb_fixed_pwl_candidate_a.sv
vvp artifacts/runs/EXP_030/candidate_a_q3_q10/pwl_tb.vvp \
  +VECTORS=artifacts/runs/EXP_030/candidate_a_q3_q10/vectors.txt
```

结果与适用范围见[实验报告](../../docs/reports/experiments/EXP_030_FIXED_PWL_RTL_V1.md)。向量只含数字字，不含模拟增益真值；软件和 RTL 一致不等于芯片实现已知。
