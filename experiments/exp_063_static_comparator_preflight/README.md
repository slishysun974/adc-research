# EXP-063：逐级固定比较器偏移的安全推导与短预检

执行静态计划5b的推导和预检；与EXP-062名义后台参考衔接，尚不执行长期配对。复用EXP-007逐比较器向量，分别只改第一级、只改第二级，另有零偏移退化控制。CDAC、匹配主辅传输和在线数字合同保持。偏移为声明机制刺激，不是芯片提取或随机失配分布。

理论扩展位于[主辅／阈值理论§13](../../docs/theory/DUAL_PATH_EFFECTIVE_THRESHOLDS_AND_PHASES_V1.md)，独立有理数控制位于[static_comparator_offsets.py](../../src/adc_research/theory/static_comparator_offsets.py)。参数、边界例外、网格和36条32窗口短路径运行前冻结于[协议](protocol.json)。记录全部转换、数字读出、门／基函数／共同支持和提交；零偏移逐窗口／逐输出匹配已有EXP-062前缀，不重跑名义长记录。

从仓库根目录执行：

```powershell
$env:PYTHONPATH='src;.'
python -m experiments.exp_063_static_comparator_preflight.run --run-id preflight_v1
python -m experiments.exp_063_static_comparator_preflight.verify --run-id preflight_v1
```

原平台生成与独立合同核对分开实现；数学精确端点与原双精度不同的受保护边界差单列，禁止静默改观测。所有路径／失败保留；32窗口不是长期收敛或净收益证据，3840转换非相干短块不报单音SNDR。短预检通过后再冻结必要同输入长配对，输入切换／动态保持后续顺序。
