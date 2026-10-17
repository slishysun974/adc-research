# 阶段二：完整链路与数字校准理论

本阶段连接输入、主辅残余电压、逐级判决、数字观测、更新状态、最终码和性能。当前停止点及下一执行只看[STATUS](../../STATUS.md)，方法与优先级只看[主线计划](../../RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md)；本页定位资料，不维护轮次进展。

先读[未知增益完整框架](../../theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md)、[理论索引](../../theory/README.md)及[结论—证据表](../../theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md)。模拟传输未知于算法，数字PWL不规定模拟曲线；额外输入、统计或物理条件须标明来源。

| 问题 | 理论与证据入口 | 限制 |
|---|---|---|
| 正常剩余误差与两级学习 | [两级误差／支持／投影](../../theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md)、EXP-072—074 | 已有有限学习连接／门通道因果关系；不提供全部误差的唯一份额或一般动态因果结论 |
| 观测、表示与在线识别 | [能力边界](../../theory/OBSERVATION_CORRECTION_LIMITS_V1.md)、NG-31／38／39、EXP-020 | 当前字固定映射、完整因果历史、附加正弦知识及不同电路训练识别分别定义 |
| 学习目标、收敛与跟踪 | [标量统计](../../theory/MILLION_SAMPLE_SCALAR_MEAN_NOISE_AND_QUANTIZATION_V1.md)、理论索引中的窗口／激励／整数条件 | 条件根、停更、有界、输出收益和恢复分别判断；一般八状态长期行为未认证 |
| 有效激励、抽取、定点和时序 | 理论索引中的Dither、主辅、四路窗口、定点与提交／广播 | 有限选样／数值／动态控制已完成指定范围；PRNG和真实实现语义不能由候选假设确认 |
| 码误差与最终性能 | 理论索引中的有限码／频谱界限、[指标协议](../../specifications/ADC_METRICS_PROTOCOL_V1.md) | 物理覆盖独立核对；普通FFT和短记录认证不成为长期／芯片保证 |

按[本地研究流程](../../../CONTRIBUTING.md)交付定义、条件、证明／反例、独立核对和分析。当前优先误差机制与能力边界，辅助理论围绕具体缺口推进；范围工具有真实计算阻碍才补，不以一般长期问题作为必做入口。

旧[TeX](../../theory/ADC_PERFORMANCE_PREDICTION_THEORY_FRAMEWORK.tex)、读者导引和EXP-015—019保留给定传输／动态特例。真实适用性另按[物理证据要求](PHYSICAL_ENVELOPE_EVIDENCE_GATE_V1.md)核对；缺少Cadence不阻止明确条件内的理论研究。旧成果、失败和预算停止保持，新增阶段方向按章程与当前授权处理。
