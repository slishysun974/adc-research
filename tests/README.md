# 测试结构

当前正式测试位于 `tests/test_*.py`，由仓库 README 中的 `unittest discover -s tests`
命令统一发现。`test_project_layout.py` 约束项目边界和关键文件，`fixtures/`
保存测试输入。

2026-10-16已取消没有实际测试的 `unit/`、`integration/`、`validation/` 占位目录，
现有测试文件与发现方式保持。若以后确需分层，应同时明确测试发现规则，
不能只移动文件而使默认命令漏测。
