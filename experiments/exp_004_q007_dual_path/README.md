# EXP-004：Q-007 双路径增益与 offset 联合余量

## 研究问题

在 `gu_behavioral_v1` 与默认 dither 下，OJSSCS 报告的约 3% 系统增益差、
trimming 前 0.3%/20 mV Monte Carlo 标准差，以及 trimming 后跨温漂移低于
0.1%/0.5 mV，如何共同改变第二级 flash 的主路径折算边界和冗余余量？

## 方法边界

- `20 mV` 和 `0.3%` 按标准差处理，不误写成硬上限；
- 用 1σ/2σ 矩形角点做确定性压力审计，不从中宣称统计良率；
- post-trim 数值按论文给出的上界做 3σ 包络压力测试；
- offset 首先建模为辅助路径公共输入参考项，比较器独立残差留到后续扩展；
- 理论模块独立计算逐边界窗口，平台只用于码级交叉验证。

## 运行

```powershell
$env:PYTHONPATH = "src"
python experiments/exp_004_q007_dual_path/run.py --run-id <unique-run-id>
```

运行产物写入 `artifacts/runs/EXP_004/<run-id>/`，已有 run 不会被覆盖。
