# ADC 架构与数字校准硬件汇报包

> 本文保留2026-10-11便携包的历史复现说明。2026-10-16的多拍整改使用独立顶层和新运行目录，见文末；旧包仍对应原逐转换实现和未通过的100 MHz综合结果。

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

## 2026-10-16多拍整改

用户已确认允许分多拍、优先保持原算法结果。新入口为[多拍RTL](../two_stage_multicycle_candidate_a.sv)，物理评估顶层为`gu_multicycle_cost_top`；原逐转换顶层继续可用。`fixed_gated_lms_exact_candidate_a`新增默认关闭的`EXTERNAL_COMMIT`与`EXTERNAL_DELTA`参数；多拍顶层采用外部提交和逐位除法算出的同一整数请求，原逐转换顶层保持原更新规则。

接口在`!reset && valid_in && ready_in`的上升沿E0接收样本；E16保存校正结果／门／学习量，E17登记带偏置分子，E18—E38逐位除125，E39同时提交两级状态、登记最终码并脉冲`done_out`。下一样本最早在E40接收，100 MHz下持续吞吐为2.5 MS/s。复位为同步高有效，取消在途事务并回到单位系数；释放后一个时钟沿拉高`ready_in`。无效数字样本仍产生完成脉冲，但`valid_out=0`、码／门／学习量为0，两个bank状态值保持。忙碌时输入不被接收；调用方必须遵守握手。旧17周期接收候选只存在于v1—v9冻结运行中。

