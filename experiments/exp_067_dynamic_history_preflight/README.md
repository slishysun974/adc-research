# EXP-067：动态三路历史与静态退化短预检

本入口执行已批准5d的必要短控制，独立职责是核对当前全程后台合同接入两相三路历史后，每次转换的物理顺序、数字边界和状态承接。推导补入[已有窗口历史文档§6](../../docs/theory/FOUR_LANE_WINDOW_DYNAMIC_LEARNING_V1.md)，参数与验收在[protocol.json](protocol.json)运行前固定。

三原模型×零动态／复位／直接保持，第一原种子，各32窗口；18算法路径全部输出，四点未入选转换仍推进三路历史。复用EXP-062已交付输入和静态短参考，不重跑旧长期记录。原平台及在线Gu均不改，理论参考不导入平台。来源／环境／全部模拟节点／数字字／窗口状态／失败与日志保存于独立运行目录，拒绝覆盖。

从仓库根执行：

```powershell
$env:PYTHONPATH='src;.'
python -m experiments.exp_067_dynamic_history_preflight.run artifacts/runs/EXP_067/preflight_v1
python -m experiments.exp_067_dynamic_history_preflight.verify artifacts/runs/EXP_067/preflight_v1
python -m experiments.exp_067_dynamic_history_preflight.analyze artifacts/runs/EXP_067/preflight_v1
```

逐转换平台运行和独立历史公式全部核对，数字输出／全部提交由独立整数参考及有理数读出核对。窗口16保存三路模拟输出、两个完整数字bank状态及全局标签，承接后缀须逐条一致；另保留错误清零与跳过未选历史的反控制。零动态须复现旧短记录所有码和Q22窗口状态；完全复位仍有放大残差因子，不冒称理想静态。短数据只给有限支持／MSE诊断，不给相干谱、收敛、芯片结论或长期排名。本入口没有长运行选项。
