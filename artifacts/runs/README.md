# 运行产物

正式运行按 `<experiment_id>/<run_id>/` 保存；运行目录应新建，成功、失败与预检记录均保留。除本说明外，本目录默认不提交Git。

建议保存冻结的专用配置／协议、源码与环境来源、结果摘要／指标、观测与状态、图、日志和独立验证。历史运行可以保留平铺文件、NPZ或二进制布局，以及原有 `source_sha256.json`／`source_hashes.json` 等名字；不为统一格式搬动大数据或回写原哈希。

新运行可使用 `traces/`、`figures/`、`logs/` 分组，但应以README或协议明确实际路径。可复现配置与经审查结论分别保存在实验定义及 `docs/reports/`，推导在 `docs/theory/`。

阅读时先查报告与协议，再读summary及verification，最后按需读取状态／观测大文件。本地缺少产物意味着无法复算，不等于可以用新合成数据替代。来源指纹包含机器绝对路径时，迁移须显式解析，不改写原记录冒充同一运行。

2026-10-10整理仅将三份tmp日志复制到EXP-056／057的 `million_v1/logs/`，原件和原产物保留；复制来源与校验见 `artifacts/research/project_organization/20261010_v1/log_copies.json`。
