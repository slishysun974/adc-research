# ADC 架构与数字校准硬件汇报包

本包用于检查现有 Gu 候选的结构、有限数字功能和综合报告。先阅读六页 PDF，再按本文打开工程、波形和短测试。可编辑 PPTX 保留架构图、公式、表格与逐页来源备注；PDF 是同一材料的静态导出。

本机已经安装 Vivado 2026.1 / XSim 和 MATLAB R2026a / Simulink；本次新增安装为 0。Vivado 位于 `D:\programs\2026.1\Vivado\bin\vivado.bat`。原项目位于 `C:\Users\17765\Desktop\曦源课题`，本轮正式集成代码位于工作副本 `rtl/gu_baseline/vivado_review/`。工程生成物和原始工具日志另存，不改变原 RTL 或历史实验。

## 打开与现场演示

将压缩包内容解压到短英文路径，例如 `C:/ADC_review`。下面所有路径相对于解压根目录。

1. 打开 `ADC_Circuit_Review.pdf`。重点说明两级主辅路径、后级到前级校正、旧系数读出与时钟沿更新，然后讨论真实负载和主辅一致性。
2. 在现有 MATLAB 中打开 `behavior/adc_behavioral.slx`。在 `behavior` 目录执行 `open_adc_demo` 可查看三个 Scope 并运行内嵌的默认短输入。这段默认短演示与最新百万训练性能协议不同；不要把它说成重现第 5 页的 SNDR。最新冻结结果见 `behavior/reduced_summary.json`、`performance_reduced_protocol.json` 和 `performance_figures/reduced_*`。全记录重新评分需原项目及其冻结运行数据，压缩包不携带百万训练原始 trace。
3. 在 Vivado 中打开 `hardware/project/gu_review.xpr`。综合顶层是 `gu_online_cost_top`，只输出有效位和最终 12 位码，内部保留八个 23 位 Q22 状态。打开 Synthesized Design → Schematic 沿 `calibration/correction`、`stage1_bank`、`stage2_bank` 检查。导出的矢量结构图在 `hardware/schematics/`；其中 `rtl_correction.svg` 是展开的 RTL 运算结构，`accumulator0_local.svg` 是第二级状态最低位附近的 11 个实际 FPGA 逻辑单元。它们不是模拟晶体管电路。
4. 在 Vivado Tcl Console 输入下面命令，查看已核对的八状态波形。替换解压路径，使用正斜杠及花括号：

```tcl
source {C:/ADC_review/hardware/show_states.tcl}
```

5. 现场重跑 RTL 短测试：

```tcl
source {C:/ADC_review/hardware/short_demo.tcl}
```

成功必须包含 `REVIEW_COST_PASS vectors=8391 idle_cycles=8391 reset_replay=128` 和 `REVIEW_SHORT_DEMO_PASS`，且没有 `Fatal:`。新日志/VCD 位于 `hardware/logs/demo_日期时间/`。这里检查最终码、有效位、复位重放及空闲保持；全部八状态的独立参考核对来自另一个测试平台和保存的在线 trace。

## 完整新建复算

保持交付包中的证据不变，选不存在的新目录，在 PowerShell 执行：

```powershell
& 'C:\ADC_review\hardware\rebuild.ps1' -NewRun 'C:\ADC_review_new'
# 若安装位置不同，追加 -Vivado 'D:\other\Vivado\bin\vivado.bat'
```

它复制源/向量到新目录，运行算术、bank、八状态、成本顶层 RTL 测试，再综合、输出报告/网表/DCP、回放同一综合网表，最后运行故意错误的负对照。Vivado 从安装 `bin` 目录启动，XSim 用相对向量路径以适配历史测试平台的 128 字节缓冲区。完整运行可能需要数分钟，现场优先用短测试。

XSim 的 `$fatal` 可能不改变 Vivado 主进程退出码；脚本同时检查实际 PASS / Fatal 日志。负对照故意改变第 0 行期望码最低位，正确结果是 `Fatal: cost output mismatch pass=0 row=0`，同时主脚本输出 `REVIEW_NEGATIVE_CONTROL_PASS`。已有 Python 可额外生成独立核对摘要；不需要新增 Python 包：

```powershell
python C:\ADC_review_new\validate.py C:\ADC_review_new --snapshot-only
```

仓库中的 `run.ps1` 与 `prepare.py` 用原 EXP-032 数字参考重新生成向量；交付包的 `rebuild.ps1` 则重用已经冻结的向量，不依赖原仓库。导出新结构图时，在 GUI 打开新工程后可运行 `hardware/export_schematics.tcl`；它针对脚本所在工程。`inspect_local.tcl` 会清理约束并重新综合，属于诊断入口，现场查看不必运行。

## 已通过的有限功能检查

