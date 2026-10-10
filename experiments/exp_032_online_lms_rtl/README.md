# EXP-032：逐转换在线 Gu 候选 RTL

本实验使用五字段数字记录，逐次比对 Python 定点参考与两级候选 RTL 的最终整数码、门控和八个更新累加器。输入是人为生成的数字压力向量，不代表可到达的芯片状态或发生率。

在仓库根目录生成参考向量：

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_032_online_lms_rtl.generate_vectors artifacts/runs/EXP_032/candidate_a_q22/vectors.txt
```

在已有 Icarus Verilog 10.3 的 WSL 环境编译、运行：

```bash
cd /mnt/d/ADC
iverilog -g2012 -Wall -s tb_two_stage_adaptive_candidate_a \
  -o artifacts/runs/EXP_032/candidate_a_q22/adaptive_tb.vvp \
  rtl/gu_baseline/gated_product_candidate_a.sv \
  rtl/gu_baseline/fixed_pwl_candidate_a.sv \
  rtl/gu_baseline/two_stage_fixed_candidate_a.sv \
  rtl/gu_baseline/fixed_gated_lms_candidate_a.sv \
  rtl/gu_baseline/two_stage_adaptive_candidate_a.sv \
  rtl/gu_baseline/tb_two_stage_adaptive_candidate_a.sv
vvp artifacts/runs/EXP_032/candidate_a_q22/adaptive_tb.vvp \
  +VECTORS=artifacts/runs/EXP_032/candidate_a_q22/vectors.txt
```

规则、结果及限制见 [EXP-032 报告](../../docs/reports/experiments/EXP_032_ONLINE_LMS_RTL_V1.md)。
