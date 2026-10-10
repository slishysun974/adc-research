# EXP-039：四路窗口更新与两相主辅动态闭环

无 Cadence 的条件性机理实验。新数字候选每路 30 条、四路共 120 条转换使用共享旧 Q22 系数；门控乘积在窗口末累加、一次舍入／饱和，新系数从下一窗口生效。配对比较逐转换、完整聚合和固定四点抽取；后者的乘积乘 30，匹配窗口时间尺度。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_039_four_lane_dynamic_loop.run artifacts/runs/EXP_039/window_v1
python -m experiments.exp_039_four_lane_dynamic_loop.audit_cross_effects artifacts/runs/EXP_039/window_v1
python -m unittest discover -s tests
```

三条模拟路径独立经过跟踪和放大相位，采用明确的人工平滑三次曲线。训练 15360 次，随后连续接入 3840 点相干正弦并继续在线更新；比较跟踪因子 0、0.1、1，以及独立随机 dither 与两张周期 255 的人工符号表。所有数值、输入和种子固定在脚本中，不声称它们是芯片 PRNG 或真实状态参数。

主程序输出每组 `analog_digital_records.jsonl`、各方法的窗口相关量／系数轨迹／在线整数码，以及带来源摘要的 `summary.json`。辅助审计只读这些文件，检查摘要并输出 `cross_effects.json`：冻结训练终点系数，对复位／保持数字记录作交叉评分，以区分直接记录变化与学习状态变化。该诊断的冻结评分与主实验的在线评分分别标明，不相互替代。

结果见[报告](../../docs/reports/experiments/EXP_039_FOUR_LANE_DYNAMIC_LOOP_V1.md)，合同与推导见[理论记录](../../docs/theory/FOUR_LANE_WINDOW_DYNAMIC_LEARNING_V1.md)。浮点电压和频谱是近似模拟／评分，本次没有扩展频谱认证或实现新硬件。
