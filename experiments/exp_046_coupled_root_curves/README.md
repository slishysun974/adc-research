# EXP-046：两级共同零点和量化后的请求

后级前三系数自由、第四为1；前级前两自由、第三／第四为1。沿EXP-045后级线段在内部四分点及范围内单位值上求前级根，然后证明每个局部范围内八相关量恒零。理想目标只用于独立冻结评分。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_046_coupled_root_curves.run artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_045/local_v2 artifacts/runs/EXP_046/curves_v1
python -m experiments.exp_046_coupled_root_curves.integer_curve_boxes artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_045/local_v2 artifacts/runs/EXP_046/curves_v1
python -m experiments.exp_046_coupled_root_curves.transverse_stability artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_046/curves_v1
$env:MPLCONFIGDIR='D:\ADC\artifacts\tooling\matplotlib_config'
python -m experiments.exp_046_coupled_root_curves.plot_results artifacts/runs/EXP_046/curves_v1
python -m experiments.exp_046_coupled_root_curves.finalize artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_045/local_v2 artifacts/runs/EXP_046/curves_v1
```

主入口输出目录必须尚不存在；正式产物为`curves_v1`。复跑使用新的EXP_046子目录。整数曲线范围入口也拒绝覆盖已存在的同名结果。图需实际查看，验收程序不能代替视觉检查。

前级低段系数由二次多项式比值给出。初始半宽1/1024受后级端点距离限制，依次检验对称／右／左区间，最多60次减半；保护分母、系数、数字分段和全部门。17份局部证书不等于17条不同全局分支。

整数平均诊断是11520条均值乘120转换步长；窗口诊断是96个窗口独立冻结于同一导出种子，没有连续提交。导出码范围的笛卡尔积是保守包含，60个组合全部排除平均不动状态，不据此声称长期发散。

前级稳定性只在固定后级、两个低段及合法门邻域中检查。局部平均稳定不等于全部八状态或实际整数窗口稳定。冻结正弦评分使用原3840点、第67基波、全速3 GS/s；浮点FFT未数值认证。

无新训练、物理数据、Cadence或Gu／RTL修改。见[推导](../../docs/theory/COUPLED_MEAN_ROOT_CURVES_AND_INTEGER_REQUESTS_V1.md)、[实验报告](../../docs/reports/experiments/EXP_046_COUPLED_ROOT_CURVES_V1.md)及[现状说明](../../docs/reports/RESEARCH_STATUS_PLAIN_2026-10-09.md)。
