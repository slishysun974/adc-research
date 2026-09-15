# 文献地图（首版）

本表优先记录标准、原始论文和出版方页面。其目的不是堆砌综述，而是明确每份资料将解决课题中的哪个缺口。

| 主题 | 来源 | 对本课题的作用 | 当前使用方式 |
|---|---|---|---|
| ADC 术语与测试 | [IEEE Std 1241-2023](https://standards.ieee.org/ieee/1241/6797/) | 统一 SFDR、SINAD/SNDR、ENOB 和采样测试口径 | 指标命名与测试协议基准 |
| 多非理想后台校准 | [14-bit RF sampling ADC with background calibration and dither，IEEE 文献 7573537](https://ieeexplore.ieee.org/document/7573537/) | 原型同时校正级间增益、动态 settling、kick-back、memory 与 comparator offset | 用于确定物理误差清单与对照架构 |
| 级间增益后台校准 | [IEEE 文献 5137059](https://ieeexplore.ieee.org/document/5137059/) | 提供包含 mismatch 与有限运放增益的级间增益校准实例 | 后续 LMS 基线和参数范围参考 |
| 硬非线性/多值区校准 | [Black-Box Calibration for ADCs With Hard Nonlinear Errors，IEEE 文献 7864410](https://ieeexplore.ieee.org/document/7864410/) | 直接讨论流水线 ADC 邻码不连续与多值区导致的常规 INL 校准失效 | 支撑 folding/边界不能只用平滑误差模型的判断 |
| 非光滑混合系统灵敏度 | [Kong 等，Saltation Matrices, arXiv:2306.06862](https://arxiv.org/abs/2306.06862) | 解释为什么跨离散事件时普通状态转移 Jacobian 不够 | 启发边界事件项；不直接照搬结论 |
| 常步长随机逼近稳态 | [Chen 等，arXiv:2111.06328](https://arxiv.org/abs/2111.06328) | 给出常步长 SGD/线性随机逼近稳态分布与协方差视角 | 支撑校准稳态统计层 |
| 有限时间常步长 SGD | [Merad 与 Gaïffas，arXiv:2306.11497](https://arxiv.org/abs/2306.11497) | 从 Markov 链视角给出非渐近收敛与集中性质 | 支撑收敛时间和置信区间分析 |
| 动态中介分析 | [Ge 等，ICML 2023 / PMLR 202](https://proceedings.mlr.press/v202/ge23a.html) | 区分即时/延迟以及直接/中介路径 | 启发 `算法→参数轨迹→频谱` 的动态效应分解 |

## 阅读顺序

1. 先以 IEEE 1241 固定指标和测试口径；
2. 阅读三篇 ADC 校准论文，抽取结构、误差源、激励、收敛指标和实现开销；
3. 阅读混合系统灵敏度论文，只提取“事件导致灵敏度跳变”的数学工具；
4. 阅读常步长与有限时间随机逼近论文，区分稳态精度和 time-to-target；
5. 最后阅读动态中介分析，检查哪些识别假设能由随机化仿真实验主动满足。

## 待补文献，不提前下结论

- Pipeline/MDAC 中 capacitor mismatch 到 INL、谐波和 folding 的解析传播；
- DEM/dither 对码相关误差频谱整形的原始论文；
- ADC 输出的置信区间与多 seed/PVT 统计验证；
- 带门控与状态相关激励的 LMS 有限时间理论；
- 硅后可实施的随机干预或自然实验设计。

新增文献时必须同时记录：模型假设、可观测量、验证数据、适用范围和本课题是否真正复用其结论。
