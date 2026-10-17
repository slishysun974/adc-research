# 配置目录

- `architectures/`：经过审查的 ADC 架构配置；
- `nonidealities/`：可复用的非理想模型和强度配置；
- `experiments/`：供多个实验复用的配置。目前尚无此类配置；单个实验专用的
  `config.yaml` 与该实验的 `run.py` 一起放在 `experiments/exp_NNN_*/`。

架构和非理想参数沿用各自的来源与审查记录；论文公开值、推导值和研究假设分别注明，不把尚未核实的芯片细节写成默认事实。
