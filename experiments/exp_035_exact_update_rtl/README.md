# EXP-035：Q22 更新的等价整数 RTL

保持 EXP-032 的步长、Q22 状态、Q1.10 输出、`≥` 门控、饱和及逐转换时序，只实现[已证明的整数化简](../../docs/stages/03_gu_baseline/CANDIDATE_A_EXACT_UPDATE_ARITHMETIC_V1.md)。两级 dither 副本固定为 `±512/±128`，专用累加器入口只接受极性；它不是任意 dither 的通用 LMS 模块。合法学习输出必须分别在 `[-8700,8698]` 和 `[-2175,2159]`。原有 RTL 和 Python 基准不修改。

验收分三层：实际 RTL 函数的 173872 组增量穷举及饱和边界检查；EXP-032 的 8263 条最终码／八状态连续记录；同一 Yosys JSON 网表的完整本地回放与独立 HDL 最终码检查。网表只导出 13 个结果 bit，不能把最终码核对称为综合网表的内部状态核对。

```powershell
wsl -d Ubuntu-20.04-D --cd /mnt/d/ADC -- bash experiments/exp_035_exact_update_rtl/simulate.sh artifacts/runs/EXP_035/exact_v1
python -m experiments.exp_035_exact_update_rtl.run artifacts/runs/EXP_035/exact_v1
python -m experiments.exp_034_generic_synthesis.replay artifacts/runs/EXP_035/exact_v1 --top online
python -m experiments.exp_034_generic_synthesis.export_scalar artifacts/runs/EXP_035/exact_v1/online/gates.json artifacts/runs/EXP_035/exact_v1/scalar/full_online
wsl -d Ubuntu-20.04-D --cd /mnt/d/ADC -- bash experiments/exp_035_exact_update_rtl/simulate_netlist.sh artifacts/runs/EXP_035/exact_v1/scalar/full_online 8263 600 128
python -m experiments.exp_035_exact_update_rtl.record_validation artifacts/runs/EXP_035/exact_v1
```

使用项目内已有 YoWASP Yosys 0.69、GCC 和 WSL Icarus 10.3。综合入口直接复用 EXP-034 的分步映射函数，检查原五个 RTL 文件摘要、工具及依赖版本、21 位输入／13 位输出／184 位状态一致。原候选的六文件综合边界只把顶层替换为专用连接，诊断输出仍不计入。摘要存放在 `summary.json`，成功仿真及源码摘要在 `validation.json`；任何失败、超时或缺失日志都不能记录为通过。

报告见 [EXP-035](../../docs/reports/experiments/EXP_035_EXACT_UPDATE_RTL_V1.md)。本实验仅比较通用逻辑结构，没有工艺面积、频率、功耗、四路抽取或芯片性能结果。
