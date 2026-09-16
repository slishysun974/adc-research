# 配置目录

- `architectures/`：经过审查的 ADC 架构配置；
- `nonidealities/`：可复用的非理想模型和强度配置；
- `experiments/`：供多个实验复用的配置。目前尚无此类配置；单个实验专用的
  `config.yaml` 与该实验的 `run.py` 一起放在 `experiments/exp_NNN_*/`。

阶段一开始前不预填 Gu 架构数值，避免把尚未审查的推断固化成正式参数。
