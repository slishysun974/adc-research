# ADC Advisor Progress - Design Spec

## I. Project Information

- Project Name: advisor_progress
- Canvas Format: ppt169, 1280x720
- Page Count: 28, including 24 main pages and 4 appendix pages
- Target Audience: 熟悉Gu论文、尚不了解本课题进展的数模混合IC设计导师
- Use Case: 可独立阅读的阶段进展汇报，后续按页讨论
- Delivery Purpose: balanced，正文24，降低单页密度，保留解释句
- Content Strategy: 严格沿用用户确认的七模块提纲。研究问题、方法、结果及结论各有明确位置。
- Created Date: 2026-10-16
- Authorization: 用户本轮要求按既有提纲设计简洁明了的汇报PPT，设计细节按此要求执行。

## II. Canvas Specification

- Format: ppt169
- Dimensions: 1280x720
- viewBox: 0 0 1280 720
- Margins: left/right 64, top 42, bottom 40
- Content Area: x=64..1216, y=145..626

## III. Visual Theme

- Mode: instructional
- Visual style: swiss-minimal
- Theme: white
- Tone: 专业、平实，明确条件，使用电路语言
- Background: #FFFFFF
- Secondary bg: #F2F5F8
- Primary: #16324F
- Accent: #226E9C
- Secondary accent: #21857A
- Body text: #243746
- Secondary text: #596D7B
- Border/divider: #D7E0E7
- Warning: #B15B36
- Muted data: #9AA9B4
- No decoration, no icons, no AI images, no animations.

## IV. Typography System

| Role | Chinese | Latin | Fallback |
| --- | --- | --- | --- |
| Title | Microsoft YaHei | Arial | sans-serif |
| Body | Microsoft YaHei | Arial | sans-serif |
| Emphasis | Microsoft YaHei | Arial | sans-serif |
| Code | Microsoft YaHei | Consolas | monospace |

- Title / Body / Emphasis stack: "Microsoft YaHei", Arial, sans-serif
- Code stack: Consolas, "Microsoft YaHei", monospace
- Body: 24
- Page title: 40
- Subtitle / core message: 28
- Subheading: 28
- Annotation: 20
- Footnote: 15
- Cover title: 64
- Hero number: 56
- Section numeral: 44
- Line spacing: body 38..42, note 26..30

## V. Layout Principles

- 页码固定右下。页眉仅保留模块名，主标题直接说明主题。
- 正文使用开放的平面排版。表格、图与解释句按内容安排，避免卡片网格。
- 科学关系图只表达实际信号、学习连接或受控比较，无装饰性示意图。
- 主结论不小于正文。条件和来源放在相关图旁或页脚。
- 一页一个主要问题，优先拆页，保留足够留白。

## VI. Icon System

无图标。所有几何图元用于信号关系、时序、表格或数据图。

## VII. Visualization Reference List

以下结构参考已读图表目录，按本课题内容手工重构。不直接复用模板SVG，page_charts记录none。

| Page | Visualization | Selection | Data / geometry |
| --- | --- | --- | --- |
| P04 | ADC信号与学习连接 | no-template-match，主辅与反向数字重构需要自定连接 | layout-driven |
| P11 | 两种系数选择的MAE柱图 | column_chart | 0.92068, 0.65701，plot x=125..655,y=275..545, axis 0..1.2 |
| P13 | 120次转换的采用与提交 | no-template-match，样本槽和旧系数语义 | layout-driven |
| P16 | 后期整数MSE | grouped_bar_chart | 15.827,33.945,9.288,32.176,34.406,10.166，plot x=110..770,y=250..550, axis 0..40 |
| P19 | 四字与全槽20案例散点 | scatter_chart | 原EXP-075保存损失，x,y均0..60，plot x=85..605,y=220..570 |
| P21 | 单案例门源与合法系数参照 | horizontal_bar_chart | 3.333927623,3.059911930,3.445446290,3.194836766,1.920095347，plot x=360..900,y=245..550, axis 0..4 |

