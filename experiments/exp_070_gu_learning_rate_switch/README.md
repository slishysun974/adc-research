# EXP-070：固定 Gu 学习率下的幅度切换

按 D-126 任务 4、D-127 的合同与有限输出定义，只比较原倍率和 1/4。三原静态模型、五原种子、point30／full120、承接／单位初值保持；从全局 3932160 转换起幅度 0.82→0.41，每新路径 32768 窗口／128 完整码块。60 条原倍率长路径复用 EXP-066，60 条 1/4 自己计算全部门、状态和输出。

理论依据为[窗口接续与有限跟踪](../../docs/theory/EXCITATION_AND_CONSTRAINED_STABILITY_V1.md)、[学习率 §16](../../docs/theory/MILLION_SAMPLE_SCALAR_MEAN_NOISE_AND_QUANTIZATION_V1.md)及[两级整数损失](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md)。冻结[专用协议](protocol.json)区分主短矩阵、不切换复现、序列化中断、原平台／有理数／正式 bank 探针和长记录预算。短记录不评分不完整相干块。

```powershell
$env:PYTHONPATH='src;.'
python -m experiments.exp_070_gu_learning_rate_switch.prepare artifacts/runs/EXP_070/preflight_v1 --preflight
& experiments/exp_070_gu_learning_rate_switch/run.ps1 -Folder D:/ADC/artifacts/runs/EXP_070/preflight_v1
python -m experiments.exp_070_gu_learning_rate_switch.verify artifacts/runs/EXP_070/preflight_v1
python -m experiments.exp_070_gu_learning_rate_switch.prepare artifacts/runs/EXP_070/tracking_v1 --accepted artifacts/runs/EXP_070/preflight_v1
& experiments/exp_070_gu_learning_rate_switch/run.ps1 -Folder D:/ADC/artifacts/runs/EXP_070/tracking_v1
python -m experiments.exp_070_gu_learning_rate_switch.verify artifacts/runs/EXP_070/tracking_v1
python -m experiments.exp_070_gu_learning_rate_switch.analyze artifacts/runs/EXP_070/tracking_v1
```

在线加速器复用原 Q3 读出和倍率请求，只接收数字字／自身状态；模拟输入、模型与理想目标只进入离线核对／评分。源字不重生，新学习量仍非零。每窗状态保存八个 little-endian int32，输出按任务路径顺序存 int16；详细顺序、初值、全局索引和源文件偏移在 `runplan.json`，分块全部门／基函数／共同支持与更新计数在对应 JSON。

每个运行拒绝覆盖，先核对原交付哈希和最终执行源。全整数重放与原平台有限探针分别报告；普通 FFT 不认证、已见条件不当留出。原经验稳定／恢复与新有限输出定义并列。当前执行状态看 STATUS，不在此 README 改写冻结运行结果。
