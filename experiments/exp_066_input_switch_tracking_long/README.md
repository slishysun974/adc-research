# EXP-066：输入幅度切换的必要长期跟踪配对

在[EXP-065](../exp_065_input_switch_tracking/README.md)短预检通过后执行计划5c已预定矩阵。独立职责是保存并评价完整切换后输出与长期跟踪；理论／切换点／输入／判据复用[跟踪理论§8](../../docs/theory/EXCITATION_AND_CONSTRAINED_STABILITY_V1.md)，不重新选参数。原名义三模型、原五种子、两方法、承接与单位初值两初始化，共60算法路径、30物理流；每条128后块／3932160实际转换。原3932160转换前缀只读引用，不重跑。

从原第128块末八个Q22状态继续，幅度0.82→0.41，频率／相位／全局标签不变。新输入单位初值路径使用相同全局标签，隔离继承数字状态。完整学习量多30倍；校准相对同新输入单位不更新输出、承接与新初值的差、有限经验稳定和恢复分开。全部实际转换的源字／输出、状态／提交、分块计数由独立整数公式核对，原平台／有理数／原bank按28窗口／流探针；所有块另用全复FFT与扩展精度MSE独立评分。

```powershell
pwsh -File experiments/exp_066_input_switch_tracking_long/run.ps1 -Output D:/ADC/artifacts/runs/EXP_066/tracking_v1
$env:PYTHONPATH='src;.'
python -m experiments.exp_066_input_switch_tracking_long.verify artifacts/runs/EXP_066/tracking_v1
python -m experiments.exp_066_input_switch_tracking_long.analyze artifacts/runs/EXP_066/tracking_v1
```

长运行拒绝覆盖，先检查EXP-065预检及全部来源，校验原交付数据后复制新协议、冻结全部执行／验证／分析源。没有比较器失配、动态、门／步长／位宽调整、新算法或按结果延长预算。首后块是瞬态；判据为离线机制定义，不证明八状态收敛或芯片恢复时间。
