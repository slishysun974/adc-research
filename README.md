# 流水线 ADC 数字后台校准研究

> 后续AI或研究者先读 [文档阅读指南](docs/README.md) 和 [当前状态](docs/STATUS.md)。阅读入口、研究流程和成果索引复用现有文件；当前批准的静态定点阶段同时包含理论推导、实验验证和结果分析。

本项目研究一个直接的问题：**残差放大器的非线性事先未知时，ADC 内部能看到哪些信息，数字校准能改善多少性能，能否设计出比 Gu et al. 基线更好的算法？** 这里的“更好”还需要通过留出测试和硬件成本比较来证明。

研究按[四阶段章程](docs/PROJECT_CHARTER.md)开展：实验平台、完整信号链与校准理论、Gu 算法基线、新算法。旧“三阶段”文档和实验编号仍在原位置，便于核查历史结果；[阶段导航](docs/stages/README.md)解释它们在新路线中的位置。

## 当前最重要的限制

已有平台可人为指定一条模拟 PWL 曲线（若干段直线），旧理论预测器在**给定这条曲线**时计算码边界与频谱。这个一致性结果没有证明真实放大器的曲线已知，也没有证明它本来就是 PWL。Gu 的 PWL 指的是**数字校正函数**，不是模拟增益的物理形状。

新阶段二的[理论入口](docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md)把模拟传输当成未知对象，同时纳入从输入到最终码的逐级信号链，以及数字校正和参数更新。旧的[TeX 推导](docs/theory/ADC_PERFORMANCE_PREDICTION_THEORY_FRAMEWORK.tex)和 [PDF](output/pdf/ADC_PERFORMANCE_PREDICTION_THEORY_FRAMEWORK.pdf)保留作有指定曲线／动态假设的条件性底稿；新的未知增益理论尚未完成，不可用旧 PDF 冒充。

## 阅读与代码入口

- [章程](docs/PROJECT_CHARTER.md)：目标、四阶段和不泄漏模拟真值的原则。
- [状态](docs/STATUS.md)与[决策](docs/DECISIONS.md)：现在做到哪里、有哪些开放问题。
- [四阶段导航](docs/stages/README.md)：旧代码、实验与新阶段的对应关系。
- `src/adc_research/platform/`：含模拟真值的逐样本实验链；`calibration/`：只从数字样本更新的校准核心；`evaluation/`：提取数字观测和离线 oracle 评分；`theory/`：现有条件性计算器；`metrics/`：统一指标。
- `experiments/`：可复现的编号实验；`docs/reports/`：经审查的结果；`rtl/`：已有 Gu 数字候选的功能核对与通用综合，目标工艺成本和新算法仍待研究。

[第一轮代码信息边界审计](docs/stages/03_gu_baseline/ONLINE_INFORMATION_BOUNDARY_AUDIT_V1.md)指出旧 EXP-010/011/013 的配置经由模拟真值对象建立；现已拆分配置来源与在线输入，但跨曲线留出测试和真实芯片可见总线核对仍未完成。

理论实现与逐样本平台保持分开；共享经过审查的架构信息可以，但不能把平台幕后真值或频谱喂给正在检验的理论和算法。

## 本地检查

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

贡献流程及公开资料限制见 [CONTRIBUTING.md](CONTRIBUTING.md)。
