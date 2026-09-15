# EXP-006：两级已知 PWL truth 与 oracle 校正级联

## 研究问题

在不引入 LMS 估计误差、定点舍入、CDAC mismatch 或阈值 offset 的条件下，
验证两级 PWL 校正结构能否表达并逆转两级独立的静态放大器非线性；同时确认
第二级 dither 必须在进入第一级 PWL 前扣除，第一级 dither 必须在第一级
PWL 后扣除。

## 模型

每级 truth 用一组非负半轴配对边界定义：

```text
ideal amplifier output edge x_i  <->  distorted output edge y_i
```

区间内线性插值，负半轴按奇对称扩展。truth 属于平台层；oracle 系数由
`x_i/y_i` 的区间宽度比推导，不能作为第二份独立手填参数。两级数字顺序为：

```text
SAR centered code
  -> PWL2
  -> +128*q2
  -> -dither2(16 code)
  -> PWL1
  -> +512*q1
  -> -dither1(64 code)
```

第一、第二级 raw-code PWL 半轴满量程分别为 512 和 128，对应 `b0=128/32`。

## 验证

1. 在连续码坐标上逐点检查 truth 与 oracle 复合为恒等映射；
2. 穷举 4096 个 12-bit 输入码中心和 4 组 dither 符号；
3. 比较未校正、正确级联以及“第二级 dither 延迟到第一级 PWL 后才扣除”的
   错序反例；
4. 检查物理过载、校正后单调性、端点饱和和各 PWL slice 的实际覆盖。

量化后的正确级联不要求浮点输出逐码严格等于理想整数码。PWL truth 的连续
反函数可以精确恢复，但最末级 8-bit SAR 已经发生的量化不可逆；因此验收使用
误差界与单调性，而不是把量化误差伪装成 oracle 失配。最终 3-bit fractional
定点舍入仍不在本实验范围内。

## 运行

```powershell
$env:PYTHONPATH = "src"
python experiments/exp_006_two_stage_pwl_truth/run.py --run-id <unique-run-id>
```

