# EXP-062：同一正弦输入从单位初值起的全程后台评价

执行当前静态计划5a，名义flash阈值、匹配静态主辅、末级8位TI-SAR和原Q3／Q1.10／Q22窗口合同。理想／两级线性／两级平滑三个已见条件、五新种子，两种学习方式各7864320次实际转换；完整累计多30倍学习观测，不能称同硬件成本。全部未选槽位也转换并保存输出；观察块不暂停更新。

新增问题、有限净收益恒等式与周期相位选样见[静态两级理论§6](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md)。具体预算、经验收敛判据、后半段统计、源指纹与核对范围运行前冻结在[协议](protocol.json)。没有比較器偏移、输入切换、动态、新算法或调参；这些按原计划接续。

仓库根目录执行：

```powershell
$env:PYTHONPATH='src;.'
pwsh -File experiments/exp_062_same_input_background/run.ps1 -Output D:/ADC/artifacts/runs/EXP_062/preflight_v1 -Preflight
python -m experiments.exp_062_same_input_background.verify artifacts/runs/EXP_062/preflight_v1
pwsh -File experiments/exp_062_same_input_background/run.ps1 -Output D:/ADC/artifacts/runs/EXP_062/background_v1 -PreflightPath D:/ADC/artifacts/runs/EXP_062/preflight_v1
python -m experiments.exp_062_same_input_background.verify artifacts/runs/EXP_062/background_v1
python -m experiments.exp_062_same_input_background.analyze artifacts/runs/EXP_062/background_v1
```

`tone.bin`保存声明的一周期双精度输入。每个条件／种子的`words.bin`按每转换4字节保存q1、q2、SAR中心码（各signed8）及两dither正号bit；`outputs.bin`每转换三个little-endian int16为不更新单位／四点／完整的最终整数码。两个`q22.bin`逐窗口保存八个double系数（其值精确等于Q22整数除2^22），包含单位初值。`probes.bin`每窗口1369个double：窗口号、两组旧状态16、120条(x,d1,d2,q1,q2,z1,m,a,z2,r2,SAR)1320、两组相关和16、两组新状态16。JSON保存逐块入选／全部转换门、基函数、共同支持和相关量，以及实际状态／导出改变。预检及长期目录均拒绝覆盖，失败保留。

原平台核对预定全部／探针转换；独立整数实现核对所有实际输出与所有数字提交，另全记录重生标签及向量物理公式。它不声称全记录都以原Python物理平台重跑，经验稳定亦不证明八状态平稳分布或芯片表现。
