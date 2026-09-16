# 流水线 ADC 结构化性能预测研究

本项目围绕三个相互衔接的研究阶段展开：

1. 参考 Gu et al. 的 12-bit、3-GS/s 流水线 ADC，建立可逐级观测的 Python 实验平台；
2. 建立不含数字后台校准的 ADC 性能解析或半解析预测理论；
3. 建立数字后台校准模块对 ADC 性能指标影响的预测理论。

阶段一 Gate A 至 Gate E 已全部通过，候选 A 行为级 v1 已冻结为可信、可观测
的静态参考平台。理想码制、数字冗余、逐项静态非理想、已知参数与自适应校正、
定点实现、静态码密度和相干单音频谱指标均有正式实验与测试证据。阶段二的独立
区间传播和正弦相位积分预测器已通过 EXP-015/016，可直接预测静态传输、
码密度、连续傅里叶功率及有限记录 SNDR/SNR/THD/SFDR/ENOB；EXP-017 已为
有限建立建立首个具有静态极限和周期稳态的一阶动态基线。理论框架 v1.1
已完成独立审查与修订；EXP-018 第一门验证了单个阈值对连续静态谱线的局部
边界导数。为便于理解和检查，继续工作前请先阅读：

- `docs/PROJECT_CHARTER.md`：已经批准、但允许后续修订的研究章程；
- `docs/STATUS.md`：当前进度和下一项工作；
- `docs/DECISIONS.md`：重要研究决策及理由。
- `docs/theory/STAGE2_READER_GUIDE_V1.md`：从手算阈值例子进入阶段二主线；
- `docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md`：逐项结论、证据等级和缺口；
- `docs/theory/ADC_PERFORMANCE_PREDICTION_THEORY_FRAMEWORK.tex`：严格推导、适用条件和阶段三入口。

阶段一冻结规格和指标协议集中在 `docs/specifications/`，验收报告为
`docs/reports/STAGE1_PLATFORM_ACCEPTANCE_V1.md`。机器可读的行为级基线为
`configs/architectures/gu_behavioral_v1.yaml`；历史草案中保持为 `null`
的字段代表公开资料尚未闭合的信息，不能由实现静默猜测。

## 代码边界

- `src/adc_research/platform/`：逐样本实验平台，用于生成验证数据；
- `src/adc_research/theory/`：独立解析预测器；
- `src/adc_research/calibration/`：数字校正和自适应校准算法；
- `src/adc_research/metrics/`：统一的 ADC 指标计算；
- `src/adc_research/common/`：配置、单位、数据结构和来源信息。

实验平台与理论预测器可以共享经过审查的配置和数据结构，但理论模块不得依赖实验平台产生的频谱或数值灵敏度来构成其核心预测。

## 研究资料与产物

- `references/`：文献清单、BibTeX 和本地参考资料；
- `configs/`：架构、非理想和实验配置；
- `experiments/`：带编号的可复现实验入口；
- `artifacts/runs/`：运行时生成的配置快照、日志、trace、指标和图表；
- `docs/reports/`：经过审查后保留的实验结论、理论与证据审查报告；
- `legacy/pre_charter_v0_1/`：新章程形成前的两级原型，非当前正式模型。

## 开发检查

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

当前目录结构本身受测试约束。后续新增实验时，应把原始运行产物与人工撰写的研究报告分开保存。

## 参与维护

本项目公开接受社区维护与贡献。任何人都可以通过 Issue 提出问题或研究建议，
并通过 fork 后提交 Pull Request 的方式参与代码、实验、文档和复现工作。具体流程与
证据要求见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。GitHub 的公开仓库不会自动向所有人
授予直接写权限；合并到主分支前仍需经过审查。
