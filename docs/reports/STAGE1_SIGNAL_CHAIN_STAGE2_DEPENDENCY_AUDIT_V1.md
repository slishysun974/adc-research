# 阶段一信号链与阶段二理论依赖审计 v1

> 日期：2026-09-17
> 结论：阶段一 `gu_behavioral_v1` 的理想静态码制和运算顺序在其冻结假设下正确；第一级独立辅助放大器被约简为主 residue 的仿射副本。阶段二静态与动态验证只覆盖该约简模型，理论框架已据此收紧。

## 核查依据与口径

- [Gu et al. 扩展论文](../../references/local/OJSSCS2026_Gu.pdf) Fig. 13：第一级主放大输出驱动第二级 CDAC，辅助放大输出驱动第二级 flash；第二级主输出进入 4 通道 8-bit TI-SAR。文中给出主路 11 GHz/100 ps、辅路 7 GHz/80 ps 与约 3% 的主辅增益差。
- 该论文 Fig. 4、5、18：模拟 dither 注入后，经数字 PWL 校正再扣除数字副本；数字 PWL 是量化后的校正映射，不是模拟放大器的拓扑。
- [架构证据基线](../specifications/GU_ARCHITECTURE_EVIDENCE_V1.md) 将双路径拓扑标为论文事实，将 flash 阈值、CDAC 电平、重构权重和 dither 幅度标为推导候选。故以下“正确”指候选 A 行为级一致性，不指硅芯片逐位复刻。

## 逐段核查

| 环节 | 代码实际连接 | 核查结果 |
|---|---|---|
| 第一级 flash 与 CDAC | [pipeline.py](../../src/adc_research/platform/pipeline.py) 将输入送第一级；[stage.py](../../src/adc_research/platform/stage.py) 用辅助坐标判决 $q_1$，CDAC 由 $q_1$ 重构，主输入减去 CDAC、加 dither 后进入模拟增益。 | 候选 A 的第一级静态顺序正确；默认第一级 flash 直接观察输入。 |
| 第一级主/辅分路 | 第一级只有一个实际 `residue`；第二级辅助坐标由 `ratio * stage1.residue + offset` 生成，第二级主输入直接使用 `stage1.residue`。 | **结构性约简**。它表达固定主辅增益差，但没有独立的辅助放大器输出或状态。 |
| 第二级与后端 | 第二级辅助坐标供 flash 判决；第二级 CDAC/残差仍使用主输入；第二级主 residue 送 8-bit midrise TI-SAR，通道按采样序号轮转。 | 在约简前提下符合 Fig. 13 的连接方向；未实现通道失配、采样时差、完整 CDAC 开关真值表。 |
| dither 与未校正数字重构 | [stage.py](../../src/adc_research/platform/stage.py) 在放大前以正号注入；[reconstruct.py](../../src/adc_research/platform/reconstruct.py) 组合 $512q_1+128q_2+c_3$，再减 $D_1+D_2$ 并加 2048。 | 理想、无过载且数字副本为整数时精确抵消。残留 dither 相关误差只会由非理想或校正不完全产生。 |
| 数字 PWL 校正 | [known_truth.py](../../src/adc_research/calibration/known_truth.py) 先校正后级码、扣除 $D_2$，再经前级校正、扣除 $D_1$；合成模拟 PWL 位于 [amplifier.py](../../src/adc_research/platform/amplifier.py)。 | 模拟传输 $g_i$ 与数字逆向校正 $f_i$ 已分开；合成模拟 PWL 是测试真值，不是论文规定的物理放大器。 |
| 有限建立 | [finite_settling.py](../../src/adc_research/platform/finite_settling.py) 只保存两级主 residue 状态，第二级 flash 的辅助输入仍取已建立的主 residue 仿射副本。 | EXP-017 验证主路单状态基线，不能验证辅路独立建立或判决时刻。 |

## 已有测试能说明什么

[Gate C 测试](../../tests/test_platform_gate_c.py) 检查逐级 residue 恒等式、4096 个码中心、两种 dither 符号组合与正负 3% 辅助增益差；[双级校正测试](../../tests/test_gu_two_stage_pwl_truth.py) 检查局部 dither 顺序；[EXP-015](experiments/EXP_015_STAGE2_STATIC_TRANSFER_V0_1.md) 和 [EXP-016](experiments/EXP_016_STAGE2_STATIC_SPECTRUM_V0_1.md) 分别验证静态码域与频谱预测；[EXP-017](experiments/EXP_017_STAGE2_FINITE_SETTLING_V0_1.md) 比较主路一阶状态的理论解和逐样本平台。它们支持**已冻结行为模型内部**的公式和实现，并未将独立辅路作为留出条件，因此不能排除这里的建模缺口。

这并不推翻理想重构代数：在理想主路与冗余范围内，$q_2$ 改变时，末级量化码可以同步补偿，最终 $C$ 仍相同。只看最终码或频谱尤其容易漏检内部双路径差异；须同时观察辅路输出、$q_2$、第二级主 residue 和是否过载。

## 一个用于区分模型的阈值反例

以下数字是**假设单极点且跨样本保持**时的辨别性计算，不是对芯片瞬态的预测。取第一级当前静态目标为 0.127，主/辅前一状态均为 0，第二级 flash 阈值为 0.125。候选 A 中可以由 $x=0.03175$、$q_1=0$、无 dither 和名义增益 4 得到这一静态目标。按论文给出的两组带宽/时间分别构造残余因子：

$$
\rho_{\mathrm m}=e^{-2\pi(11\,\mathrm{GHz})(100\,\mathrm{ps})}
=0.0009962585,\qquad
\rho_{\mathrm a}=e^{-2\pi(7\,\mathrm{GHz})(80\,\mathrm{ps})}
=0.0296413844.
$$

于是主路末值为 $0.127(1-\rho_{\mathrm m})=0.1268734752>0.125$，辅路末值为 $0.127(1-\rho_{\mathrm a})=0.1232355442<0.125$。按候选阈值表，现有主路副本会取 $q_2=1$，独立辅路会取 $q_2=0$。这个构造只证明两种模型**可分辨**；若实际电路每相位复位或两路采样时刻不同，必须改用对应的状态与时序方程。

## 对阶段二的处理

1. 现有静态区间传播与频谱结果继续作为仿射辅路行为基线；其路径胞腔命题的条件须显式包含 $r_1^{\mathrm a}=a_2r_1^{\mathrm m}+o_2$。
2. 更一般的静态模型应独立定义 $r_1^{\mathrm m}=g_1^{\mathrm m}(w_1)$ 与 $r_1^{\mathrm a}=g_1^{\mathrm a}(w_1)$；用后者判决 $q_2$，用前者计算第二级 CDAC 残差。区间传播须纳入辅路分段与阈值原像。
3. 动态模型须分别描述主、辅建立和 flash 判决时刻；若两路都跨样本保持，至少需要第一级主、第一级辅和第二级主三个状态。先区分复位、保持、压摆和高阶动态，不能仅凭终点带宽替芯片选定状态语义。
4. 下一验证门应在靠近第二级 flash 阈值的输入上比较两路模拟末值、$q_2$ 和第二级 residue；同时考察 dither、主辅静态非线性及采样时差。使用电路瞬态或测量锚定参数后，才能把其频谱变化称为芯片预测。

正式理论已在 [v1.3 框架](../theory/ADC_PERFORMANCE_PREDICTION_THEORY_FRAMEWORK.tex) 中加入双路径对象，并将已有证明和 EXP-017 证据限定于约简模型。
