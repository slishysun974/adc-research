# ADC 架构与数字校准硬件汇报材料

这是 2026-10-11 面向电路教师的正式交付。先看六页汇报，再用完整工程包检查实际电路图、网表和波形。数字功能核对通过；100 MHz 综合估计时序未满足，布局布线、板级及模拟晶体管验证尚未开展。

| 下载 | 用途 |
|---|---|
| [六页 PDF](ADC_Circuit_Review.pdf) | 阅读和现场汇报 |
| [可编辑 PPTX](ADC_Circuit_Review.pptx) | 修改架构图、公式、表格与讲稿 |
| [一页复现指南](Reproduction_Guide.pdf) | 打开工程、查看八状态和重跑短测试 |
| [完整工程压缩包](ADC_Circuit_Review_Package.zip) | Vivado `.xpr`、源/向量、DCP、结构 Verilog/EDIF、原生 SVG/PDF 电路图、WDB/VCD、报告与两组优化对照 |
| [发布校验清单](publication_validation.json) | 下载文件 SHA-256、归档/页面/搬移与回归验收 |

下载压缩包请在 GitHub 文件页点击 **Download raw file**。解压到短英文路径（例如 `C:/ADC_review`），在 Vivado 2026.1 打开 `hardware/project/gu_review.xpr`；按包内 `REPRODUCE.md` 或一页指南执行短测试。既有 Vivado/XSim、MATLAB/Simulink 即可使用工程与模型；硬件复算不需要排版脚本使用的本机 Codex 运行时。

本次原基线为2548 LUT/184 FF/4 DSP，WNS −50.309 ns。PWL 位宽候选通过1581056项模块对照及完整有限数字回放，资源为2462 LUT/184 FF/2 DSP，WNS −47.996 ns；它仍未满足100 MHz。两组隔离候选保存在压缩包 `timing_trials/`，六页材料继续展示原基线。浮点 full120 的 SNDR/SFDR 曲线属于已有行为结果，不能归到本次逐转换定点网表。

实现与事实依据见 [复现源码](../../../rtl/gu_baseline/vivado_review/REPRODUCE.md)和[工程与验收报告](../CIRCUIT_REVIEW_VIVADO_RESULTS_2026-10-11.md)。原始百万训练 trace、工具安装、未筛选的工作目录和大体积编译缓存继续保存在本机；这个 ZIP 是已验收的便携交付，不代表全部研究原始数据。
