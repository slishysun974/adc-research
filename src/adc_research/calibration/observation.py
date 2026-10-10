"""Only digital signals allowed to enter the online calibration update."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable


@dataclass(frozen=True)
class DigitalCalibrationSample:
    stage1_symbol: int
    stage2_symbol: int
    backend_centered_code: int
    stage1_dither_symbol: Hashable | None
    stage2_dither_symbol: Hashable | None