| 检查 | 实际成功范围 |
|---|---|
| 精确更新算术 | 173872 个增量、869360 个饱和探针、173872 个禁用探针 |
| 单 bank 定向检查 | 22 组门限等值/邻点、两种 dither 极性及单位初值检查 |
| 在线链独立数字参考 | 8263 条记录，其中 1048 条无效；最终码、有效标记、门、学习输出和全部八状态逐转换匹配 |
| 成本顶层 RTL / 综合网表 | 各 8391 次输出检查、8391 个空闲周期、128 条复位重放 |
| 负对照 | 错误期望码在第 0 行被拒绝 |
| 搬移工程 | 12 个源文件/约束可解析；搬移后再次综合及短测试通过 |

连续数字向量是本轮调用未修改的 EXP-032 生成器所得的新记录，不称恢复了丢失的历史运行。`hardware/manifest.json` 保存初始运行的冻结哈希与协议；`hardware/integration_revisions.json` 说明兼容性修复；`hardware/review_protocol.json` 是有效约束合同。`assembly_manifest.json` 保存交付时各文件 SHA-256。历史初始日志保留失败，实际通过证据优先看带 `_repaired` 的日志/VCD，以及 `reports/rechecked/`。

## 两个讲解算例

PWL 示例：第二级分段宽度为 256 个 Q3 单位，正输入 300、前两段 Q1.10 系数 1024 / 1100。第一段偏移为 256，第二段局部输入为 44，最近偶数舍入 `44×1100/1024=47.265625` 得 47，故输出为 303 个 Q3 单位。这里的 300 / 303 不是伏特或最终 ADC 整数码。

更新示例：`vectors/online.txt` 零基第 7 行有 `Y2=120`、`d2=-1`、`j=1`。`T2=-64*d2*j*Y2=7680`，`Delta=floor((7680+62)/125)=61`，`A20` 从 4194304 更新到 4194365，而导出的 Q1.10 系数仍为 1024。本转换以旧状态评分，时钟沿写回，下一转换使用新状态。该行沿前最终码为 3535；对应图来自实际 `online_repaired.vcd`。

## 资源、时序与性能的边界

Vivado 2026.1 Build 6511674，器件 `xc7a100tcsg324-1`，保留层级，2548 LUT / 184 FF / 4 DSP48E1 / 0 BRAM。10 ns 展示时钟、输入与输出延迟各 1 ns、输出负载 1 pF；未添加引脚/板卡约束。早期尝试的 `set_input_transition` 不受 Vivado XDC 支持且被忽略，已从复算入口和有效 XDC 移除；清理后的再次综合资源/时序数值相同，网表原语类型、连接与参数规范化后完全一致。

100 MHz 展示约束**未满足**：WNS −50.309 ns、TNS −16860.232 ns；建立失败端点 557/561。WHS −0.079 ns，保持失败端点 44/561。`check_timing` 的无时钟/无输入输出延迟/未约束内部端点等项均为 0。报告的最长路径由 SAR 输入经过两级校正进入第一级更新 bank，数据路径估计 60.847 ns、78 级逻辑。布局布线、Fmax、板级和真实 ADC 速率尚未验收。

第 5 页 SNDR 45.2334→61.4768 dB、SFDR 53.0304→78.9052 dBc 来自已有浮点 full120 行为结果：人工静态三次传输、匹配主辅、1000080 次训练及 97.75390625 MHz 相干测试。保留 60 万次较高 SNDR 和终点回落、高段无更新支持。本轮逐转换定点 RTL 与其数值/调度合同不同，尚不能称这些性能由 RTL 实现。完整 ADC 晶体管电路还需要真实拓扑、尺寸、偏置、负载及 PDK；此次交付可供老师沿实际数字证据讨论下一步。

## 时序改进对照

主材料对应原基线。追加的两组独立结果在 `timing_trials/`：原 RTL 跨层映射为2645 LUT/184 FF/3 DSP、WNS −48.716 ns；PWL 位宽候选为2462 LUT/184 FF/2 DSP、WNS −47.996 ns。都完成相同功能/负对照核对，位宽候选额外完成1581056项原/候选 PWL 检查。两者都未满足100 MHz，详情见 `RESEARCH_RESULTS.md` 与 `timing_trials/timing_comparison.json`。

可打开各自的 `project/gu_review.xpr`，或 Vivado File → Open Checkpoint 查看 `checkpoints/gu_review_synth.dcp`。位宽候选源代码与本轮完整日志独立保存；原基线保持不变。重新生成位宽候选不需要新增 Python 包：

```powershell
python C:\ADC_review\timing_trials\scripts\prepare_width_trial.py C:\ADC_review\hardware C:\ADC_width_new
Push-Location 'D:\programs\2026.1\Vivado\bin'
& '.\vivado.bat' -mode batch -source 'C:\ADC_width_new\build.tcl' -log 'C:\ADC_width_new\logs\vivado.log' -journal 'C:\ADC_width_new\logs\vivado.jou'
Pop-Location
```

新目录必须不存在。该脚本先运行独立 PWL 预检，然后依次执行完整数字测试、综合和网表回放；通过标记来自实际日志，不只看主进程退出码。跨层映射试验使用原 `build.tcl`，唯一综合配置改动为 `ARGS.FLATTEN_HIERARCHY rebuilt`。本包没有加入流水级或改变窗口/系数反馈规则；这些方向需要先明确新时序合同。
