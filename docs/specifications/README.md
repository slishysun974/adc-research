# 架构与接口规格

阶段一开始后，本目录用于保存 Gu 架构规格、参数来源、归一化约定、数字码定义、冗余规则和模块接口。

规格中的每个重要参数应标明来源类别：论文明确给出、外部资料、推导、拟合或研究假设。

## 当前冻结基线

- `GU_ARCHITECTURE_EVIDENCE_V1.md`：行为级 v1 的证据层级、冻结范围和开放物理层；
- `GU_SIGNAL_CODE_CONVENTIONS_V1.md`：行为级 v1 的路径、码制、dither、重构与事件语义；
- `configs/architectures/gu_behavioral_v1.yaml`：Gate A/B/C 验证后的可执行配置。
- `ADC_METRICS_PROTOCOL_V1.md`：阶段一 Gate E 冻结的静态码密度与相干单音频谱指标。

## 历史草案与持续问题

- `GU_ARCHITECTURE_EVIDENCE_V0_1.md`：论文参数、证据定位、版本差异及可冻结边界；
- `GU_SIGNAL_CODE_CONVENTIONS_V0_1.md`：归一化、量化器、CDAC、重构和 trace 接口约定；
- `GU_OPEN_QUESTIONS_V0_1.md`：未公开细节、风险和关闭计划；
- `STAGE1_SOFTWARE_SPEC_V0_1.md`：平台模块、接口、验收门与首批实验的历史规格；Gate A 至 Gate E 已完成。

上述 `v0.1` 文件保留为审计底稿。`GU_OPEN_QUESTIONS_V0_1.md` 继续维护尚未
关闭的问题；`gu_nominal_v0_1_draft.yaml` 中值为 `null` 的字段不得由实现
静默猜测。阶段一验收结论见
`docs/reports/STAGE1_PLATFORM_ACCEPTANCE_V1.md`。
