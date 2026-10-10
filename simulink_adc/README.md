# ADC 行为级 Simulink 模型

这个目录把项目现有 Python 行为模型独立实现为可编辑的 Simulink 信号流程。主文件是 [adc_behavioral.slx](adc_behavioral.slx)。模型内保存默认参数、4096 条输入和 dither；直接打开、运行即可，不需要在仿真过程中调用 Python。

GitHub 交付包含模型、`blocks/` 内嵌函数源、建模／运行／核对／绘图脚本、参数协议和结果摘要。实验结果图只保留最新减小非线性及学习率的六组 PNG／SVG（`performance_figures/reduced_*`）；模型结构图单独保留。旧结果图、`performance_runs/`／`validation_runs/` 原始记录、MATLAB 缓存和 `.deps/` 依赖留在本地。报告中的本地路径不是仓库下载链接，完整 trace 可按复算命令重新生成。

## 打开与查看

在 MATLAB 中把当前目录切换到本目录，执行：

```matlab
open_adc_demo
```

或者双击 `adc_behavioral.slx`，点击 Run。双击子系统查看其内部模块。三个 Scope 分别显示主辅残差、校正前后码和两组数字 PWL 系数。完整信号还写入仿真结果的 `stimulus_trace`、`physical_trace`、`digital_trace` 和 `learning_trace`。

默认演示采用已有 EXP-057 的 `both_smooth` 人工模拟曲线、四点／120 次转换的 `point30` 更新候选。它展示机制及实现一致性，不表示这段短记录已经收敛，也不承诺校准必然提高该记录的性能。

## 信号流程与对应源码

| Simulink 模块 | 对应 Python | 可查看的信号 |
|---|---|---|
| `Stage_1`、`Stage_2` 的 Flash | `platform/quantizer.py` | 8 路温度计判决、九态 symbol、region；阈值等值取高区间 |
| CDAC、Residue_sum | `platform/cdac.py`、`stage.py` | 名义 DAC、失配、dither、放大前残差 |
| Actual_gain、Analog_transfer | `platform/amplifier.py` | 线性增益、独立模拟 PWL 或平滑三次传输、静态目标 |
| Finite_establishment、Previous_residue | `finite_settling.py`、`two_phase_dual_path.py` | 前次残差、跟踪相起点、建立后输出 |
| `Auxiliary_path` | `pipeline.py`、`dual_path_settling.py`、`two_phase_dual_path.py` | 静态仿射辅路，或独立有历史的辅路 |
| `SAR_8bit` | `backend_sar.py` | raw、centered、四路轮询 channel、量化电压 |
| `Digital_correction` | `calibration/pwl.py`、`two_stage.py` | 后级 PWL、局部扣 D2、前级 PWL、局部扣 D1、偏置与裁剪 |
| `Gu_background_update` | `gated_lms.py`、`adaptive_two_stage.py` | 旧系数、门限、门、相关乘积、窗口提交、下一系数、实际观测数 |
| `Overload_and_clipping` | `reconstruct.py` 及离线评分语义 | 17 个过载、裁剪和可纠正标记 |

模拟求和、增益、数字权重、dither 减法、输出裁剪和状态延迟是原生 Simulink 块。判决表、分段传输及窗口更新使用短 MATLAB Function 块；源码保存在 `blocks/`，同时嵌入 `.slx`。模型没有一个封装整个 ADC 的黑箱，也不把 Python 输出接到模型输出端。

数字算法只接收两级 symbol、SAR centered code、dither tag 和自身状态。理想输入、模拟参数、模拟过载与 Python 参考结果均未接入数字学习器。参考结果只在仿真完成后用于比较和绘图。

## 数值与时序约定

一个离散 tick 表示一次 ADC 转换，时间 `n` 对应 Python `sample_index=n`。固定离散求解器、步长 1，不使用连续积分或输入插值。图中横轴是转换序号；离线频谱采用已有演示口径 3 GHz，而不是把 tick 当成 1 秒的物理采样。

前级默认 `q∈{-4,…,4}`，`DAC=q/4`，`r=4*(main-DAC+d)`；后端 `c3=clip(floor((r2+1)/(2/256)),0,255)-128`。模拟非理想项保持原代码组合顺序。数字链为：

```text
c3 → PWL2 → +128*q2 → -D2 → PWL1 → +512*q1 → -D1 → +2048 → clip[0,4095]
```

PWL 分段宽度为 128／32；负满量程延伸最后一段，正满量程拒绝。冻结系数和在线输出是原 Python 的浮点数，未额外整数化。未校正支路保留原整数重构。

`C.digital_mode`：0 为旁路，1 为冻结，2 为逐转换更新，3 为 point30，4 为 full120。point30 每 120 次转换只选位置 0、1、2、3，并在位置 119 同时提交两个 bank；full120 选全部转换。步长来自 EXP-057，point30 的乘 30 和按整块观测数归一化保持原候选合同。当前转换始终用旧系数，提交后的系数经 Unit Delay 在下一转换生效。动态状态在所有转换推进，未选作学习观测的样本也不跳过。

在 MATLAB 中修改模式的例子：

```matlab
mw = get_param('adc_behavioral','ModelWorkspace');
C = evalin(mw,'C');
C.digital_mode = 4;
assignin(mw,'C',C);
result = sim('adc_behavioral');
```

`C` 的两级阈值、DAC 失配、实际增益、模拟传输和建立参数也可修改。修改后只有重新运行核对才能声称与对应 Python 配置一致。`build_adc_model` 会从原配置及参考清单重建模型，覆盖手工改动；手工探索前可另存 `.slx`。

