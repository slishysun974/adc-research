# Gu ADC 架构证据表 v0.1

> 状态：可审阅草案，尚未冻结  
> 建立日期：2026-09-14  
> 主证据：Gu et al., OJSSCS 2026  
> 交叉证据：Gu et al., ISSCC 2025 论文与 63 页演示稿

## 1. 证据使用规则

本表只记录能够追溯到现有本地资料的架构信息。来源类别采用：

- `paper_reported`：论文或演示材料明确给出；
- `derived`：由多个已报道量直接推导；
- `assumed`：为建立模型而暂定，不能冒充论文参数；
- `unresolved`：现有公开材料不足以确定。

当 2025 ISSCC 材料与 2026 OJSSCS 扩展稿不一致时，默认以内容更完整、时间更晚的 OJSSCS 扩展稿为当前主证据，并保留差异记录。页面号按 PDF 页码计。

## 2. 系统与逐级结构

| ID | 参数或结构 | 当前值/描述 | 来源类别 | 证据定位 | 置信度 | 建模处理 |
|---|---|---|---|---|---|---|
| SYS-001 | 标称分辨率 | 12 bit | paper_reported | OJSSCS 摘要；Fig. 13 | 高 | 输出接口按 12-bit 设计 |
| SYS-002 | 采样率 | 3 GS/s | paper_reported | OJSSCS 摘要、Sec. III-A | 高 | `fs_hz = 3e9` |
| SYS-003 | 工艺 | 28-nm CMOS | paper_reported | OJSSCS 摘要、Sec. IV | 高 | 仅作来源元数据，不进入首版行为方程 |
| SYS-004 | 输入满量程摆幅 | 1 Vpp | paper_reported；差分解释为 derived | OJSSCS pp. 6-8、Fig. 14；ISSCC slides p.38 | 高（数值）；中高（差分解释） | Fig. 14 明确为单端示意且实际路径为差分；候选 A 采用系统差分 1 Vpp，仍注明正文未逐字写 differential |
| SYS-005 | 总体结构 | SHA-less、三级流水线 | paper_reported | OJSSCS Sec. III-A、Fig. 13 | 高 | 首版静态模型忽略 SHA-less 时序效应，但保留开关 |
| SYS-006 | 有效位数组合 | 2 + 2 + 8 = 12 | derived | 前两级各 3-bit 且各含 1-bit 冗余，末级 8-bit | 高 | 只冻结位数恒等式，不据此猜测码表 |
| ST1-001 | 第一级子 ADC | 3-bit flash | paper_reported | OJSSCS Sec. III-A、Fig. 13 | 高 | 阈值与输出映射使用外部表配置 |
| ST1-002 | 第一级残差放大 | 开环 MDAC，标称级间增益约 4 | paper_reported | OJSSCS Sec. III-A、Fig. 13 | 高 | 首版 `gain_nominal = 4` |
| ST1-003 | 第一级冗余 | 1 bit | paper_reported | OJSSCS Sec. III-A | 高 | 验收必须单测可纠正范围与失效边界 |
| ST1-004 | 第一级单端采样电容 | 480 fF | paper_reported | OJSSCS Sec. III-A、Fig. 13 | 高 | 元数据；后续用于 kT/C 与 mismatch 扩展 |
| ST1-005 | 双路径放大 | 主路径驱动下一级 CDAC，辅助路径驱动下一级 flash | paper_reported | OJSSCS Fig. 13；ISSCC slides pp.37-42 | 高 | 首版静态理想模式令两路径输入等价；后续独立加入路径增益/失调 |
| ST1-006 | 主/辅放大器尺寸比 | 5:1 | paper_reported | OJSSCS Fig. 13；ISSCC slides pp.37-38 | 高 | 只作电路元数据，不直接解释成精确增益比 |
| ST2-001 | 第二级子 ADC | 3-bit flash | paper_reported | OJSSCS Sec. III-A、Fig. 13 | 高 | 阈值与输出映射使用外部表配置 |
| ST2-002 | 第二级残差放大 | 开环 MDAC，标称级间增益约 4 | paper_reported | OJSSCS Sec. III-A、Fig. 13 | 高 | 首版 `gain_nominal = 4` |
| ST2-003 | 第二级冗余 | 1 bit；文中给出 62.5 mV 冗余量 | paper_reported | OJSSCS Sec. III-A | 中 | 62.5 mV 的精确参考节点/单端差分口径待澄清 |
| ST2-004 | 第二级单端采样电容 | 80 fF | paper_reported | OJSSCS Sec. III-A、Fig. 13 | 高 | 元数据；为第一级的 1/6 |
| BE-001 | 后端结构 | 4-channel time-interleaved SAR | paper_reported | OJSSCS Sec. III-A、Fig. 13 | 高 | 每个样本记录 `channel_id = n mod 4` |
| BE-002 | 后端分辨率 | 每通道 8 bit | paper_reported | OJSSCS Sec. III-A、Fig. 13 | 高 | 首版理想均匀量化器；真实 SAR 码制另行配置 |
| BE-003 | 后端采样电容 | 约 20 fF | paper_reported | OJSSCS Sec. III-A、Fig. 13 | 高 | 元数据 |
| BE-004 | 后端单位电容 | 0.15 fF | paper_reported | OJSSCS Sec. III-A | 高 | 元数据 |
| BE-005 | 后端时序失配 | 转换保持信号，因此架构上免受输入 timing skew | paper_reported | OJSSCS Sec. III-A | 高 | 首版关闭 TI timing-skew；仍保留通道增益/失调接口 |

