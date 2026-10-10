"""Extract the hardware-visible digital fields from a full simulator trace."""

from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.platform.pipeline import PipelineResult


def digital_sample(raw: PipelineResult) -> DigitalCalibrationSample:
    return DigitalCalibrationSample(
        stage1_symbol=raw.stage1.quantizer.symbol,
        stage2_symbol=raw.stage2.quantizer.symbol,
        backend_centered_code=raw.backend.centered_code,
        stage1_dither_symbol=raw.stage1.cdac.dither_symbol,
        stage2_dither_symbol=raw.stage2.cdac.dither_symbol,
    )