## 一键复算一致性

需要 MATLAB/Simulink（已在 R2026a Update 2 验证）、Python ≥3.10、NumPy、PyYAML。不需要 DSP、Fixed-Point、Simscape 或 HDL 工具箱。当前机器可复用本目录 `.deps` 中的 PyYAML；该依赖和原始运行产物不入 Git。

首次在新机器复算，先在项目根目录安装本项目声明的 Python 依赖：

```powershell
python -m pip install -e .
```

从项目根目录执行：

```powershell
.\simulink_adc\run_validation.ps1
# 也可显式指定解释器：
.\simulink_adc\run_validation.ps1 -Python 'C:\path\to\python.exe'
```

脚本在新的 `validation_runs/<日期时间>/` 中依次保存原 Python 输出、Simulink 输出、MATLAB 日志、图和逐字段误差报告；已有运行目录不会覆盖。脚本先构建 `.slx` 再运行核对，失败会停止并保留记录。验收前冻结的条件见 [validation_protocol.json](validation_protocol.json)，结果见 [VALIDATION.md](VALIDATION.md)。

`python_reference.py` 调用现有正式 Python 模块产生参考，不另写一套近似 ADC。两端使用同一份精确保存的输入及 dither。离散码、判决、门、计数和标记要求完全相等；模拟电压和校准浮点运算采用预定绝对误差限，不能把浮点容差通过说成逐位相同。CSV 使用 17 位有效数字，矩阵信号按转换展开；每个标量字段的名称和顺序写在运行 `manifest.json` 中。

## 适用范围

校准前后频谱、两级系数演化和信号波形见 [性能演示报告](PERFORMANCE_DEMO.md)。本次最终浮点 SNDR 为 46.4741→58.3381 dB、SFDR 为 53.9609→64.9478 dBc；数字输出／学习与原 Python 全相等，少量模拟电压最大差 4.44×10⁻¹⁶。性能演示使用 [performance_protocol.json](performance_protocol.json) 中独立冻结的参数与预算。复算入口：

```powershell
.\simulink_adc\run_performance.ps1
```

追加的三倍三次非线性与谐波分析使用独立冻结的 [performance_harmonics_protocol.json](performance_harmonics_protocol.json)，测试频率改为约97.75MHz以分开谐波。已完成运行：SNDR 42.23→54.43 dB，HD3／HD5／HD19 分别降低 7.30／8.42／11.95 dB；[谐波图与完整分析](PERFORMANCE_DEMO.md#增强增益非线性后的谐波对比)、[数据摘要](harmonic_summary.json)。复算命令：

```powershell
.\simulink_adc\run_performance.ps1 -Protocol .\simulink_adc\performance_harmonics_protocol.json
```

最新减小非线性及学习率的 [协议](performance_reduced_protocol.json) 将上一组的三次项减半、学习率降为1/4；同一97.75MHz测试与训练预算下，SNDR 45.23→61.48 dB，SFDR 53.03→78.91 dBc。[结果与新旧对比图](PERFORMANCE_DEMO.md#减小非线性及学习率后的结果)、[数据摘要](reduced_summary.json)。复算命令：

```powershell
.\simulink_adc\run_performance.ps1 -Protocol .\simulink_adc\performance_reduced_protocol.json
```

性能运行器按所选协议配置两级模拟三次传输和学习率；HD2–HD31的dBFS、dBc与抑制量均在离线评分中计算，原默认协议和已保存基线不被替换。

该入口调用原 Python 核心生成参考，再用原 `.slx` 独立训练并传递自身系数，比较全部记录信号；同一正弦在固定检查点冻结评分。图使用 MATLAB 原生绘图导出 PNG／SVG，原模型的内置演示不被覆盖。完整参考与原生记录分别保存在新的 `performance_runs/<日期时间>/` 中，不能拿 Python 系数给 Simulink 代跑学习。该演示采用 full120 浮点候选，额外整数化仅属于离线评分。

对原论文的主辅路径和逐级校准核查见 [验收记录中的论文核对](VALIDATION.md#与原论文的主辅路径及两级校准核对)。顶层 `Digital_correction` 内已有 `PWL_stage_2` 和 `PWL_stage_1`，分别使用两组四段系数；它们在数字域依次校正第二级和第一级放大误差。`Gu_background_update` 的两个 bank 分别学习，不能把顶层一个子系统理解为一套最终码统一校准。双击数字与学习子系统即可看到这些连接。

这是对现有静态、单相主路径、独立主辅单相和两相行为候选的浮点迁移。已实现阈值偏移、DAC 失配、dither、增益误差、模拟 PWL／三次曲线，以及冻结／在线两级数字校正。现有 Q3、Q1.10、Q22 定点和 RTL 候选不属于这个 `.slx`，连续后端离线 oracle 也没有接入在线路径。

目前支持加入模拟 CDAC 失配和 Flash 阈值偏移，但没有实现论文完整数字引擎的前景电容权重提取／数字校正、比较器前景修调或 SAR 通道失配校准。默认 `Auxiliary_path` 是静态仿射近似，默认 point30 提交时序是项目候选。两级 PWL／gated-LMS 的原理及级联结构一致，不代表完整论文电路或校准引擎已经复原。

仿真一致只证明指定行为合同下的程序一致；模拟曲线、建立参数、辅路和提交时序仍是已有研究假设，不能升级为芯片准确性、硬件成本或长期收敛结论。本目录的浮点性能演示不执行已批准静态定点研究计划的长记录任务，不搬动冻结 Python 实验与原始数据。
