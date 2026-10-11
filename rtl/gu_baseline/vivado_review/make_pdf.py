"""Create static slide PDF and one-page reproduction guide with existing tools."""
import argparse
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('work',type=Path)
    args=parser.parse_args()
    root=args.work
    output=root/'output'
    output.mkdir(exist_ok=True)
    # The editable PPTX remains primary. PDF is an exact static rendering.
    c=canvas.Canvas(str(output/'ADC_Circuit_Review.pdf'),pagesize=(960,540))
    c.setTitle('ADC circuit review, 2026-10-11')
    for n in range(1,7):
        c.drawImage(str(root/f'renders/slide_{n}.png'),0,0,width=960,height=540)
        c.showPage()
    c.save()
    pdfmetrics.registerFont(TTFont('ReviewCN',r'C:\Windows\Fonts\msyh.ttc',subfontIndex=0))
    c=canvas.Canvas(str(output/'Reproduction_Guide.pdf'),pagesize=A4)
    c.setTitle('ADC circuit review reproduction guide')
    width,height=A4
    y=height-47
    def lines(text,size=11,leading=18,color='#172B4D'):
        nonlocal y
        c.setFillColor(color);c.setFont('ReviewCN',size)
        for line in text.split('\n'):
            c.drawString(43,y,line);y-=leading
    def section(label):
        nonlocal y
        y-=10;lines(label,13,21,'#087F8C')
    lines('ADC 架构与数字校准硬件：复现与现场演示',18,26)
    lines('2026-10-11  |  Vivado 2026.1 / XSim  |  新增软件安装：0',10,17,'#536477')
    section('1  打开材料与工程')
    lines('先看 ADC_Circuit_Review.pdf，修改讲稿用同名 PPTX。\n解压 ADC_Circuit_Review_Package.zip 到短英文路径，例如 C:/ADC_review。\n在 Vivado 打开 hardware/project/gu_review.xpr。工程含源文件和测试向量。\nSimulink 模型位于 behavior/adc_behavioral.slx，使用现有 MATLAB/Simulink。')
    section('2  沿电路与波形检查')
    lines('hardware/schematics/rtl_correction.svg：两级校正的 RTL 运算结构。\nhardware/schematics/accumulator0_local.svg：寄存器 D 输入附近的真实 FPGA 逻辑。\n在 Vivado Tcl Console 输入 source {工程根目录/show_states.tcl}，\n载入已核对的八状态 WDB 与查看配置。纸质备份可用 schematics/ 下的 PDF。')
    section('3  现场短测试')
    lines('在已打开工程的 Tcl Console 输入 source {工程根目录/short_demo.tcl}。\n本机工程根目录以 hardware 为准。用正斜杠，含空格路径放在花括号内。\n通过标记：REVIEW_COST_PASS vectors=8391 idle_cycles=8391 reset_replay=128\n检查日志保存在 hardware/logs/demo_日期时间/，不覆盖历史记录。\n完整新建复算：运行 hardware/rebuild.ps1 -NewRun C:/ADC_review_new。')
    section('4  一个现场手算点')
    lines('独立参考零基第 7 行：Y2=120、d2=-1、j=1。\nT2=-64*d2*j*Y2=7680，Delta=floor((7680+62)/125)=61。\nA20 从 4194304 更新到 4194365，导出 Q1.10 系数仍为 1024。\n本转换用旧系数读出，时钟沿写回，新状态参与下一转换。')
    section('5  成绩与限制')
    lines('Artix-7 xc7a100tcsg324-1：2548 LUT、184 触发器、4 DSP、0 BRAM。\n10 ns 展示时钟、输入/输出延迟各 1 ns，WNS=-50.309 ns，未满足时序。\n仅完成综合和数字功能核对，布局布线、板级与晶体管验证未开展。\nSNDR 45.2334 至 61.4768 dB 来自既有浮点 full120 行为仿真，\n与本次定点逐转换 RTL 的硬件闭环性能分开报告。',10.5,17)
    c.setFillColor('#536477');c.setFont('ReviewCN',9)
    c.drawString(43,35,'完整条件与来源见 REPRODUCE.md、manifest.json、validation.json 和研究报告。')
    if y<53:raise ValueError(f'Guide exceeds one page: bottom={y}')
    c.save()

if __name__=='__main__':main()
