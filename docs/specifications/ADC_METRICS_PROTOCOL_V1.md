# ADC 静态与单音频谱指标协议 v1.0

> 状态：阶段一 Gate E 基线  
> 适用对象：`gu_behavioral_v1` 实验平台及后续独立理论预测器  
> 依据：IEEE 1241-2023 的 ADC 术语与测试方法框架，以及 Analog Devices
> MT-003 对 SINAD、SNR、THD、SFDR 和 ENOB 的定义说明[^1][^2]

## 摘要

本协议规定静态行为级 ADC 平台和后续独立理论预测器共同使用的均匀斜坡码
密度指标与相干单音 FFT 指标。协议明确 DNL、码转换边界 INL、缺失码、
SNDR/SINAD、SNR、THD、SFDR、ENOB、谐波折叠、积分带宽和最终整数化规则，
并要求分别报告无 dither 与有 dither 的工作条件。指标实现只负责转换同一
输出记录，不参与 ADC 传输函数或校正参数计算。

**关键词：** 模数转换器；码密度测试；相干采样；微分非线性；积分非线性；
信号与噪声加失真比；无杂散动态范围

## 1. 目的与适用边界

本协议规定平台和后续理论预测器共同使用的静态码密度指标与相干单音 FFT
指标。统一指标实现只负责把同一输出记录转换为可比较的数值，不参与 ADC
传输函数或校准参数计算，因此不能成为实验平台与理论预测器之间的隐含拟合
通道。

协议适用于均匀采样、名义均匀量化的 ADC 输出。当前版本不包含双音互调、
相位噪声、孔径抖动估计、非相干采样窗函数选择或测量仪器修正。

## 2. 静态码密度指标

### 2.1 输入记录

静态测试使用覆盖归一化输入范围 `[-1,1)` 的均匀斜坡。每个样本位于相邻数值
网格的中点，避免把恰好落在判决边界上的样本计入上、下区间规则。EXP-014
使用 4096 个输出码、每个理想码 32 个样本，共 131072 个输入样本。

每次报告必须注明：输入范围、样本总数、每个理想码的样本数、dither 状态、
校正模式和最终整数化规则。无 dither 与有 dither 的码密度结果不得合并。

### 2.2 DNL、INL 与缺码

设输出码 $i$ 的直方图计数为 $H_i$，共有 $L$ 个允许输出码，样本总数为 $N$。
均匀输入下的平均计数为 $\bar H=N/L$，码 $i$ 的微分非线性定义为

$$
\operatorname{DNL}_i=\frac{H_i}{\bar H}-1.
$$

当前版本报告以下端点参考的码转换边界积分非线性：

$$
\operatorname{INL}_j=\sum_{i=0}^{j-1}\operatorname{DNL}_i,
\qquad j=0,1,\ldots,L.
$$

其中 $\operatorname{INL}_0=0$，$\operatorname{INL}_j$ 对应第 $j$ 个码转换边界，
不是码中心误差。若 $H_i=0$，则码 $i$ 记为缺码，并有
$\operatorname{DNL}_i=-1$ LSB。报告同时给出 DNL/INL 的最小值、最大值和缺码
列表，不用单一最大绝对值代替正、负范围。

本定义是均匀数值斜坡的码密度估计。与硅测量比较时，还需对齐输入源线性度、
测试样本数、通道合并方式、dither 状态和端点处理；否则只比较变化方向。

## 3. 相干单音 FFT 指标

### 3.1 输入记录和 FFT

记录长度为 $M$，采样率为 $f_s$，输入频率选择为

$$
f_{in}=\frac{k}{M}f_s,
$$

其中 $k$ 是明确记录的正整数 FFT 频点，且位于第一奈奎斯特区内部。EXP-014
使用 $M=65536$、$f_s=3$ GS/s 和频点 997、21845、32749，对应约
45.639 MHz、999.985 MHz 和 1499.130 MHz。输入峰值为归一化满量程的 0.999。

相干记录采用矩形窗。FFT 前减去输出均值；DC 不计入噪声、失真或杂散功率。
实信号单边频谱按均方根功率归一化，使各频点功率之和等于去均值记录的均方值。
基波频点由配置给定，不通过搜索最大谱线确定。

### 3.2 谐波和频率折叠

当前版本统计二至五次谐波。第 $h$ 次谐波先按 $hk$ 对 $M$ 取模，再折叠到
`[0,M/2]`。若所选谐波折叠到 DC 或基波频点，配置无效；不同谐波折叠到同一
频点时只累计一次该频点功率。