Selection summaries:
- column_chart: Pick for single-series category value comparison, 3-8 categories. Skip for >12 long-label items (use horizontal_bar_chart) or multi-series (use grouped_bar_chart).
- grouped_bar_chart: Pick for 2-4 series side-by-side across the same categories (e.g. YoY/QoQ). Skip if showing composition within each category (use stacked_bar_chart).
- scatter_chart: Pick for x-y correlation, cluster, or outlier scan. Skip if a size dimension also matters (use bubble_chart).
- horizontal_bar_chart: Pick for ranking 5-12 items, especially with long labels. Skip if <=8 short-label items (use column_chart).
- P11 uses two important endpoints only. A table could obscure the error magnitude, while a line would imply an unavailable full objective curve.
- P19 uses one point per paired case. A dumbbell chart with20 labels and a grouped chart with40 bars would crowd the reading page.
- P21 preserves comparison order and offline information labels. It is a comparison, not an inferred causal percentage ranking.

## VIII. Image Resource List

No raster images. Figures and tables are editable SVG primitives. Data values come from copied module reports and saved JSON summaries. No new ADC simulation, learning, scoring, or FFT is run.

## IX. Content Outline

| Page | Module | Title / intent | Layout |
| --- | --- | --- | --- |
| P01 | Cover | 流水线ADC数字后台校准研究 | typography, left aligned |
| P02 | Opening | 研究目标与当前进展 | goal + progress + open relation |
| P03 | Overview | 七个模块的研究安排 | numbered open list |
| P04 | M1 | 实验平台的信号与信息边界 | actual signal diagram |
| P05 | M1 | 平台核对与可交付模型 | evidence rows + artifact |
| P06 | M2 | 给定模拟传输下的性能预测 | method stages |
| P07 | M2 | 条件性预测的成果与适用范围 | comparison table |
| P08 | M3 | Gu数字校正与定点实现 | reconstruction + precision |
| P09 | M3 | RTL功能与FPGA实现进展 | resource table + timing |
| P10 | M4 | 数字观测能够约束什么 | observation example |
| P11 | M4 | 相关量为零与输出误差最小 | two candidate values + bar |
| P12 | M4 | 信息、表示与在线取得 | distinct questions |
| P13 | M5 | 学习样本与系数提交时刻 | editable window diagram |
| P14 | M5 | 启动、持续波动与平均偏差 | scalar controlled results |
| P15 | M6 | 持续后台运行的评价方法 | frozen vs updating |
| P16 | M6 | 学习率与后期整数误差 | grouped bars |
| P17 | M6 | 后期误差与切换恢复的取舍 | explicit recovery definition + result |
| P18 | M7 | 剩余误差的受控分析方法 | paired intervention |
| P19 | M7 | 增加采用样本的效果与限制 | 20-case scatter |
| P20 | M7 | 剩余六例的两种增损关系 | flat categorical rows |
| P21 | M7 | 一个门来源的深入对照 | horizontal bars + information cost |
| P22 | M7 | 学习历史与尚未取得的改善 | supported causal chain in words |
| P23 | Synthesis | 当前阶段形成的主要认识 | 4 findings |
| P24 | Next | 下一步研究的关键关系 | information + online + fair evaluation |
| P25 | Appendix A | 指标与比较口径 | definitions |
| P26 | Appendix B | Gu原文与本项目候选 | source/candidate table |
| P27 | Appendix C | 阅读索引与证据入口 | source map |
| P28 | Appendix D | 未完成项与保留限制 | finite evidence limits |

Cover impact: 以“数字后台校准”为清晰学术主题，使用两行大标题和充足留白，底部列出Gu基线、学习过程与剩余误差三个研究对象。不放装饰插图。
Closing impact: 给出已明确的下一关系，说明当前课题的延续方向，避免泛泛的致谢页。

## X. Speaker Notes & Delivery

- Each page has explanatory notes and original evidence paths.
- Main pages are independently readable. Notes add definitions and source detail, not missing core claims.
- Deliverable: ADC课题阶段汇报_v1_2026-10-16.pptx.
- Readme provides fixed page ranges for follow-up questions.
- Render every page, inspect content and fit, verify chart geometry against saved values, and validate the native PPTX package.