## 3. 时序、双路径与电路级锚点

| ID | 参数 | 当前值 | 来源类别 | 证据定位 | 备注 |
|---|---|---|---|---|---|
| TIM-001 | 跟踪相位 | 150 ps | paper_reported | OJSSCS Sec. III-A | 与下列相位合计 330 ps，3 GS/s 周期约 333.3 ps |
| TIM-002 | 量化与 DAC switching | 60 ps | paper_reported | OJSSCS Sec. III-A | 首版仅记录，不模拟连续时间 |
| TIM-003 | 放大相位 | 100 ps | paper_reported | OJSSCS Sec. III-A | 首版静态模式假定完全建立 |
| TIM-004 | 非交叠裕量 | 20 ps | paper_reported | OJSSCS Sec. III-A | 与 3.3 ps 未分配差额一起作为时序容差记录 |
| AMP-001 | 第一级主放大器跨导 | 70 mS | paper_reported | OJSSCS Sec. III-B | 电路级锚点 |
| AMP-002 | 第一级主放大器负载电阻 | 80 ohm | paper_reported | OJSSCS Sec. III-B | 电路级锚点 |
| AMP-003 | 输入寄生导致的衰减因子 | 约 0.7 | paper_reported | OJSSCS Sec. III-B | 与 `gm * R` 一起解释约 4 倍增益 |
| AMP-004 | 主路径建立要求 | 10-bit accuracy / 100 ps / 11 GHz | paper_reported | OJSSCS Table 1 | 动态模型候选锚点 |
| AMP-005 | 辅助路径建立要求 | 5-bit accuracy / 80 ps / 7 GHz | paper_reported | OJSSCS Table 1 | OJSSCS 数值优先于 slides p.43 |
| AMP-006 | 辅助路径系统性增益失配 | 约 3% | paper_reported | OJSSCS Sec. III-A | 首版双路径非理想测试候选 |
| AMP-007 | 辅助路径随机失调标准差 | 20 mV | paper_reported | OJSSCS Sec. III-A | Monte Carlo 电路结果，不等同于硅后分布 |
| AMP-008 | 辅助路径随机增益失配标准差 | 0.3% | paper_reported | OJSSCS Sec. III-A | Monte Carlo 电路结果 |
| REF-001 | 参考电压轨 | 0/1 V | paper_reported | OJSSCS Sec. III-B | 物理 CDAC 模型需结合单端/差分定义使用 |

## 4. 校准实现证据（为阶段一预留接口）

