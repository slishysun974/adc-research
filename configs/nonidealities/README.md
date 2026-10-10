# 非理想配置

保存可复用的 mismatch、噪声、增益、非线性和动态误差参数组。参数单位及来源必须明确。

- `gu_gate_d_static_v0_1.yaml`：用于 Gate D 的合成静态非理想 profile；验证
  flash threshold、CDAC mismatch、线性主增益和 PWL truth 的开关隔离及组合
  顺序，不代表芯片统计分布。

这里的 `PWL truth` 由离线测试者设置，供评分和验证；在线数字校准算法不能读取其分段或斜率。当前四阶段路线将加入不与数字分段对齐的非 PWL 测试曲线，不能把这个配置当成默认物理放大器。
