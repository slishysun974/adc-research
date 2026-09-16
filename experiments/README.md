# 可复现实验

每个正式实验使用独立目录：

```text
exp_NNN_short_name/
├─ README.md
├─ config.yaml
└─ run.py
```

`README.md` 说明问题、假设、变量、指标和验收条件；`run.py` 只负责调用正式源码，不在脚本中重复实现核心模型。运行结果写入 `artifacts/runs/`。
实验专用配置保留在该实验目录；需要跨实验复用的架构和非理想配置放在 `configs/`。
