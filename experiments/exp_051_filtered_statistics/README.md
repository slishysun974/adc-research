# EXP-051：四点相关量平滑与小步长对照

沿正常闭环中实际出现的有限选样问题，固定相位0、每窗口4个样本。原步长基线、小步长`mu/4`及一阶平滑`alpha=1/4`共享PWL、Q1.10／Q3／Q22、样本预算及窗口提交频率。平滑保留原步长，新增208位统计状态；小步长不新增学习状态，但其速度代价须单独检查。

[协议](protocol.json)在计算前固定两组新三次曲线参数、三个新种子组、24格条件及筛选门。各输入的正弦频点在三个种子组间保持不变，便于检验种子影响。全部从单位系数和零滤波状态开始，切换到正弦时均不复位。检查点离线评分同一正弦记录，不选择最好停止点。

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -p '*filtered*.py' -v
python -m experiments.exp_051_filtered_statistics.run artifacts/runs/EXP_051/filter_v1
python -m experiments.exp_051_filtered_statistics.verify artifacts/runs/EXP_051/filter_v1
python -m experiments.exp_051_filtered_statistics.audit_filter_sums artifacts/runs/EXP_051/filter_v1
$env:MPLCONFIGDIR='D:\ADC\artifacts\tooling\matplotlib_config'
python -m experiments.exp_051_filtered_statistics.plot_results artifacts/runs/EXP_051/filter_v1
python -m experiments.exp_051_filtered_statistics.finalize artifacts/runs/EXP_051/filter_v1
```

主入口拒绝覆盖已有目录，所有失败和过载保留。平台、源码及协议摘要固定。独立标量核对全部数字PWL、门、滤波状态、请求、饱和、八状态和最终码；离线目标／误差／滤波舍入影子状态精确还原实际更新，不反馈给运行中的校准器。滤波累计和另作精确边界项检查。

[条件推导](../../docs/theory/FILTERED_STATISTICS_STEP_AND_STATE_VARIANCE_V1.md)区分统计方差、系数方差、目标偏差和学习速度，不把标量模型套成已识别的Gu八状态模型。合成平台及浮点FFT不提供芯片结论。详见[报告](../../docs/reports/experiments/EXP_051_FILTERED_STATISTICS_V1.md)。