两级计算始终使用接收该笔转换之前的同一组系数。不能将最后一拍的提交脉冲接到PWL的有效输入，否则有效信号会在最后一拍启动整个长算术链。16／15周期的建立／保持例外只从18位样本寄存器和184位状态寄存器，指向E16的53位中间寄存器；逐位除法、状态写回、计数器、就绪／完成、复位与外部IO均按单周期检查。原理依据为[AMD UG903同周期时钟的多周期路径规则](https://www.xilinx.com/support/documents/sw_manuals/xilinx2022_1/ug903-vivado-using-constraints.pdf)。

本机可用工具位于WSL `Ubuntu-20.04-D`的`/opt/Xilinx/Vivado/2022.1`。该安装有`xc7z020clg400-1`，缺少历史Artix-7器件库。新结果必须注明所用器件，不替代原Artix-7验收。运行目录必须不存在；以下命令在WSL中从仓库根执行，不覆盖旧证据：

```bash
python3 rtl/gu_baseline/vivado_review/prepare_multicycle.py \
  artifacts/research/circuit_review/timing_new --part xc7z020clg400-1
adc_run="$PWD/artifacts/research/circuit_review/timing_new"
bash "$adc_run/sources/simulate_multicycle.sh" "$adc_run"
/opt/Xilinx/Vivado/2022.1/bin/vivado -mode batch \
  -source "$adc_run/sources/build_multicycle.tcl" \
  -log "$adc_run/logs/vivado.log" -journal "$adc_run/logs/vivado.jou" \
  -tclargs "$adc_run"
bash "$adc_run/sources/simulate_routed.sh" "$adc_run"
```

约束固定10 ns时钟、IO延迟min 0.2／max 1 ns、1 pF负载、LVCMOS33／FAST／12 mA；最终码／有效／完成的14个寄存器放入IOB。物理顶层用MMCM的10倍／10分频维持100 MHz，通过全局反馈补偿时钟网络偏差，锁定信号经两级同步后释放核心复位。该顶层复位释放后需等待`ready_in`，不能套用裸核心的单拍释放时间。器件原语及频率关系见[AMD UG953](https://docs.amd.com/r/2022.1-English/ug953-vivado-7series-libraries/MMCME2_BASE)。

没有板卡引脚合同，不生成板卡bitstream。`build_multicycle.tcl`检查例外端点数量并输出综合、布局布线、时钟、约束完整性、DRC、DCP与SDF。仿真脚本要求实际PASS文本，正向仿真、编译及展开均拒绝Warning／Error／Fatal及建立保持告警；错误第0行的负对照必须失败。PASS与仿真调度告警并存不算通过。复现脚本对目标器件缺失、时序失败或仿真失配直接报错。布线仿真按实际BUFG工作时钟计事务，在该沿后1 ns驱动待接收输入，在后续接收／提交沿后9.2 ns检查实际输出；外部参考相位下的IO建立／保持由STA独立检查。它保留转换间空闲拍，裸核心测试另检查40周期最短接收间隔。

物理验收顶层只导出就绪、完成、有效及最终码；裸核心检查八状态、门及学习量，v10另在布线DCP导出的功能网表通过层次引用逐笔核对八状态及53位中间寄存器，没有增加硬件端口。该功能网表全量通过不能替代时序网表回放。导出额外诊断寄存器或改变计算周期时，须同步调整约束并重新验收。当前综合映射禁止使用DSP块，`build_multicycle.tcl`与冻结清单均采用上限0；具体隔离原因与最终资源见报告。

详细整改过程、结果与失败记录见[本轮报告](../../../docs/reports/RTL_MULTICYCLE_TIMING_2026-10-16.md)。

### 同一v10网表／SDF的跨版本短核对

准备阶段的25项离线控制保持。随后实际WSL重试已完成Bash语法检查、原语回放及原2022.1第34行失败校准；同一前级学习量／门失配复现，**完整SDF仍未通过，另一版本交叉核对尚未开始**。本次日志与指纹见`artifacts/research/circuit_review/timing_crosscheck_20261017_retry_v1/actual_retry.json`。不要重新综合或改变SDF。若需重新准备可搬移包，从仓库根运行，输出目录必须不存在：

```bash
python3 rtl/gu_baseline/vivado_review/prepare_timing_crosscheck.py prepare \
  artifacts/research/circuit_review/timing_multicycle_20261017_v10 \
  artifacts/research/circuit_review/timing_crosscheck_new
```

本次最终包为`artifacts/research/circuit_review/timing_crosscheck_20261017_v1/bundle_v3`。先在原2022.1上校准新测试平台，预期在零基第34行报告`CROSSCHECK_ROW34_MISMATCH`并退出失败；原语回放应先通过。若未重现，停止跨版本归因，保留日志查明测试平台差别。

```bash
adc_bundle="$PWD/artifacts/research/circuit_review/timing_crosscheck_20261017_v1/bundle_v3"
bash -n "$adc_bundle/run_xsim.sh"
bash "$adc_bundle/run_xsim.sh" \
  /opt/Xilinx/Vivado/2022.1/settings64.sh /opt/Xilinx/Vivado/2022.1 \
  "$PWD/artifacts/research/circuit_review/crosscheck_baseline_new" pilot
```

随后显式设置`ADC_ALTERNATE_SETTINGS`为实际另一版本的`settings64.sh`绝对路径，再运行候选短核对；原2022.1目录用于编译同一官方CARRY4源码及原语用glbl，不加载原版本的编译产物。候选其他预编译原语库属于候选安装，路径／版本与源指纹单独记录，不能称为只改变引擎的实验。

```bash
bash "$adc_bundle/run_xsim.sh" \
  "${ADC_ALTERNATE_SETTINGS:?set the actual alternate settings64.sh path}" \
  /opt/Xilinx/Vivado/2022.1 \
  "$PWD/artifacts/research/circuit_review/crosscheck_candidate_pilot_new" pilot
```

原语与第34行正负控制均通过才打印`CROSSCHECK_PILOT_CONTROLS_PASS`。只在该结果成立后，改用新的结果目录和最后参数`full`运行一次完整阶段；该调用先重复原语与短控制，再做8263／128／38完整比较及第0行负对照。通过仅打印`CROSSCHECK_SLOW_MAX_CONTROLS_PASS`，仍不是四角或板级验收。任何Warning／Error／无SDF成功注释／超时都拒绝正向通过。每个安装最多短、完整两次调用；不安装工具、不覆盖旧目录，不自动续扫其他参数。调用方另保存命令退出码，完整结果须连同所有编译／展开／仿真日志审查，不能只凭PASS文本更新STATUS。

### 论文功能边界分段候选

正式源码为`../fixed_pwl_staged_candidate_a.sv`、`../two_stage_staged_candidate_a.sv`；单PWL只验段宽256／1024，核心按COMPUTE_CYCLES=16保持E39／40。当前功能／单周期STA通过，完整SDF在221行失败；第9节已实际定位E17前分子／符号并在2019.1／2022.1复现。不要把短PASS、软件自检或跨版本相同失败当完整验收。来源、证明关系及失败见整改报告第8节。

本机冻结目录为`artifacts/research/circuit_review/timing_staged_20261017_v3`，内含sources、原向量、build_staged.tcl、实际网表、报告与tools。重算必须用新目录，仅复制sources、manifest.json、online.txt及negative.txt并新建logs，不能覆盖该证据目录。冻结物理顶层已实例化分段核心，构建清单选用它。Linux命令（adc_new为新的完整运行目录）：

```bash
bash "$adc_case/tools/run_staged_rtl.sh" "$adc_new"
bash "$adc_case/tools/run_staged_build.sh" "$adc_new"
```

上述构建保持10ns、同IO负载、max_dsp4，无MCP或false-path例外。实际运行前核对manifest源码与向量SHA。网表184＋53位观察接线生成与SDF入口原脚本也在tools，当前固定本机v3路径；移植时先明确目标新目录并保留改动指纹，不对原记录直接重跑。结果不是板级或ASIC验收，也不是原v10故障归因。

### 2026-10-17分子定位与实际软件环境

本轮证据为`artifacts/research/circuit_review/timing_staged_crossversion_20261017_v1/`。原2022.1为`/opt/Xilinx/Vivado/2022.1/settings64.sh`；独立安装的2019.1为`/opt/Xilinx/alternate2019/Vivado/2019.1/settings64.sh`。该旧版当前Ubuntu20／WSL环境不属于其官方OS列表，只作实际诊断；其他原语库随安装变化，不作纯引擎因果实验。

目录内`tools/run_staged_crossversion.sh`接受安装settings、新结果绝对路径、`baseline`或`candidate`和`pilot`或`full`。它先冻结同一网表／SDF／向量与222行停止测试平台，正向及第221行负对照通过才可全量；本轮两版均在221行失败，没有执行候选负对照／全量。保存的2022.1旧入口有日志门禁错误，真实退出1及同日志复核记录见`paired_2022/result.json`，不对旧目录重跑。

`tools/run_seed_probe.sh`和`run_2019_seedprobe.sh`记录实际有限探针，含本机原快照绝对路径，移植前先另建目录、核对输入指纹和时刻，不覆盖任何证据目录。2019.1实际编译快照另保留在`/opt/Xilinx/rtl_checks/staged_2019_20261017_v1`。两版27×60个采样值相同；这些是有限连接线观察，不是原语内部连续历史。

CVC二进制在`/opt/Xilinx/alternate_simulators/open-src-cvc/build64/cvc64`，固定源码与许可留在该目录。`software/`保留安装配置、成功日志、零器件拒绝日志、构建告警和两种随包自检日志；`cvc_primitive/`保存35101事件／79稳定值以及3条未屏蔽告警。CVC忽略PATHPULSE，不能替代当前脉冲合同；本轮未做CVC整网表回放。源码、DCP、原SDF不改，原训练／留出和完整SDF未完成状态保持。
