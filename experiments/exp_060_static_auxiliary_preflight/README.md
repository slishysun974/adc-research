# EXP-060：主辅静态失配的信号合同与正向预检

接续EXP-059和当前静态定点计划。独立辅路读取与主路相同的第一级求和节点，第二级flash读取辅路、CDAC读取主路；只有末级8位TI-SAR。复用两相平台的零放大因子特例，不改生产平台或Gu算法。

[协议](protocol.json)在运行前冻结八个指定静态条件、固定网格、两个新种子和16窗口短控制。它检验[主辅理论§8—11](../../docs/theory/DUAL_PATH_EFFECTIVE_THRESHOLDS_AND_PHASES_V1.md)：CDAC分支抵消、后级残差传播、理想输出相同但学习门不同、条件平衡dither零相关。不是稳态估计或新算法排名。

从仓库根目录执行：

```powershell
$env:PYTHONPATH = "src;."
python experiments/exp_060_static_auxiliary_preflight/run.py --run-id preflight_v1
python experiments/exp_060_static_auxiliary_preflight/verify.py --run-id preflight_v1
```

运行目录必须不存在；冻结配置、源码指纹、完整记录、失败及日志存于 `artifacts/runs/EXP_060/<run-id>`。独立核对保持数学有理数与原双精度端点合同的区别，不用理想目标反馈在线学习。结果见[报告](../../docs/reports/experiments/EXP_060_STATIC_AUXILIARY_PREFLIGHT_V1.md)。
