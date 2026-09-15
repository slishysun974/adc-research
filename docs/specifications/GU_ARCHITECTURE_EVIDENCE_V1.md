# Gu ADC 架构证据基线 v1

> 状态：行为级冻结  
> 冻结日期：2026-09-15  
> 范围：静态可执行基线；不声称复原硅内部 bit-true 真值表

## 1. 冻结含义

本文件把 `GU_ARCHITECTURE_EVIDENCE_V0_1.md` 的逐项来源审计与 Gate A/B/C
结果合并为首个可执行基线。冻结表示后续实验必须显式引用一个配置版本，
不能无记录地改变信号域、阈值、CDAC 电平、dither 或重构权重。冻结不把
推导值升级成论文事实；获得新的作者资料或电路证据后允许产生 v2。

详细页码、版本差异和电路参数仍以 v0.1 证据表为审计底稿。本文件规定
哪些内容进入 v1 执行契约，以及每项可以作出多强的声明。

## 2. 论文支持的结构层

| 项目 | v1 取值 | 来源类别 | 执行处理 |
|---|---|---|---|
| 总体结构 | SHA-less 三级，12 bit，3 GS/s | paper_reported | 静态 v1 不模拟 SHA-less 时序 |
| 前两级 | 各为 3-bit flash + 开环 MDAC，增益约 4，1-bit 冗余 | paper_reported | 码表由下节候选层给出 |
| 后端 | 4-channel、8-bit TI-SAR | paper_reported | 理想 midrise，通道为 `n mod 4` |
| 双路径 | 前一级主路径驱动第二级 CDAC，辅助路径驱动第二级 flash | paper_reported | 3% 失配只进入第二级 flash 判决坐标 |
| 辅助系统增益差 | 约 3% | paper_reported | Q-007 扫描正负方向，不假设论文给出符号 |
| 随机 offset/增益失配 | Monte Carlo 标准差 20 mV/0.3% | paper_reported | trimming 前统计量，不作为硬边界 |
| 校准后温漂 | 标准差低于 0.5 mV/0.1% | paper_reported | Q-007 的 post-trim 漂移包络 |
| dither 代数方向 | 模拟 residue 相加，PWL 后数字相减 | paper_reported | 行为符号冻结；物理 PRNG 映射未决 |

## 3. Gate 验证后冻结的推导层

| 项目 | v1 取值 | 声明边界 |
|---|---|---|
| flash 状态 | 8 阈值、9 状态、`q=-4...4` | derived candidate，不是公开硅码表 |
| 阈值/CDAC | `t=(q+1/2)/4`，`a(q)=q/4` | 通过 Gate A/B residue 与冗余验证 |
| 级间重构 | `512*q1 + 128*q2 + c3 + 2048` | 通过 4096 码 Gate C 验证 |
| 默认 dither | 放大前 `+/-1/32`，数字 64/16 | 来源约束下的默认解释 |
| 替代 dither | 放大前 `+/-1/64`，数字 32/8 | 非默认、可证伪替代，不与默认混跑 |
| 电压映射 | 1 归一化单位 = 0.5 V differential | 高置信 derived interpretation |

默认与替代 dither 均通过数字恒等式测试，只说明各自内部自洽，不能据此
认为两种解释具有相同来源权重。

## 4. 未冻结的物理层

下列内容继续为显式开放问题：

- flash 内部 thermometer-to-binary 编码；
- CDAC 元件级权重与物理开关真值表；
- PRNG `0/1` 到 dither 电容的物理开关映射；
- `1/16 backend FSR` 是否被作者另行定义为总峰峰值；
- 硬件端点饱和、bubble、亚稳态和动态建立语义；
- 论文电压数值的逐字 single-ended/differential 标签。

这些缺口不阻止静态行为研究，但任何报告都必须使用“候选 A 行为级”或
`gu_behavioral_v1`，不能直接称为 Gu 芯片 bit-true 模型。

## 5. 版本纪律

正式运行应优先引用 `configs/architectures/gu_behavioral_v1.yaml`。旧的
`gu_nominal_v0_1_draft.yaml` 和 `gu_static_hypothesis_a_v0_1.yaml` 保留为
证据形成历史及 EXP-001 至 EXP-003 的复现输入，不在原地改写其已运行
含义。
