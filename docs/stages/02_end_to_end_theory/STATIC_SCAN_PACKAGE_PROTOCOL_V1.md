# 三路静态扫描数据的接入与验收 v1

> 2026-10-05。此协议把[物理范围取证要求](PHYSICAL_ENVELOPE_EVIDENCE_GATE_V1.md)接到可运行的[离线验收器](../../../src/adc_research/evaluation/physical_scan_package.py)。它检查所提供资料的完整性、数学相容性及有限留出；不认证资料的物理真实性。真实 Cadence／芯片数据仍未取得。

## 提供什么数据

一个目录包含 `manifest.json`、建立范围的 `fit.csv`、独立核对的 `holdout.csv` 及说明最大斜率和误差依据的文件。文件名可以改变，实际名字和 SHA-256 写入 manifest。波形、仿真版本和条件记录仍须另行保存，说明文件应能追溯到它们。验收器接收已整理成下述字段的 CSV，不直接解析 Spectre PSF 或猜测导出列名。

每个允许条件必须有第一级主路 `stage1_main`、第一级辅助判决路 `stage1_auxiliary`、第二级主路 `stage2_main` 的两组数据。不同 PVT、通道、修调或历史条件分开编号；不能先混在一张曲线里丢掉标签。程序不把两个条件的曲线相交，而是在调用方明确选择条件集合后取输出范围的并集。

CSV 列按以下顺序排列：

```text
record_id,condition_id,path,input_voltage,input_error,output_lower,output_upper
```

电压为差分伏特，数值使用原始十进制或有理数字符串。`input_voltage` 是标称放大前输入，实际值在其 `±input_error` 范围内；`output_lower/upper` 覆盖该实际输入下所声明条件的所有允许输出。它们不是只表示均值、三倍标准差或置信区间。若噪声没有有限覆盖界，不能通过改字段名字得到最坏情况保证。记录编号在建立范围与留出文件之间不得重复，留出的标称电压也不得与建立网格相同。这只检查显式复用；改名、同源波形或事后选择仍需人工审查。

manifest 至少声明：

| 字段 | 含义 |
|---|---|
| `schema_version: 1` | 本格式版本 |
| `source.kind` / `description` | `synthetic`、`cadence` 或 `measurement`，及资料说明 |
| `model: static_memoryless` | 在每个声明条件内使用无记忆静态传输；动态资料需要另一种模型 |
| `error_semantics: all_allowed_outputs` | 输出区间声称覆盖全部允许输出；该声称需要独立证据 |
| `units` | 输入／输出 `V`、`definition: differential` 及正的 `volts_per_normalized_unit` |
| `fit` / `holdout` / `evidence` | 各自的 `file` 与 `sha256`；斜率／误差依据不能就是扫描 CSV 本身 |
| `evidence_description` | 依据、有效范围、误差口径及外部原始资料位置 |
| 每个 `conditions` 项 | `id`、工艺、供电、温度、通道、修调、噪声、历史、判决时刻标签 |
| 每条件的 `paths` | 三条路径的节点名、`slope_bound`、`slope_domain`、`required_domain`、`slope_provenance` |

`slope_bound` 是放大前到放大后电压的最大绝对斜率，单位为 V/V。其来源可以声明 `assumed`、`analytic`、`circuit_analysis` 或 `specification`；样点间最大割线或拟合斜率不接受为该界。数字校正 PWL 的斜率也不是模拟放大器斜率依据。来源字段只是供审查的标签，填写“电路分析”不会使程序认证该分析。

`slope_domain` 必须覆盖每个实际输入误差区间；网格的标称范围必须覆盖 `required_domain`。所有 manifest 数值同样用字符串，避免 JSON 浮点数在读入之前改变原始数值。顾氏候选的共同归一化参考目前为每单位 `0.5 V`，不是由验收器默认补入。三条路径采用同一参考；不同参考的资料需先明确转换。

完整可运行的示例由 [EXP-036](../../../experiments/exp_036_physical_scan_intake/generate_fixture.py)生成，来源明确写为人工合成，不能直接拿它当电路证据模板中的真实数据。

## 输入误差怎样进入输出范围

