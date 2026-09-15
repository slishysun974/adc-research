# 阶段一 Python 实验平台软件规格 v0.1

> 状态：历史实现规格；Gate A 至 Gate E 已于 2026-09-15 完成  
> 适用范围：Gu et al. 三级 12-bit、3-GS/s 流水线 ADC  
> 本版目标：先完成理想静态信号链与冗余证明，再逐项增加非理想和校准
> 验收记录：`docs/reports/STAGE1_PLATFORM_ACCEPTANCE_V1.md`

## 1. 目标与非目标

平台必须逐样本复现：采样值、flash 判决、CDAC 重构、残差、后端 SAR 量化、数字冗余重构和最终输出码；每一级中间量均可观察、可保存、可独立测试。

本版不以匹配论文最终 SNDR/SFDR 为首要目标，也不把早期两级 `legacy` 原型直接复制为正式实现。晶体管级功耗、版图寄生和完整 SHA-less 时序属于后续保真层。

## 2. 分层结构

```text
configs / common
      | reviewed parameters and explicit assumptions
      v
platform (sample-wise reference simulator) ---> artifacts/runs

theory (independent analytical predictor) ----> separate predictions

calibration (known-truth and adaptive blocks) -> plugs into platform
metrics (one tested implementation) ----------> both result paths
```

`theory` 不得导入 `platform`。平台与理论可以共享不可执行的配置 schema、单位定义和 trace 数据结构；理论不能读取平台生成的频谱或数值 Jacobian 作为核心预测。

## 3. 建议模块与职责

```text
src/adc_research/common/
  config.py          load/validate resolved YAML
  types.py           immutable configs and trace/result records
  provenance.py      source category and locator validation
  units.py           normalized/physical conversions

src/adc_research/platform/
  quantizer.py       table-driven interval quantizer
  cdac.py            code/dither reconstruction and mismatch
  amplifier.py       ideal, static nonlinear, dynamic variants
  stage.py           quantizer + CDAC + residue composition
  backend_sar.py     ideal and channelized 4x TI-SAR
  reconstruct.py     redundancy-aware digital reconstruction
  pipeline.py        sample orchestration only
  trace.py           trace selection and serialization

src/adc_research/calibration/
  pwl.py             floating and bit-true PWL correction
  gated_lms.py       coefficient extraction and update scheduling
  known_truth.py     oracle coefficients for representation tests

src/adc_research/metrics/
  static.py          code histogram, DNL, INL, missing-code checks
  spectral.py        coherent FFT, SNDR, SFDR, THD, ENOB
  events.py          threshold crossings, overload, redundancy failure
```

第一实现批次只需建立 `common`、`quantizer`、`cdac`、`amplifier`、`stage`、`backend_sar`、`reconstruct`、`pipeline` 和必要静态测试；校准与频谱模块按验收门逐步加入。

## 4. 核心接口

### 4.1 Quantizer

```python
convert(value: float, config: QuantizerConfig) -> QuantizerResult
```

结果至少包含 `region_index`、`symbol`、`overload_low`、`overload_high`、`distance_to_nearest_threshold`。批量接口只能是该标量定义的无状态矢量化，不允许存在不同边界语义。

### 4.2 CDAC

```python
reconstruct(symbol, dither_symbol, config, mismatch) -> DacResult
```

结果同时给出名义值、各元件贡献、mismatch 贡献和 dither 贡献，以便将码相关误差追溯到具体权重。

### 4.3 Residue amplifier

```python
amplify(residue_input, state, config, rng) -> AmplifierResult
```

实现按保真度注册：`ideal_static`、`static_polynomial`、`static_pwl_truth`、`finite_settling`、`memory`。首版只启用 `ideal_static`；不同模型不得用同一参数名表达不同物理含义。

### 4.4 Pipeline stage

```python
process(main_input, aux_input, dither_symbol, config, nonidealities) -> StageResult
```

双路径必须显式传入。理想模式可以断言 `main_input == aux_input`，但不能删除辅助路径字段，否则后续无法定位 flash-path mismatch。

### 4.5 Digital reconstruction

```python
reconstruct(stage_results, backend_result, config) -> ReconstructionResult
```

