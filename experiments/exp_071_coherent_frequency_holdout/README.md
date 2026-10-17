# EXP-071：固定 Gu 候选的新相干输入频率验证

接续 D-129 四项主线的任务4。首批只选一类验证轴：在同一已见、无记忆两级平滑模型和幅度下改变相干正弦的时间排列。原三代表块与完整组的同字损失差、块间输出变化，以及固定表示能力范围，说明必须区分静态可达校正与实际学习轨迹，见[正常两级 §14](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md)。

**D-132完成最终实现预检、80在线／20单位的固定128块确认；原端点失败与全部末端失败保持。两项冻结预测支持，未来保留未消费，D-129本批有限计划验收。** 实际结果见[报告 §6](../../docs/reports/experiments/EXP_071_COHERENT_FREQUENCY_PREFLIGHT_V1.md)，执行门看STATUS。原[协议](protocol.json)保持，固定509／1009两个开发频点、2003／4001两个 Gu 确认频点、五个新种子、指标、固定终点和预算。四个用例保持既有模拟模型、五字段、Q3／Q1.10／Q22、dither幅度、门和120槽提交；原倍率、1/4及单位参考、point30／full120分开评价。

30720点正弦表由原 EXP-062 的存储表作模排列，保持输入数值多重集的逐位一致；dither仍由全局转换索引产生，并不随输入表一起排列。均匀四标签的静态离线控制在排列下有相同码 MSE／固定表示能力；实际 counter 标签、动态状态及因果更新不满足该排列前提，所以不预设实际 Gu 轨迹或收益不变。这是模型内的时序／选样验证，不声明电路带宽或高频建立得到验证。

6007／8009等频率作为未来新算法保留条件，只规定生成规则和用途，本阶段不生成校准结果、诊断或排名。Gu 确认用例先保持封闭；开发预检、执行实现、来源、预测和预算完全冻结并验收后才开封，开封后全部种子和失败进入结果。已消费 Gu 留出不能再证明未来新算法泛化。

本设计只使用本阶段首批上限的一半长预算：80在线路径，各128块／3932160槽，另20共享单位参照。[开发入口](preflight.py)已完成正常路径、承接和逐码独立核对；v1失败与v2完整端点诊断均保留，v2 `passed=false`，不能作为长入口。初始README的设计快照、后续执行来源、输入及环境分别归档，不修改原协议和历史EXP-062／069／070入口。

D-131新增[边界合同](boundary_contract_v2.json)，仅修订全量程压力端点的验收对象；0.82工作路径仍要求取整前／后都无裁剪。[NG-34](../../docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md)给解析单位界、随当前系数的充分范围及饱和MSE关系。保存数据v3探针计数失败保留，v4完成68独立探针、109584整数／Q3读出，原12端点越界保持。复算使用新空目录，拒绝覆盖：

```powershell
$env:PYTHONPATH='src;.'
python -m experiments.exp_071_coherent_frequency_holdout.check_boundary_contract artifacts/runs/EXP_071/boundary_audit_new
```

该入口验证原数据／源码定义的连续性，不生成输入、训练、FFT或确认结果。`boundary_preflight_accepted=true`不等于`long_ready=true`：下一须实现并冻结最终长执行／来源／存储及其开发短核对，Gu确认和未来保留均未开封。


D-132最终实施复用原整数读出／门／请求提交，新增[源与控制](Kernel.cs)、[冻结](prepare.py)、[调度](run.ps1)、[独立核对](verify.py)和[完整评分](analyze.py)，方法／预算先见[执行合同](execution_contract_v1.json)。实际运行是 `final_preflight_v1` 和 `background_v1`。预检＋长在线314634240码、每级学习162561024、双bank提交2621952；长12800块／25600普通FFT及全部源／数字重放通过，536回归通过。确认后期预测20／20、full120启动排序10／10支持，point30／quarter确认末端各4／5，旧稳定末端0／80。

以上原D-131段落记录当时状态；其后最终预检才获得入口，长记录／评分另各自验收，不能把原门追改为通过。2003／4001已消费，复算也是已见条件，不能产生新的独立留出或未来算法泛化证据。复算须有全套既有数据、使用新目录，旧目录拒绝覆盖；未来6007／8009不得复用此入口生成成绩。

```powershell
$env:PYTHONPATH='src;.'
python -m experiments.exp_071_coherent_frequency_holdout.prepare artifacts/runs/EXP_071/final_preflight_new --preflight
& experiments/exp_071_coherent_frequency_holdout/run.ps1 -Folder D:/ADC/artifacts/runs/EXP_071/final_preflight_new
python -m experiments.exp_071_coherent_frequency_holdout.verify artifacts/runs/EXP_071/final_preflight_new
python -m experiments.exp_071_coherent_frequency_holdout.prepare artifacts/runs/EXP_071/background_new --accepted artifacts/runs/EXP_071/final_preflight_new
& experiments/exp_071_coherent_frequency_holdout/run.ps1 -Folder D:/ADC/artifacts/runs/EXP_071/background_new
python -m experiments.exp_071_coherent_frequency_holdout.verify artifacts/runs/EXP_071/background_new
python -m experiments.exp_071_coherent_frequency_holdout.analyze artifacts/runs/EXP_071/background_new
```

结果、全部种子／失败与实际边界见[报告 §7—8](../../docs/reports/experiments/EXP_071_COHERENT_FREQUENCY_PREFLIGHT_V1.md)。新算法、硬件及追加矩阵仍须讨论；本批完成不当作未知传输通用解或芯片验证。
