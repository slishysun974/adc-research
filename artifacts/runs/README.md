# 运行产物

建议结构：

```text
<experiment_id>/<run_id>/
├─ resolved_config.yaml
├─ environment.json
├─ metrics.json
├─ traces/
├─ figures/
└─ logs/
```

除本说明外，本目录默认不提交 Git。可复现配置和经过审查的结论应分别提升到 `configs/` 与 `docs/reports/`。

