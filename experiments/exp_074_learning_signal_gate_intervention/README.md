# EXP-074：后级进入前级学习的读出与门通道

固定原五种子、两倍率、两起点和[128,136)，新增“学习数值取移动后级／门取保持后级”及相反两个混合政策的40条前级路径。前级自己的门和读出仍按当前状态／源变化，切断的仅为后级参数进入某学习输入的连接；输出始终用移动后级。额外shadow读出仅为诊断，不是新算法或同资源收益验收。

完整[协议](protocol.json)、[报告](../../docs/reports/experiments/EXP_074_LEARNING_SIGNAL_GATE_INTERVENTION_V1.md)及[NG-41](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md#18-ng-41后级进入前级学习的读出与门通道)说明必要性、全部预测、预算、两个顺序和范围。原双级／双切断角点由NG-40证明与完整预检复现，后级自治记录复用。

原冻结流程在正式编号登记前运行`prepare --out <新目录> --support <已完成请求分析目录>`，然后`run`与`verify`。本对象已完成，prepare拒绝重复编号，run拒绝覆盖完成目录。需要复算时先复制完整已保存运行到新目录，再用其中`frozen_run.py verify --out <复制目录>`，保留新的核对日志／计数；不要覆盖原归档验收。记录位于`artifacts/runs/EXP_074/learning_channels_v1/`。

第二门旧历史分析见[报告§6](../../docs/reports/experiments/EXP_074_LEARNING_SIGNAL_GATE_INTERVENTION_V1.md#6-第二门的历史传导与有益有害条件旧轨迹分析)及[NG-42](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md#19-ng-42第二门的参数历史传导输出支持与有益条件)。[analyze_gates.py](analyze_gates.py)按原40对／320块分开直接门驱动、自身历史响应、两低坐标输出差及目标交叉；只读取已有轨迹，不运行新学习或更改原协议。固定支持／导出符号分类、全部小效应及额外预算在`artifacts/research/second_gate_history_20261013_v1/`。

该只读核查用`$env:PYTHONPATH='src;.'`后运行`python -m experiments.exp_074_learning_signal_gate_intervention.analyze_gates prepare --out <新分析目录>`，再按冻结脚本运行`analyze --out <同目录>`。它拒绝覆盖完整结果；prepare会记录当前源码指纹，原验收目录／源码不改，Python启动路径提示不等于数值核查失败。这里只核对已见对象，新的时间／模型／算法不由此授权。

第一历史响应与共同相位目标投影见[报告§7](../../docs/reports/experiments/EXP_074_LEARNING_SIGNAL_GATE_INTERVENTION_V1.md#7-第一历史响应的输出抵消与共同相位目标认证)及[NG-43](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md#20-ng-43第一历史响应的相关驱动输出抵消与共同相位目标约束)。独立只读入口[analyze_response.py](analyze_response.py)复用原40对／320块，核对第一请求的两相关驱动、输出平方／损失的区别及NG-39共同相位范围，未运行新学习。冻结与全部证据在`artifacts/research/first_response_projection_20261013_v1/`。

同样以`$env:PYTHONPATH='src;.'`运行模块`experiments.exp_074_learning_signal_gate_intervention.analyze_response`的`prepare --out <新目录>`及冻结后的`analyze --out <同目录>`；拒绝覆盖结果。prepare冻结全部来源与有限预算，发现来源／算术不一致即保存失败；原盒未认证记录不被新投影证书覆盖改写。它评价保存路径，未来政策／未知输入和硬件成本仍未验收。

第一段的采样、读出来源与目标矩核对见[报告§8](../../docs/reports/experiments/EXP_074_LEARNING_SIGNAL_GATE_INTERVENTION_V1.md#8-第一段采样读出来源与目标矩的同对象核对)／[两级§21](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md#21-正常第一段的采样读出来源与目标矩核对ng-2143补充)。[analyze_moments.py](analyze_moments.py)复用NG-21／43与原40对／320块，核对第一目标交叉的六项、四字／归一化全槽响应及第一名义判决的目标外界；不新编NG／EXP或传播学习政策。全部冻结、结果与原字节在`artifacts/research/first_moment_audit_20261013_v1/`。

运行模块`experiments.exp_074_learning_signal_gate_intervention.analyze_moments`的`prepare --out <新目录>`、`analyze --out <同目录>`，仍需`$env:PYTHONPATH='src;.'`，仍拒绝覆盖结果。全槽只是原四字定标下的相关比较，不能当同成本完整累计策略；六项截断不提供独立因果份额，目标范围失败不证明完整历史不可识别。

采样差与状态历史见[报告§9](../../docs/reports/experiments/EXP_074_LEARNING_SIGNAL_GATE_INTERVENTION_V1.md#9-采样差dither分组与参数历史关联)、[NG-44／Dither§11](../../docs/theory/DITHER_INFORMATION_AND_STOCHASTIC_UPDATE_AUDIT_V1.md#11-ng-44名义正弦的低阶采样匹配不保持带状态权重的相关)及[两级§22](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md#22-ng-44采样差与参数历史的有限关联)。[analyze_sampling_history.py](analyze_sampling_history.py)仅重建最小两级Q3读出，核对时间／重复输入相位协方差、标签／四槽组分解和名义输入矩，不生成门／请求／学习政策。

同样以`$env:PYTHONPATH='src;.'`运行该模块的`prepare --out <新目录>`、`analyze --out <同目录>`，仍拒绝覆盖。结果在`artifacts/research/sampling_history_20261013_v1/`，其中40份2048×13 int64窗口矩、协议列名／分母及`compact_moment_hashes.json`支持后续只读复用；先查指纹，已有矩足够就不重复整套读出。名义低阶匹配、分区关联与目标／未来保证分别判断。

评价前固定状态的同字参照见[报告§10](../../docs/reports/experiments/EXP_074_LEARNING_SIGNAL_GATE_INTERVENTION_V1.md#10-评价前固定状态的同字采样参照)及[NG-45／两级§23](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md#23-ng-45评价前状态参照下的采样差参数替换与q3界)。[analyze_anchor_sampling.py](analyze_anchor_sampling.py)先验收原窗口矩，再仅补固定／混合参数的缺格读出，保留原k历史与两个参数替换顺序，没有传播新学习。

模块`experiments.exp_074_learning_signal_gate_intervention.analyze_anchor_sampling`仍用`prepare --out <新目录>`及冻结后`analyze --out <同目录>`，仍需`$env:PYTHONPATH='src;.'`且拒绝覆盖。完整结果在`artifacts/research/anchor_sampling_20261013_v1/`；40份新2048×7 int64矩4587520字节及指纹支持继续复用。固定背景、当前读出参数修正、Q3交互和目标损失分别判断，已有矩足够就不再计算同字读出。
