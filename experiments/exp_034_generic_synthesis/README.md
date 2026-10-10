# EXP-034：Gu 候选的通用逻辑综合基准

保持 EXP-031/032 的算法、Q1.10/Q3/Q22 算术和逐转换时序，比较两条只导出 `valid_out` 与最终 12 位码的链。冻结系数链的八个系数是输入，系数存储不计入；在线链保留八个 23 位累加器。此实验没有工艺库、器件、时钟约束或四路抽取。

固定版本工具安装在 **ADC 项目内**，无需修改其他工程或全局 Python：

```powershell
python -m pip install --target artifacts/tooling/yowasp --disable-pip-version-check --no-cache-dir -r experiments/exp_034_generic_synthesis/tool_requirements.txt
python -m experiments.exp_034_generic_synthesis.run artifacts/runs/EXP_034/generic_staged_v1
python -m experiments.exp_034_generic_synthesis.replay artifacts/runs/EXP_034/generic_staged_v1
```

综合使用 Yosys 0.69。粗综合后，执行 12 次 `techmap -max_iter 1` 与 `opt -fast`，最后确认全部逻辑已映为通用单元。提前消除常数逻辑，避免直接映射在线链时产生的大量中间展开。关闭 ABC，不把单元数当作标准单元面积。

Windows 本地回放使用已有 `gcc`，也可用 `replay --cc <编译器路径>` 指定兼容的 C 编译器。回放器只支持本实验实际保留的五种组合单元及两种同步复位／使能触发器；其他单元、重复驱动、组合环路或未知输出均不能通过。它对照既有 EXP-031/032 数字记录，另检查空闲周期、复位重放及故意损坏的参考输出。此前的 Python 向量须先存在，缺失时按 EXP-031/032 的入口生成。

用户确认恢复 WSL 授权后，使用 `Ubuntu-20.04-D` 内已有 Icarus 10.3，所有输出仍写 ADC。冻结链 RTL／网表各 18432 条、在线 RTL 8263 条及复位重放 128 条核对通过。原 Yosys 在线 Verilog 的运行未完成；清理别名后导出的原语实例版本也在 120 秒内未进入可观察的检查进度，根因尚未确定。

`export_scalar.py` 把原 JSON 网表的每个单元和引脚逐位写成 Verilog，保留 200629 个单元及 184 位状态，不改 RTL 或更新算术。`simulate_export.sh` 的 16 条定向记录及 16 条复位重放全部通过，另有 32 次空闲时钟和两级非法字检查；完整 8391 条在线网表检查仍见本地回放。最终成功计数和文件摘要由 `record_hdl_validation.py` 校验，不能把超时当成通过。

```powershell
wsl -d Ubuntu-20.04-D --cd /mnt/d/ADC -- bash experiments/exp_034_generic_synthesis/simulate.sh artifacts/runs/EXP_034/generic_staged_v1 frozen
wsl -d Ubuntu-20.04-D --cd /mnt/d/ADC -- bash experiments/exp_034_generic_synthesis/simulate.sh artifacts/runs/EXP_034/generic_staged_v1 online 128 rtl
python -m experiments.exp_034_generic_synthesis.export_scalar artifacts/runs/EXP_034/generic_staged_v1/online/gates.json artifacts/runs/EXP_034/generic_staged_v1/scalar/online
wsl -d Ubuntu-20.04-D --cd /mnt/d/ADC -- bash experiments/exp_034_generic_synthesis/simulate_export.sh artifacts/runs/EXP_034/generic_staged_v1/scalar/online 16 300 16
python -m experiments.exp_034_generic_synthesis.record_hdl_validation artifacts/runs/EXP_034/generic_staged_v1 --online-gate-directory artifacts/runs/EXP_034/generic_staged_v1/scalar/online --online-gate-rows 16 --online-gate-reset-rows 16
```

全输入形式等价证明与目标工艺时序分析未完成。报告见 [EXP-034](../../docs/reports/experiments/EXP_034_GENERIC_SYNTHESIS_V1.md)。
