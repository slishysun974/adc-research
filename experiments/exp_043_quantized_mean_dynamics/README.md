# EXP-043：整数平均更新、停更与门控选择

用既有EXP-039六组记录各前96窗口，研究后级前两系数的整数平均映射。第三、第四项固定为1，但其请求始终计算并保存。N=11520的平均乘120转换步长是明确声明的离线诊断，不替代原每窗口120条更新。

```powershell
$env:PYTHONPATH='src'
python -m experiments.exp_043_quantized_mean_dynamics.run artifacts/runs/EXP_039/window_v1 artifacts/runs/EXP_042/roots_v4 artifacts/runs/EXP_043/mean_v4
$env:MPLCONFIGDIR='D:\ADC\artifacts\tooling\matplotlib_config'
python -m experiments.exp_043_quantized_mean_dynamics.plot_cycles artifacts/runs/EXP_043/mean_v4
python -m experiments.exp_043_quantized_mean_dynamics.finalize artifacts/runs/EXP_043/mean_v4
python -m unittest discover -s tests -p test_quantized_mean_dynamics.py -v
python -m unittest discover -s tests
```

输出目录必须尚不存在；正式产物为`mean_v4`，复跑使用新的EXP_043子目录。`probe.py`及早期输出只属于开发探查，其中额外矩形尝试没有进入正式接受合同。

初始中心来自之前报告的后级连续根，或第一零点直线在16/15的交点；不是按性能择优。矩形搜索顺序固定为导出码中心±1、2、4、8、16，接受首个不变集合。精确枚举完整导出原像的平移，覆盖矩形全部Q22状态。没有停更的不变有限集合最终周期；指定轨迹仅在完整整数状态重复后报周期，且核对周期每一步不重复。事件上限20000，达到上限不能报告找到周期。

独立原定点PWL核对所有使用的导出码对，原四路更新器核对真实窗口越界见证。另保存raw=±47/dither=±16样本的Q3门边界移动。前级理想目标仅进入`evaluation/gated_target_diagnostics.py`及独立离线分解，不进入数字更新。

`finalize.py`核对来源／输出摘要、两个周期的全部第二门切换样本，运行全项目回归与本轮文档链接检查，生成`verification.json`。正式运行269项测试、236个本地链接均通过。图须先实际查看；该脚本本身不能替代视觉检查。

来源EXP-039、EXP-042的摘要、记录与依赖源码运行前后核对SHA-256。无Cadence、模拟重跑、新训练、步长调整、Gu更新或RTL修改。

推导见[理论记录](../../docs/theory/QUANTIZED_MEAN_DYNAMICS_AND_GATE_SELECTION_V1.md)，结论见[实验报告](../../docs/reports/experiments/EXP_043_QUANTIZED_MEAN_DYNAMICS_V1.md)。
