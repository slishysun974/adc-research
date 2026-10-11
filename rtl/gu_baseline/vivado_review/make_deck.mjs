import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation,PresentationFile} from '@oai/artifact-tool';

const workspaceDir=process.argv[2];
const SKILL_DIR='C:/Users/17765/.codex/plugins/cache/openai-primary-runtime/presentations/26.1009.11318/skills/presentations';
const RUNTIME_PYTHON='C:/Users/17765/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
process.env.RUNTIME_NODE_MODULES='C:/Users/17765/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const FONT='Microsoft YaHei';
const C={ink:'#172B4D',teal:'#087F8C',orange:'#AF501E',gray:'#536477',line:'#D8E1E9',pale:'#EFF7F8',warm:'#FFF4EA'};
const p=Presentation.create({slideSize:{width:1280,height:720}});
p.theme.defaultFont=FONT;

function text(s,value,x,y,w,h,size=23,bold=false,color=C.ink,fill='none'){
  const o=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill,line:{fill:'none',width:0}});
  o.text=value;o.text.style={typeface:FONT,fontSize:size,bold,color};o.text.insets=0;return o;
}
function box(s,value,x,y,w,h,color=C.teal,size=23){
  const o=s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill:'#FFFFFF',line:{fill:color,width:1.6}});
  o.text=value;o.text.style={typeface:FONT,fontSize:size,color:C.ink,alignment:'center',verticalAlignment:'middle'};
  o.text.insets=8;return o;
}
function link(s,a,b,from='right',to='left',color=C.teal,dashed=false){return s.shapes.connect(a,b,{kind:'elbow',fromSide:from,toSide:to,line:{fill:color,width:2,style:dashed?'dashed':'solid'},tail:{type:'arrow',width:'sm',length:'sm'}});}
function page(title,subtitle,source){
  const s=p.slides.add();s.background.fill='#FFFFFF';
  text(s,'ADC 课题进度   2026.10.11',52,20,600,24,15,false,C.gray);
  text(s,title,52,60,1176,52,36,true);
  text(s,subtitle,52,120,1176,45,20,false,C.gray);
  text(s,source,52,670,1110,28,14,false,C.gray);
  text(s,String(p.slides.items.length).padStart(2,'0'),1174,670,52,28,15,true,C.teal);
  return s;
}
async function img(s,name,x,y,w,h){const b=await fs.readFile(path.join(workspaceDir,name));s.images.add({blob:b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength),contentType:'image/png',alt:name,fit:'contain',position:{left:x,top:y,width:w,height:h}});}
function table(s,values,x,y,w,h,widths){
  const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:widths});
  t.borders.assign({fill:C.line,width:1,style:'solid'});
  for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){
    const cell=t.getCell(r,c);cell.fill=r===0?C.ink:(r%2?'#F4F8FA':'#FFFFFF');
    cell.text.style={typeface:FONT,fontSize:22,color:r===0?'#FFFFFF':C.ink,bold:r===0};
  }return t;
}