| ID | 参数或流程 | 当前值/描述 | 来源类别 | 证据定位 | 建模处理 |
|---|---|---|---|---|---|
| CAL-001 | dither | 前两级各注入一个 1-bit 伪随机 dither | paper_reported | OJSSCS Sec. III-A、Fig. 13 | 理想静态模式关闭；校准模式记录序列和符号 |
| CAL-002 | dither 幅度 | 后端满量程的 1/16 | paper_reported | OJSSCS p. 6；ISSCC p. 428；slides pp. 38, 45 | 候选 A 将每个二值电平解释为 +/-FSR/16，推出放大前 +/-1/32、后端输入 +/-1/8；原文未给物理开关真值表 |
| CAL-013 | dither 代数方向 | `Vd` 在模拟残差端相加，PWL 校正后减去 `Dd` | paper_reported | OJSSCS Figs. 4-5、p. 4；ISSCC Fig. 24.1.3 | 行为级符号约定可冻结；PRNG `0/1` 与 CDAC 开关的物理映射仍未公开 |
| CAL-003 | PWL 分段数 | 4 slices | paper_reported | OJSSCS Sec. II-C、Fig. 10 | 作为 Gu 基准；通用接口允许其他分段数 |
| CAL-004 | PWL 连续性 | `b_n = b_0 * sum(k_i, i=1..n)` | paper_reported | OJSSCS Eq. (2)-(3) | 可直接写单元测试 |
| CAL-005 | 一阶系数更新 | `k1[n+1] = k1[n] - mu1*Dd[n]*Dout[n]` | paper_reported | OJSSCS Eq. (5) | 浮点参考实现公式 |
| CAL-006 | 高段系数门控 | 第 i 段使用由前序 `k` 决定的自适应下阈值 | paper_reported | OJSSCS Eq. (7)、Fig. 10 | 等号归属按统一半开区间规则实现并测试 |
| CAL-007 | 首级后端原始码 | 二、三级组合为 10-bit；正半轴用于 4-slice 时为 9-bit | paper_reported/derived | ISSCC paper Fig. 24.1.2 说明；OJSSCS Sec. II-A/III-C | 有符号表示尚未公开，不能只凭位宽猜测 |
| CAL-008 | 4-slice 数字参数示例 | `b0=128`；`k_i` 为 [0,2] 内 11-bit 定点、10 个小数位；计算保留 3 个小数位 | paper_reported | OJSSCS Sec. II-A、III-C | 仅在码制确认后启用 bit-true 模式 |
| CAL-009 | 数字并行度 | 4 路处理单元，每路 750 MHz | paper_reported | OJSSCS Sec. III-C、Fig. 18 | 样本值参考模型与硬件调度模型分层 |
| CAL-010 | 系数更新抽取 | 四路处理输出再 decimate by 30 | paper_reported | OJSSCS Sec. III-C、Fig. 18 | 等效全速样本更新率需结合四路交织调度核验 |
| CAL-011 | 校正级联次序 | 先校正 SAR/第二级得到第一级输出码，再校正第一级 | paper_reported | OJSSCS Sec. III-C、Fig. 18 | 软件接口必须显式保留该顺序 |
| CAL-012 | 电容权重获取 | 上电前景、片外提取，并归一化到固定满量程 | paper_reported | OJSSCS Sec. III-C | 首版可支持“真值已知校正”，不模拟提取过程 |

## 5. 版本差异与取值原则

| 项目 | ISSCC 2025 | OJSSCS 2026 | 当前处理 |
|---|---|---|---|
| 辅助路径精度 | slides p.43：4 bit | Table 1：5 bit | 采用 5 bit；保留差异 |
| 主路径带宽 | slides p.43：12 GHz | Table 1：11 GHz | 采用 11 GHz |
| 辅助路径带宽 | slides p.43：6 GHz | Table 1：7 GHz | 采用 7 GHz |
| 单路径功耗/节省 | slides p.43：12 mW、节省 40% | Table 1：8.3 mW、节省约 15% | 采用扩展稿表格 |
| 芯片总功耗 | ISSCC paper：32.5 mW | OJSSCS：50.5 mW（含 18 mW 输入缓冲） | 性能比较必须注明是否计入输入缓冲 |
| 核心面积 | ISSCC paper：0.04 mm2 | OJSSCS：0.044 mm2 | 采用 0.044 mm2 |
| FoMS/FoMW | 165 dB / 15.2 fJ/conv-step | 164 dB / 23.7 fJ/conv-step | 采用扩展稿口径；不混算 |

## 6. 现阶段可以冻结与不能冻结的内容

可以进入首版软件规格的高置信内容：三级结构、2+2+8 有效位数组合、两级标称增益 4、两级 1-bit 冗余、采样电容、后端 4x8-bit TI-SAR、静态与动态模型的边界、校准级联顺序。

在补充推导或显式批准假设前不能冻结：

- 3-bit flash 的精确阈值数量、阈值值和阈值处判决规则；
- 图中 `Vth[7:0]`/`D[7:0]` 与“3-bit flash”的精确编码关系；
- 两级 CDAC 的名义权重、冗余码和 dither 开关真值表；
- 逐级数字重构权重与最终 12-bit 饱和/舍入规则；
- PRNG `0/1` 到 dither 电容开关的物理真值表，以及 `1/16` 是否被硅实现文档另行定义为峰峰值。

候选 A 已建立可运行但仍带来源限定的物理解释：系统输入为 1 Vpp differential，理想放大前 residue 为 +/-62.5 mV differential；dither 行为采用模拟加、数字减和每个符号 +/-FSR/16。该解释足以进入 Gate A/B，但不能标记为硅内部 bit-true 码表。
