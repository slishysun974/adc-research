# 流水线 ADC 数字后台校准研究

本项目以Gu的分段线性后台校准为基线，研究：**内部数字信息怎样驱动系数学习，为什么仍会留下输出误差，以及在观测和资源限制下还有多少改善空间。** 最终目标是据此设计并检验更好的校准算法。

## 与Gu论文的关系

熟悉Gu论文的读者，可以从校正函数与系数学习之间的关系进入。分段线性函数决定怎样重构数字码，门控LMS决定怎样利用已知微小扰动（dither）调整系数。本项目进一步检查：哪些样本提供了有效信息，系数怎样随时间变化，以及这些变化最终改善还是降低输出质量。

研究依据公开结构和公式建立了Gu候选实现。论文未公开的内部精度、随机源和更新时序采用明确标注的项目约定，详见[与原文的对应关系](docs/reports/GU_ALGORITHM_EVALUATION_V1.md#4-本项目实现与gu原文的对应关系)。这些候选用于条件研究，不等同于芯片全部内部实现。

模拟平台可以预设放大曲线，供研究者控制和评分；**运行中的算法仍不知道这条曲线，只使用内部数字码、扰动标签和自身状态。** Gu的分段线性形式属于数字校正函数，不规定模拟放大器的物理形状。

## 目前最重要的三项认识

以下概述依据截至2026-10-15的既有证据，均保留原行为模型和有限记录条件；最新进展、准确停止点与下一研究安排由[STATUS](docs/STATUS.md)维护。

1. **学习信息的数量和采用方式会影响净收益。** 少量样本的统计变化可能抵消校正收益；减小步长或增加学习观测，在部分条件下能降低误差，也会涉及启动、恢复和资源取舍。见[后台性能汇报](docs/reports/RESEARCH_MODULE_06_BACKGROUND_PERFORMANCE_V1.md)。
2. **剩余误差需要结合平均系数与持续变化解释。** 学习目标、请求发生的时间、随状态变化的采用门和两级作用共同影响结果，当前证据不能归结为单一原因。见[误差来源汇报](docs/reports/RESEARCH_MODULE_07_ERROR_MECHANISMS_V1.md)。
3. **较好系数的存在与在线取得它是不同问题。** 部分合法固定系数能够给出更低误差，但离线构造依赖的目标信息不能直接交给在线算法。见[数字观测与校正目标](docs/reports/RESEARCH_MODULE_04_INFORMATION_V1.md)。

## 已有基础与当前关键缺口

已有静态行为平台验收、条件性信号链／性能推导、Gu浮点与定点实现、有限RTL功能核对，以及一批持续后台运行和受控干预结果。这些成果分别支撑实验、理论和实现判断，各自的成立条件由原报告说明。

当前仍需回答：**实际可见信息或可信输入条件，能否帮助算法判断有益方向，并从同一初态达到、维持较好的校正？** 同成本收益、更广输入适用性、一般长期收敛和芯片物理证据仍待解决；新算法阶段尚未正式启动。

[四阶段章程](docs/PROJECT_CHARTER.md)描述推进路线：实验平台、完整链路与校准理论、Gu基线、新算法。现有工作主要在阶段二、三。[七个研究模块](docs/reports/PROJECT_STRUCTURE_AND_RESEARCH_REVIEW_2026-10-16.md#6-七个模块的研究汇报)是成果分类，便于按问题阅读，不表示四阶段均已完成。

## 怎样阅读

已经读过Gu论文、第一次接触项目，请从[首次阅读路线](docs/README.md#首次阅读了解课题与已有成果)进入：先理解目标和与论文的对应关系，再看实际性能、学习过程、误差原因和信息边界。预测理论、平台细节和硬件实现可按需要补读。

准备继续开展研究时，再按[研究接续流程](docs/README.md#继续开展研究确认当前证据与停止点)核对STATUS、现行主线和相关证据。决策、历史记录与全部实验编号用于追溯，首次阅读无需顺读。

## 实现与复现入口

- `src/adc_research/`：`platform/`为模拟实验链，`calibration/`为在线数字校准，`evaluation/`为数字观测提取和离线评分，`theory/`为条件计算器，`metrics/`为统一指标。理论预测与逐样本平台独立实现，真值和理想参照不进入在线学习。
- [Simulink行为模型](simulink_adc/README.md)：可展开的逐级信号流程、浮点反馈和与Python的逐样本核对。定点、RTL和芯片适用性分别验收。
- [导师阶段汇报](output/advisor_progress_ppt169_20261016/README.md)：28页可编辑PPT、逐页说明与SVG源文件，按七模块组织截至2026-10-15的研究证据；最新进展仍以STATUS为准。
- [实验索引](docs/reports/experiments/README.md)定位`experiments/`的定义和原报告；[RTL入口](rtl/README.md)定位数字候选、功能核对与综合。原逐转换候选未通过100 MHz；[多拍整改](docs/reports/RTL_MULTICYCLE_TIMING_2026-10-16.md)保留原递推，当前串行除法版接收间隔40周期，100 MHz完整验收与适用范围见报告。目标工艺成本仍待验证。
- [旧TeX](docs/theory/ADC_PERFORMANCE_PREDICTION_THEORY_FRAMEWORK.tex)和[PDF](output/pdf/ADC_PERFORMANCE_PREDICTION_THEORY_FRAMEWORK.pdf)是给定传输／动态假设下的底稿；[未知增益理论框架](docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md)说明一般问题和现有条件关系。

早期实验的配置来源修订见[在线信息边界审查](docs/stages/03_gu_baseline/ONLINE_INFORMATION_BOUNDARY_AUDIT_V1.md)；旧结果保留其条件，真实芯片可见总线仍有未公开项。

## 本地检查

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

贡献流程及公开资料限制见 [CONTRIBUTING.md](CONTRIBUTING.md)。
