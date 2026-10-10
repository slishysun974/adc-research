# EXP-048：成对dither、共同门和周期误差

只读审查EXP-039的六组输入／三路有效跟踪初态，确认哪些正负dither读出满足源模型的配对条件。独立数字入口求成对基函数差的Gram及对比方程；随后离线检查目标误差。额外例子是明确声明的精确数学反例，不是新增ADC平台仿真或物理数据。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_048_paired_dither_conditions.run artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_047/sources_v2 artifacts/runs/EXP_048/pairs_v1
$env:MPLCONFIGDIR='D:\ADC\artifacts\tooling\matplotlib_config'
python -m experiments.exp_048_paired_dither_conditions.plot_results artifacts/runs/EXP_048/pairs_v1
python -m experiments.exp_048_paired_dither_conditions.finalize artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_048/pairs_v1
```

主入口拒绝覆盖已有目录，复跑须换新EXP_048子目录。正式产物为`pairs_v1`，图须实际查看。数字对比方程不读取理想目标；配对的输入／跟踪元数据仅在离线源模型审查中读取，现有五字段在线接口不提供这些条件的证书。

没有在线训练、反馈提交、原Gu／RTL修改或Cadence。没有计算全ADC频谱。平方对比损失、四系数解和单级码误差分别报告，不把反例或三对旧正弦读出当作新算法评估。见[推导](../../docs/theory/PAIRED_DITHER_CANCELLATION_AND_PERIODIC_ERRORS_V1.md)、[报告](../../docs/reports/experiments/EXP_048_PAIRED_DITHER_CONDITIONS_V1.md)。