重构依据配置中的权重/等价类表；结果保留裁剪前值、12-bit 输出、饱和和 `correctable` 标志。

## 5. 运行模式

| 模式 | 用途 | 允许的校准信息 |
|---|---|---|
| `ideal_static` | 验证码制、残差范围、重构和冗余 | dither/非理想/校准全部关闭 |
| `nonideal_uncalibrated` | 逐项建立非理想到输出的对照数据 | 不允许数字校正 |
| `known_truth_corrected` | 区分校正结构表达能力与估计算法误差 | 可使用生成非理想的真值 |
| `adaptive_background` | Gu gated-LMS 收敛与稳态研究 | 只能使用可观测码、dither 和历史状态 |

禁止把 `known_truth_corrected` 的结果称为“后台算法已收敛”。

## 6. 配置与来源契约

每个重要配置项包含：

```text
value, unit, provenance, source_id, locator, confidence
```

如果 `provenance = assumed`，还必须包含 `assumption_id` 和 `rationale`；如果 `value = null`，加载器应在需要该字段的运行模式下失败，而不是自动填入惯例值。

每次运行把解析后的完整配置复制到运行目录。配置 hash、源码版本、Python/NumPy 版本、随机种子和启动命令写入 `environment.json`。

## 7. 逐层验收门

### Gate A：量化器与 CDAC

- 所有阈值单调且每个区间只映射一个状态；
- 阈值处的上区间规则有测试；
- 理想 CDAC 码表单调或对非单调冗余状态有明确说明；
- dither 关闭时不改变任何输出。

### Gate B：单级残差与冗余

- 对每个输入区间给出解析残差端点；
- 标称增益 4 时，非过载输入的残差落入后级可表示范围；
- 穷举相邻决策路径，冗余范围内最终重构码相同；
- 超出可纠正范围时 `correctable=False`，不能静默饱和伪装成正确。

### Gate C：三级理想链

- 2+2+8 的重构产生 12-bit 单调传输；
- DC 扫描无缺码（端点饱和码除外）；
- 相同输入与配置逐位复现；
- 浮点残差恒等式与数字重构误差不超过预定量化界。

### Gate D：逐项非理想

- 每种非理想有独立开关和零值恒等测试；
- 主/辅路径增益差只通过辅助判决路径进入；
- CDAC mismatch、阈值 offset、增益误差、非线性分别可追踪；
- 组合非理想的顺序由规格固定。

### Gate E：指标与 Gu 锚点

- FFT 协议经过理想量化器测试；
- 复现论文中 4-slice PWL 的连续性与理想合成例；
- 再比较论文的 THD/SNDR/SFDR 趋势，不把无法对齐的电路细节吸收到任意拟合系数中。

## 8. 首批正式实验

| 实验 | 研究问题 | 主要输出 |
|---|---|---|
| EXP-001 | 候选 flash/CDAC 码表是否满足 residue 覆盖？ | 分段端点、overload 区间、路径表 |
| EXP-002 | 1-bit redundancy 的等价类和纠错边界是什么？ | 等价类、可纠正判决偏移范围、失效反例 |
| EXP-003 | 三级理想链是否严格形成 12-bit 单调量化？ | DC transfer、缺码、重构误差 |
| EXP-004 | 单一静态非理想如何改变 residue 与码边界？ | trace 差分、边界穿越率、DNL/INL |
| EXP-005 | 4-slice PWL 浮点校正能否复现论文合成例？ | `k_i/b_i`、连续性误差、THD 趋势 |

实验编号以正式新主线为准；`legacy/pre_charter_v0_1` 中的 Experiment 001 不占用新序列的证据地位。

## 9. 实施顺序与停止条件

1. 批准或命名一个覆盖 Q-001 至 Q-006 的假设集。
2. 实现 Gate A/B，并生成可人工审计的区间表。
3. Gate B 通过后实现三级链和 Gate C。
4. Gate C 通过后才加入非理想、频谱与校准。

如果没有任何候选码表能同时满足 4 倍增益、两级 1-bit 冗余、1 Vpp 量程和 12-bit 单调重构，应停止编码并回到来源/电荷守恒推导；不能通过调整最终码映射掩盖结构矛盾。
