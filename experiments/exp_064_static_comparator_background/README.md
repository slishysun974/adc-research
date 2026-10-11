# EXP-064：逐级比较器固定偏移的同输入长期配对

执行已批准静态计划§6，三原模型×两原单级向量×五原种子×两原方法，共60新增后台路径。每路径7864320实际转换，名义30路径复用EXP-062交付，不重跑；输入周期表直接复制并核对SHA256。原Q3／Q1.10／Q22、门、步长、窗口、预算及经验判据保持，完整方法学习量多30倍。

独立职责是比较器长配对与全部实际输出／数字提交核对。EXP-063已有边界／安全控制，本实验新增离线加速源，先逐转换对原平台预检，再逐窗口匹配EXP-063原短记录。所有实际转换保存单位、四点、完整输出，逐块保存全部／入选支持、相关量、实际更新与判决改变；第一级四点状态必须逐窗口等于名义，输出仍独立计算。推导见[阈值理论§13.7](../../docs/theory/DUAL_PATH_EFFECTIVE_THRESHOLDS_AND_PHASES_V1.md)，合同见[协议](protocol.json)。

从仓库根目录执行，运行目录拒绝覆盖：

```powershell
$env:PYTHONPATH='src;.'
pwsh -File experiments/exp_064_static_comparator_background/run.ps1 -Output D:/ADC/artifacts/runs/EXP_064/preflight_v2 -Preflight
python -m experiments.exp_064_static_comparator_background.verify artifacts/runs/EXP_064/preflight_v2
pwsh -File experiments/exp_064_static_comparator_background/run.ps1 -Output D:/ADC/artifacts/runs/EXP_064/background_v1 -PreflightPath D:/ADC/artifacts/runs/EXP_064/preflight_v2
python -m experiments.exp_064_static_comparator_background.verify artifacts/runs/EXP_064/background_v1
python -m experiments.exp_064_static_comparator_background.analyze artifacts/runs/EXP_064/background_v1
```

二进制布局继承EXP-062：每转换4字节判决／标签和3个int16最终码，逐窗口8个Q22系数的double表示，探针每窗口1369个double。加速物理源全记录另用向量公式核对，原物理平台按预定32窗口／流探针核对；全部数字输出、提交和计数重放。有限四格诊断使用完整改变的数字观测，保留第一级主残差影响及全部平方交叉，不称八状态因果分解。无芯片参数、输入切换、动态、新算法或调参。
