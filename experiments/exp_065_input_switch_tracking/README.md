# EXP-065：静态输入切换的状态承接与短预检

本实验执行已批准计划5c的合同／推导与短预检，独立职责是从已有EXP-062全程后台状态接续输入变化，核对Q22隐藏状态、全局dither标签、同步窗口与实际输出。三原名义静态模型，原两方法，第一原种子；不加比较器失配或动态。协议见[protocol.json](protocol.json)，推导见[已有跟踪理论§8](../../docs/theory/EXCITATION_AND_CONSTRAINED_STABILITY_V1.md)。

切换位于全局3932160转换／32768窗口／128块末，幅度0.82→0.41，127/30720频率和相位不变。直接复用并校验原前半段与两个方法各自的八个Q22状态。不改变输入的34窗口接续须逐码／逐状态等于原记录；切换路径保存2前窗口与32后窗口，单位初值的新输入对照从同一全局标签开始32窗口。全部9物理流／18算法路径／36000实际转换由独立整数公式、有理数读出、原平台及原bank提交完整核对。短窗口不报SNDR/SFDR或恢复时间。

从仓库根运行（本机使用已配置的pwsh和Python运行时）：

```powershell
pwsh -File experiments/exp_065_input_switch_tracking/run.ps1 -Output D:/ADC/artifacts/runs/EXP_065/preflight_v1
$env:PYTHONPATH='src;.'
python -m experiments.exp_065_input_switch_tracking.verify artifacts/runs/EXP_065/preflight_v1
python -m experiments.exp_065_input_switch_tracking.analyze artifacts/runs/EXP_065/preflight_v1
```

运行拒绝覆盖，来源与原交付文件先冻结SHA256。原Gu／平台／RTL及已有实验源保持。后续必要长记录的60条配对、128后块预算和离线跟踪判据在协议运行前声明；本入口只执行短预检，长入口须在短结果分析后接续实现和冻结，长记录尚未生成。单位参考、输入真值及跟踪判据均不进入在线更新。
