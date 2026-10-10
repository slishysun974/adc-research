# EXP-045：第三系数释放后的局部相关目标

第四系数固定为1，前三参数自由。预定第三切片3/4、7/8、1、9/8、5/4只产生种子；认证结果中的第三参数在连续区间内自由移动，没有固定在切片上。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_045_released_third_roots.run artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_044/ordered_v1 artifacts/runs/EXP_045/local_v2
$env:MPLCONFIGDIR='D:\ADC\artifacts\tooling\matplotlib_config'
python -m experiments.exp_045_released_third_roots.plot_segments artifacts/runs/EXP_045/local_v2
python -m experiments.exp_045_released_third_roots.finalize artifacts/runs/EXP_045/local_v2
```

输出目录必须尚不存在；正式产物是`local_v2`，复跑使用新的EXP_045子目录。`probe.py`及`local_v1`为开发探查。图生成后须实际查看。

每个种子形成固定门仿射矩阵。满秩候选必须留在合法域并保持门；秩2根沿零空间得到参数线，再交全部开闭门半空间，保护整个线段及第四相关量。去重只合并完全相同的参数式／范围。

该方法没有枚举全部三维门单元，候选拒绝或无认证不能报告全域无解；局部线段最大也不等于整个根集合已完成。前级、Q3／Q22整数停更及实际更新可达性均未认证。

只读取后级数字码和dither，理想目标不进入求根或验证。来源／源码摘要运行前后核对，无新训练、物理样本、Cadence或Gu修改。结果见[报告](../../docs/reports/experiments/EXP_045_RELEASED_THIRD_ROOTS_V1.md)及[推导](../../docs/theory/RELEASED_THIRD_ROOT_SEGMENTS_V1.md)。

正式验收285项测试、256个本地文档链接及23个有理数线段检查点通过。独立数字读出Gram在六组均秩3，只描述数字函数敏感性，不能改称物理可观测性或正确目标。
