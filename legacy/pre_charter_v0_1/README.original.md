# 面向数字后台校准的流水线 ADC 性能理论研究

本目录是课题的全新起点。研究对象不再只是某一种校准算法，而是一个统一的闭环：

> ADC 结构与器件非理想 → 码型、余量与折叠事件 → 校准观测与参数估计 → 输出频谱 → SFDR、SNDR、ENOB 与收敛时间。

当前版本（v0.1）已经完成：

- 新课题研究计划与可证伪研究假设；
- 物理层、算法层、频谱层和因果层的统一数学框架；
- 一份只纳入可追溯来源的文献地图；
- 可运行的两级流水线 ADC 行为模型；
- 级间增益误差、CDAC mismatch、比较器阈值失调和 residue folding/overload 的显式建模；
- 基于共同随机数和全因子干预的 SFDR/SNDR 归因实验；
- 单元测试和首批实验记录。

## 快速运行

在本目录执行：

```powershell
$env:PYTHONPATH = "src"
python experiments/run_baseline_factorial.py
python -m unittest discover -s tests -v
```

实验结果写入 `results/experiment_001_baseline.json`。

## 目录

- `docs/RESEARCH_PLAN.md`：一年研究计划、问题边界与里程碑；
- `docs/THEORY_FRAMEWORK_V0_1.md`：统一理论框架 v0.1；
- `docs/LITERATURE_MAP.md`：文献地图及其在课题中的用途；
- `docs/EXPERIMENT_001.md`：首个基线实验的设计与结论；
- `src/adc_research/`：ADC、频谱指标和干预归因代码；
- `experiments/`：可复现实验入口；
- `tests/`：最小正确性测试；
- `results/`：机器可读实验结果。

## 当前边界

这是理论研究用的行为级模型，不等价于晶体管级电路。v0.1 暂不覆盖采样时钟抖动、运放有限带宽/记忆效应、热噪声随电路状态变化、参考电压动态和版图空间相关性。后续只有在基础模型通过参数扫描与电路锚点验证后，才逐项增加这些自由度。

