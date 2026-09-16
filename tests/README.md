# 测试结构

当前正式测试位于 `tests/test_*.py`，由仓库 README 中的 `unittest discover -s tests`
命令统一发现。`test_project_layout.py` 约束项目边界和关键文件。预留的 `unit/`、
`integration/`、`validation/` 目录分别用于以后按局部正确性、完整信号链和
独立对照组织测试；在相应的测试发现配置就绪前，不把现有测试直接移入这些目录。