### 3.3 动态指标

设基波功率为 $P_s$，除 DC 和基波外的总功率为 $P_{n+d}$，指定谐波功率之和
为 $P_h$，其余噪声功率为 $P_n=P_{n+d}-P_h$，最大非 DC、非基波谱线功率为
$P_{spur}$。指标定义为

$$
\operatorname{SINAD}=10\log_{10}\frac{P_s}{P_{n+d}},
$$

$$
\operatorname{SNR}=10\log_{10}\frac{P_s}{P_n},
\qquad
\operatorname{THD}=10\log_{10}\frac{P_h}{P_s},
$$

$$
\operatorname{SFDR}=10\log_{10}\frac{P_s}{P_{spur}},
\qquad
\operatorname{ENOB}=\frac{\operatorname{SINAD}-1.76}{6.02}.
$$

本文将论文使用的 SNDR 与 SINAD 作为同一功率比的两种常用名称；程序字段
`sndr_db` 按上述 SINAD 公式计算。SINAD（SNDR）、SNR 和 SFDR 以正的功率比
dB 值报告；THD 以相对基波的负 dB 值报告；
SFDR 当前使用 dBc。若需要 dBFS，必须另行提供满量程正弦的峰值定义。报告必须
注明积分带宽，当前版本为 DC 至第一奈奎斯特频率。

## 4. 校正模式与最终整数化

平台至少区分以下输出：

- `ideal_static`：理想静态链，无非理想和数字校正；
- `nonideal_uncalibrated`：启用指定非理想，不使用相应数字校正；
- `known_truth_corrected`：使用生成非理想的已知参数，只检验校正结构；
- `adaptive_background`：系数只能来自可观测码、dither 和历史状态。

浮点或定点校正结果转换为 12-bit 输出码时，必须明确舍入和饱和规则。EXP-014
的已知系数校正采用舍入到最近偶数，并限制在 `[0,4095]`。不同规则的结果不得
放在同一统计量中平均。

## 5. Gate E 验证要求

统一指标实现必须通过以下检查：

1. 每个输出码计数相同的人工直方图产生零 DNL、零 INL 和零缺码；
2. 一个缺码和相邻双宽码产生 `-1/+1` LSB 的 DNL，并在累积后恢复端点 INL；
3. 已知幅度的单一谐波产生相应的 THD 和 SFDR；
4. 理想 12-bit 三级链在均匀斜坡下产生零 DNL、零 INL 和零缺码；
5. 近满量程相干正弦的理想链 SINAD 接近 12-bit 理想量化范围；
6. 相同静态传输函数在互质相干频点上的指标应保持一致；
7. 与论文结果只比较可归因于相同机制的变化方向，不通过任意拟合参数匹配绝对值。

## 6. 论文参照结果与使用限制

Gu 等人的扩展论文报告：仿真中四段 PWL 校正的名义 THD 约为 -80 dB，最坏
工艺、电压和温度条件下约为 -75 dB；1 GHz、0 dBFS 测量中，增益非线性校正
使 SNDR 从 54.0 dB 增至 60.3 dB，SFDR 从 62.7 dB 增至 76.0 dB；输入频率
超过 1 GHz 后，输入缓冲器和采样电路使性能下降。[^3]

当前静态平台不包含电路噪声、输入缓冲器失真、采样失真和完整 SHA-less 时序，
因此不能复现测量绝对值或高频下降。Gate E 只检查 PWL 校正是否使 THD、SNDR
和 SFDR 按论文方向变化，并把频率不变性作为静态模型适用边界，而不是把缺失
动态机制吸收到 PWL 参数中。

[^1]: [IEEE 1241-2023, IEEE Standard for Terminology and Test Methods for Analog-to-Digital Converters](https://standards.ieee.org/ieee/1241/6797/).
[^2]: [W. Kester, “Understand SINAD, ENOB, SNR, THD, THD+N, and SFDR,” Analog Devices MT-003](https://www.analog.com/media/en/training-seminars/tutorials/MT-003.pdf).
[^3]: Mingyang Gu, Yi Zhong, Lu Jie, and Nan Sun, “A 12-b 3-GS/s Pipelined ADC With Piecewise-Linear Gain Nonlinearity Calibration,” *IEEE Open Journal of the Solid-State Circuits Society*, 2026, Figs. 9 and 20–23, DOI: 10.1109/OJSSCS.2026.3656850；本地副本 `references/local/OJSSCS2026_Gu.pdf`。