原网格理论假定扫描输入精确为 $x_i$。现在实际输入为 $w_i\in[x_i-e_i,x_i+e_i]$，观测输出在 $[l_i,u_i]$，并有独立依据给出整个有效域内的斜率界 $L$。由 Lipschitz 条件，

\[
|g(x_i)-g(w_i)|\le L e_i,
\qquad
g(x_i)\in[l_i-L e_i,\ u_i+L e_i].
\]

因此先把观测误差区间各端扩大 $Le_i$，再调用[网格到连续范围](../../theory/GRID_TO_ANALOG_ENVELOPE_V1.md)的上下锥形构造。没有输入误差界，输出波形误差再小也不够。此结论对每一个允许传输分别成立，不要求模拟传输为 PWL 或单调。

同一条件、同一标称输入若出现多条建立记录，其扩大后的范围应同时包含同一个静态传输在该点的允许输出，故取交集。交集为空时，静态假设、输入／输出误差或条件归属至少有一项不成立；程序不能仅凭这一点证明一定是动态记忆。不同条件不进行这种相交。

上述读取、扩大、网格相容性检查及锥形查询使用 `Fraction` 有理数，原始字符串精确表示的数值不会先转为二进制浮点。结果端点保留分数。`path_envelope` 连接原浮点静态传播器时，在最后把结果转为浮点，并逐端点向外取相邻可表示值。这个保护只认证该范围函数的输出；原浮点链的前后级加减、阈值运算及 FFT 仍没有完整数值证书。

需要保持扫描到最终码的精确算术时，使用 `rational_path_envelope(path, condition_ids)`。它要求归一化查询端点为 `Fraction`，在有理数上完成单位换算与条件并集，不转成浮点。配合 `propagate_rational_static_fixed_online_codes`，还须给显式有理数输入、模拟 dither、阈值、CDAC 和末级范围／阈值表，再接已有定点整数校准配置与初始状态范围。[EXP-037](../../reports/experiments/EXP_037_RATIONAL_STATIC_ONLINE_V1.md)完成了人工在线核对；条件和包含证明见[精确静态组合](../../theory/RATIONAL_STATIC_TO_FIXED_CODE_BOUNDS_V1.md)。端点类型不认证自定义回调内部算术，调用方须另审。该精确范围止于最终整数码及系数累加器，不能写成数值认证的 SNDR/SFDR 或物理保证。

## 留出怎样判定

在留出的输入误差区间上求预测范围 $P=[a,b]$，与独立记录的输出误差范围 $M=[l,u]$ 比较：

| 关系 | 结果 | 能说什么 |
|---|---|---|
| $M\subseteq P$ | `covered` | 此记录声称允许的输出全部被当前范围包含 |
| $M\cap P=\varnothing$ | `contradiction` | 两组范围不可能同时包含真实输出，至少一个前提有问题 |
| 相交但 $M\nsubseteq P$ | `inconclusive` | 真实值可能在交集内，也可能在预测范围外；不能算作通过或确定失效 |

仅有交点也属于相交。程序不自动扩大范围去包含失败的留出，因为那会改变已冻结的建立资料；修订后须重新分配独立留出。任何路径缺失、文件摘要不符、网格与 $L$ 矛盾、请求超出域或重复使用网格点都会拒绝。只有全部声明条件／路径的留出都为 `covered`，`package_checks_passed` 才为真；否则不提供可用于后续静态链路的条件并集接口。

## 运行与结论边界

```powershell
$env:PYTHONPATH='src'
python -m adc_research.evaluation.physical_scan_package path/to/package/manifest.json --output artifacts/runs/scan_audit.json
```

报告输出须在来源数据包目录之外；来源文件只读。成功退出码为 0，矛盾、不确定或格式错误为 1。`path_envelope(path, condition_ids)` 选择已声明的条件并取并集，返回现有三路静态传播器可调用的区间函数。它会要求每个选中条件都覆盖查询域，不跳过域不够的条件。

`physical_guarantee` 始终为假。真正升级物理结论仍须独立审查斜率与误差依据、条件覆盖、静态适用性、节点／时刻映射，以及 flash/CDAC/SAR 码制和在线抽取时序。有限留出通过也可能只是说明当前范围很宽；后续应检查最终码范围是否足以支持预定频谱目标。所有模拟数据留在离线 `evaluation/`，不能成为在线 Gu 更新的输入。