// Editable engineering diagram. All main/aux destinations follow source audit.
{
  const s=page('两级残差通路给数字校准提供观测','先区分主路的残差电压与辅路的 Flash 判决，再讨论数字补偿。','来源：Gu OJSSCS 2026 Fig.13–14、18；本项目主辅路径与数字总线来源审计');
  const input=box(s,'输入 Vin',55,245,118,62,C.gray);
  const f1=box(s,'第一级\nFlash',212,186,142,80);
  const d1=box(s,'第一级\nCDAC + dither',212,339,142,86);
  const main=box(s,'残差放大器 1\n主输出',415,339,154,86);
  const aux=box(s,'辅助判决输出',415,186,154,80,C.orange,22);
  const f2=box(s,'第二级\nFlash',629,186,142,80,C.orange);
  const d2=box(s,'第二级\nCDAC + dither',629,339,142,86);
  const a2=box(s,'残差放大器 2',825,339,156,86);
  const sar=box(s,'8 位 SAR',1030,339,182,86);
  link(s,input,f1,'right','left',C.gray);link(s,input,d1,'right','left',C.gray);
  link(s,f1,d1,'bottom','top');link(s,d1,main);link(s,d1,aux,'right','bottom',C.orange);
  link(s,aux,f2,'right','left',C.orange);link(s,main,d2);link(s,f2,d2,'bottom','top',C.orange);link(s,d2,a2);link(s,a2,sar);
  text(s,'主路驱动第二级 CDAC',403,440,392,32,20,true,C.teal);
  text(s,'辅路驱动第二级 Flash',406,278,392,32,20,true,C.orange);
  box(s,'数字观测：两级判决 q1、q2，SAR 码 b，两路 dither 标记 d1、d2',212,512,1000,66,C.gray,23);
  text(s,'候选约定：q = −4…4，当前 RTL 每级用 4 位有符号字。真实内部码制与四路调度仍待核实。',55,603,1170,42,20,false,C.orange);
  s.speakerNotes.text='讲解约2分钟。主路与辅路连向不同负载。图是公开结构的项目概括，不是晶体管拓扑。候选q九态、位宽和静态匹配主辅属于当前建模假设。Gu et al. DOI 10.1109/OJSSCS.2026.3656850；docs/stages/03_gu_baseline/DIGITAL_BUS_AND_DUAL_PATH_SOURCE_AUDIT_V1.md。论文后端四路TI-SAR，此图合并为一个功能块；当前RTL没有四路引擎。';
}
{
  const s=page('数字校正先处理后级，八个状态在时钟沿更新','在线输入只有数字码、dither 和自身状态。模拟真值留在离线核查侧。','来源：two_stage_fixed_candidate_a.sv、fixed_gated_lms_exact_candidate_a.sv；精确更新理论 v1');
  const b=box(s,'SAR 码 b\n(b − 128) × 8',54,184,220,80,C.gray,22);
  const p2=box(s,'第二级 PWL\nQ3 / Q1.10',312,184,222,80);
  const r=box(s,'前级残差重构\n1024q2 + PWL2 − 128d2',574,184,358,80,C.gray,21);
  const p1=box(s,'第一级 PWL\nQ3 / Q1.10',970,184,255,80);
  link(s,b,p2);link(s,p2,r);link(s,r,p1);
  text(s,'最终码：裁剪并取整 [4096q1 + PWL1 − 512d1 + 16384] / 8',54,284,1170,42,23,true);
  const bank2=box(s,'第二级系数 bank\n4 × 23 位 Q22 状态',312,373,310,85,C.teal,23);
  const bank1=box(s,'第一级系数 bank\n4 × 23 位 Q22 状态',854,373,371,85,C.teal,23);
  link(s,bank2,p2,'top','bottom');link(s,bank1,p1,'top','bottom');
  text(s,'有效门 + 校正观测 Y2 + d2',312,343,402,30,20,false,C.gray);
  text(s,'有效门 + 校正观测 Y1 + d1',854,343,375,30,20,false,C.gray);
  text(s,'门开时：A⁺ = clip(A + Δ)    Δ = sgn(T)⌊(|T| + 62) / 125⌋',54,490,1170,41,25,true);
  text(s,'T1 = −16 d1 j Y1，T2 = −64 d2 j Y2，j ∈ {1, 3, 6, 12}',54,536,1170,37,23);
  text(s,'手算第 7 行：Y2 = 120，d2 = −1，j = 1。T2 = 7680，Δ = 61。\nA20 从 4194304 更新为 4194365，导出的系数仍为 1024。',54,583,1170,65,22,false,C.teal);
  s.speakerNotes.text='讲解约2分钟。d1、d2取±1。图中量均在整数Q3域。PWL系数导出为nearest-even(A/4096)，限制在0..2047。两个bank用本转换旧系数计算输出与门控，在同一时钟沿写入状态，下一转换使用新系数。门限候选采用≥。手算来自vectors/online.txt零基第7行。另一个PWL算例：第二级宽度256，raw_q3=300，C0=1024,C1=1100，其分段偏移256，局部44×1100/1024取偶舍入为47，结果303Q3。完整算法说明见docs/stages/03_gu_baseline/CANDIDATE_A_EXACT_UPDATE_ARITHMETIC_V1.md。';
}
{
  const s=page('Vivado 已生成可检查的数字电路与 FPGA 网表','同一候选 RTL，保留模块层级。目标器件 Artix-7 xc7a100tcsg324-1。','来源：本轮 Vivado 2026.1 综合网表、utilization.rpt、timing_synth.rpt、critical_paths.rpt');
  await img(s,'assets/digital_top.png',52,180,745,282);
  text(s,'Vivado 原生综合网表层级图',52,471,745,32,21,true,C.teal);
  table(s,[['资源','综合使用'],['LUT','2,548'],['触发器','184'],['DSP48E1','4'],['BRAM','0']],832,180,395,285,[240,155]);
  text(s,'184 位 = 两级 × 四段 × 23 位状态',832,485,395,66,21,true);
  text(s,'100 MHz 展示约束未满足',52,537,746,38,28,true,C.orange);
  text(s,'WNS = −50.309 ns。最长报告路径从 SAR 输入经过两级校正进入第一级更新 bank。\n这里只完成综合，布局布线、板级运行和真实 ADC 速率仍未验收。',52,580,1172,66,22,false,C.gray);
  s.speakerNotes.text='讲解约2分钟。网表funcsim Verilog与EDIF、综合DCP、PDF/SVG电路图均随工程提供。资源顶层gu_online_cost_top仅保留valid_out和12位final_code，不导出debug状态影响成本边界。时序合同10ns，输入/输出延迟1ns，输出负载1pF。曾尝试set_input_transition但Vivado不支持并忽略，记录在工程修订中。WHS=-0.079ns，557/561 setup endpoints失败，0未约束内部端点。最长路径数据延迟60.847ns、78逻辑级，route是综合估算。没有据此换算可实现Fmax，也没有与行为3GS/s直接比较。';
}
{
  const s=page('时钟波形核对了旧系数读出和新状态写回','下面来自本轮 XSim VCD。输出在时钟沿之前评分，系数状态在沿后改变。','来源：online_repaired.vcd 与独立数字参考 vectors/online.txt；全部原 RTL 源码 SHA-256 未变');
  await img(s,'assets/rtl_state_trace.png',42,169,1190,385);
  text(s,'第 7 行：沿前 final_code = 3535，沿后 A20 增加 61',54,564,1170,32,24,true,C.teal);
  text(s,'8,263 组序列：全部八个状态逐转换匹配独立参考。\nRTL 与综合网表各通过 8,391 组输出检查、等量空闲周期及 128 行复位重放。',54,606,1170,55,22);
  s.speakerNotes.text='讲解约2分钟。图取零基第7至14行；时钟激励非周期现场频率合同，ns尺度不表示可达频率。完整状态核对还包含门控、学习观测、非法字和停更；综合网表仅核对成本顶层可观测输出，不能称形式等价证明。算术173872增量、869360饱和探针、173872停更探针；专门bank等值/邻点22例。负控制将第0行预期输出翻转一位，必须被testbench拒绝。初期失败来自历史bench长路径截断和glbl 100ns GSR，修复只作用于集成bench与路径，不改核心RTL。';
}
{
  const s=page('已有行为数据表明校准改善了该静态模型的频谱','匹配主辅、人工三次传输、浮点 full120。训练 1,000,080 次，测试 97.75390625 MHz。','来源：simulink_adc/reduced_summary.json、performance_reduced_protocol.json、已有独立 MATLAB FFT 核对');
  await img(s,'assets/behavior_metrics.png',44,179,758,383);
  table(s,[['指标','校准前','终点'],['SNDR / dB','45.2334','61.4768'],['SFDR / dBc','53.0304','78.9052']],825,203,402,213,[168,117,117]);
  text(s,'60 万次 SNDR 为 62.0431 dB，\n终点出现回落。第三、第四段\n均缺少对应学习门支持。',837,448,378,108,22,false,C.orange);
  text(s,'这组性能采用浮点窗口累计。当前 FPGA 候选采用定点逐转换更新，\n硬件闭环频谱仍需对齐数值和调度合同后验证。',54,594,1170,61,23,true,C.gray);
  s.speakerNotes.text='讲解约2分钟。这页复用已验收记录，未重新训练。行为模型stage1 z传输0.975z−0.0825z³，stage2为0.98z−0.06z³；无噪声/动态、主辅匹配，test amplitude0.82，nominal fs3GHz，30720点相干FFT。步长为上一strong组1/4，同时改变非线性与步长，不能单因素归因。图中保留所有7检查点与终点回落。数字硬件结果和浮点行为性能是两类独立证据，未建立这次RTL的ADC闭环性能。';
}
{
  const s=page('当前可复现的进度，以及需要老师判断的电路问题','汇报现场可打开 Simulink 信号链、Vivado 电路图，并重跑数字短测试。','随附：6 页材料、.xpr、结构网表、波形、工具报告、源哈希和复现说明');
  table(s,[['检查对象','目前证据','尚待验证'],['ADC 结构','主辅信号流与可编辑模型','真实负载、建立过程、噪声'],['数字校准','定点 RTL、时钟状态、FPGA 网表','100 MHz 时序与四路调度'],['性能','冻结浮点行为曲线和独立 FFT','定点硬件闭环与硅后数据']],54,187,1170,294,[235,435,500]);
  text(s,'首先讨论：辅路是否准确表征主路残差？',54,518,1170,39,28,true,C.teal);
  text(s,'若能取得实验室现有残差放大器拓扑与 PDK，下一步可检查真实负载下的传输和建立。\n数字路径的流水化或更新调度需要另行确定，不能直接改动本轮候选。',54,567,1170,72,23);
  s.speakerNotes.text='讲解约2分钟。新增软件安装为0：现有Vivado/XSim、MATLAB/Simulink与已有Python/Node依赖足够交付。完整模拟晶体管电路仍缺拓扑尺寸偏置及PDK，不能由Verilog反推。现场按REPRODUCE.md先开既有模型，再开工程的digital_top schematic，再运行tb_review_cost短测试。详细证据和失败修复见CIRCUIT_REVIEW_VIVADO_RESULTS_2026-10-11.md。研究定点长记录计划保持未执行，新算法/晶体管/板级实测保持未开展。若老师不接受AI文字，直接以源文件、工具报告、手算和现场重放讨论；不伪称来源或测量。';
}

const {finalizePresentation}=await import(pathToFileURL(path.join(SKILL_DIR,'container_tools/artifact_tool_utils.mjs')).href);
const staging=path.join(workspaceDir,'.codex-finalizer');await fs.mkdir(staging,{recursive:true});
const candidatePath=path.join(staging,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidatePath);
const finalPath=path.join(workspaceDir,'output/ADC_Circuit_Review_v2.pptx');
const result=await finalizePresentation({workspaceDir,candidatePath,finalPath,pythonExecutable:RUNTIME_PYTHON,integrityValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','3','--require-native-table-slide','5','--require-native-table-slide','6'],explicitTotalSlideCount:6,requiredNativeTableOwnerSlides:[3,5,6],requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(staging,'deck_v2.validation.json')});
for(const [i,s] of p.slides.items.entries()){
  const png=await p.export({slide:s,format:'png',scale:1});
  await fs.writeFile(path.join(workspaceDir,`renders/slide_${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
}
console.log(JSON.stringify({finalPath,validated:result.ok??true,slides:6}));
