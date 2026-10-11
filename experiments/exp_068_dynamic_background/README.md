# EXP-068：有限动态全程后台配对

在已批准5d／计划§9内检验EXP-067的复位与保持条件是否改变同输入净收益、状态波动和第三段支持。三原模型／五原种子／两历史／两原方法，固定128相干块；静态同源参考只读复用EXP-062前128块。全部实际转换推进三路历史，四点不跳槽。理论扩展在[窗口理论§6.6—6.7](../../docs/theory/FOUR_LANE_WINDOW_DYNAMIC_LEARNING_V1.md)，完整运行前合同见[protocol.json](protocol.json)。

独立职责是动态长输出与历史核对；不改平台／在线Gu，不新增扫描或算法。源码、协议、环境、原始字／码／Q22／窗口模拟历史、探针与失败保存，拒绝覆盖。原平台全短核对后才允许长运行；长数字全重放、独立物理递推全字／历史核对，原平台按声明探针核对。

从仓库根执行：

```powershell
$env:PYTHONPATH='src;.'
pwsh -NoProfile -File experiments/exp_068_dynamic_background/run.ps1 artifacts/runs/EXP_068/preflight_v1 -Preflight
python -m experiments.exp_068_dynamic_background.verify artifacts/runs/EXP_068/preflight_v1
pwsh -NoProfile -File experiments/exp_068_dynamic_background/run.ps1 artifacts/runs/EXP_068/background_v1 -PreflightPath artifacts/runs/EXP_068/preflight_v1
python -m experiments.exp_068_dynamic_background.verify artifacts/runs/EXP_068/background_v1
python -m experiments.exp_068_dynamic_background.analyze artifacts/runs/EXP_068/background_v1
```

实现通过门与收益分开。启动谱不称稳态，经验判据首次通过后仍报告后续违反，预算不延长；五已见种子不当作芯片成功率或独立留出。仅本地研究，不提交／推送。
