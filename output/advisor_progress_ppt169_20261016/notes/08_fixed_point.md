本候选前后级各四个斜率，PWL段间偏移由之前各段累计构成。后级先校正，再重构前级局部量并处理dither副本。Q3为数据保留3个二进制小数位，Q1.10为接口保留10小数位，Q22为内部更新累加精度。EXP-013的10小数位累加器控制中有效更新都舍入为零，提高内部精度才能保存小更新。接口暂时不变不表示隐藏状态已经停止。

来源：D:/ADC/docs/reports/RESEARCH_MODULE_03_IMPLEMENTATION_V1.md；D:/ADC/docs/reports/experiments/EXP_013_FIXED_LMS_ACCUMULATOR_V1.md；D:/ADC/docs/reports/GU_ALGORITHM_EVALUATION_V1.md §4。