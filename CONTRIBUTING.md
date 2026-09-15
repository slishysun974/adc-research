# 参与贡献

欢迎通过 Issue 和 Pull Request 参与本项目的维护。贡献可以包括缺陷修复、实验复现、
理论推导、测试、文档改进和来源核验。

## 工作流程

1. 先阅读 `docs/PROJECT_CHARTER.md`、`docs/STATUS.md` 和 `docs/DECISIONS.md`。
2. 对范围较大的工作，先建立 Issue，说明目标、方法、预期证据和影响范围。
3. fork 仓库并从 `main` 创建主题分支；一次 Pull Request 聚焦一个完整问题。
4. 保持实验平台与解析预测器独立实现，并标明参数和结论的来源类型。
5. 运行测试并在 Pull Request 中记录命令、关键结果、假设与局限。
6. 阶段性结论完成时，同步更新状态、决策或报告文档，并提交和推送对应的 Git 变更。

## 本地检查

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

请勿提交 `references/local/` 中的本地论文、`artifacts/runs/` 中的运行产物、密钥、
个人信息或无法公开再分发的材料。需要保留的结论应整理到 `docs/reports/`，并附上可复现配置。
