"""Compatibility imports for historical experiments.

New code must use ``calibration.two_stage`` for digital correction and
``evaluation.oracle`` for offline truth-based scoring.  This file preserves
the old import path so previously recorded experiments remain reproducible.
"""

from adc_research.calibration.two_stage import (  # noqa: F401
    TwoStagePwlCalibrationConfig,
    TwoStagePwlCalibrationResult,
)
from adc_research.evaluation.scoring import correct_two_stage  # noqa: F401
from adc_research.evaluation.oracle import (  # noqa: F401
    build_two_stage_oracle,
    oracle_pwl_config,
)
