# 候选 A 组合 RTL 的首次功能仿真

> 2026-10-03。只验证仓库自定义的 flash 适配器和逐转换门控乘积；不声明 Gu 芯片逐位复现。

## 环境与运行

只读使用 `D:\SoCLab` 对应 WSL Ubuntu 中的 Icarus Verilog 10.3（`/usr/bin/iverilog`、`/usr/bin/vvp`）。源码、编译产物均位于 `D:\ADC`；没有写入 SoCLab。该版本对当前源码的 `always_comb` 报语法错误，最小探针证实这是工具兼容问题。两个纯组合模块改用 `always @*` 后执行如下命令：

```bash
cd /mnt/d/ADC
mkdir -p artifacts/runs/RTL_GU_CANDIDATE_A/20261003
iverilog -g2012 -s tb_gated_product_candidate_a \
  -o artifacts/runs/RTL_GU_CANDIDATE_A/20261003/gate_tb.vvp \
  rtl/gu_baseline/gated_product_candidate_a.sv \
  rtl/gu_baseline/tb_gated_product_candidate_a.sv
vvp artifacts/runs/RTL_GU_CANDIDATE_A/20261003/gate_tb.vvp
iverilog -g2012 -s tb_flash_thermometer_adapter_a \
  -o artifacts/runs/RTL_GU_CANDIDATE_A/20261003/flash_tb.vvp \
  rtl/gu_baseline/flash_thermometer_adapter_a.sv \
  rtl/gu_baseline/tb_flash_thermometer_adapter_a.sv
vvp artifacts/runs/RTL_GU_CANDIDATE_A/20261003/flash_tb.vvp
```

## 结果与范围

门控模块测试覆盖正、负输出恰等于门限时 `≥`/`>` 两种语义、最小 16 位有符号码的绝对值和乘积、无效转换清零；输出 `gated_product_candidate_a directed checks passed`。flash 入口测试穷举全部 256 个原始八位字：九种理想 thermometer 模式映射到候选 `q=-4…4`，其他 247 个字均报无效且 `q=0`；输出 `flash_thermometer_adapter_a all 256 inputs passed`。

这验证的是**当前候选代码在指定输入和断言下的组合功能**。它不决定论文芯片是否采用该九态编码、式 (7) 的 `≥` 还是 Fig. 10 的 `>`、真实数字位宽或主辅路径来源。门控测试尚非全输入穷举；这些模块也没有抽取、系数更新、时钟和寄存器。综合、时序、功耗及与真实 RTL 同记录逐字对照仍未完成。下一验证门沿[逐转换数字记录协议](DIGITAL_EXTRACTION_TRACE_PROTOCOL_V1.md)取得四路对齐字、抽取器两侧和系数生效时刻；缺此证据时不扩大芯片适用性结论。
