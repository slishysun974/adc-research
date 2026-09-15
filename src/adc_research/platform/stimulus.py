"""Deterministic input records for static and coherent-tone platform tests."""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd, isfinite, pi

import numpy as np


@dataclass(frozen=True)
class UniformRampConfig:
    code_count: int
    samples_per_code: int
    input_range: tuple[float, float] = (-1.0, 1.0)

    def __post_init__(self) -> None:
        low, high = self.input_range
        if self.code_count <= 0:
            raise ValueError("code_count must be positive")
        if self.samples_per_code <= 0:
            raise ValueError("samples_per_code must be positive")
        if not all(isfinite(value) for value in self.input_range) or high <= low:
            raise ValueError("input range must be finite and increasing")

    @property
    def sample_count(self) -> int:
        return self.code_count * self.samples_per_code


def uniform_ramp(config: UniformRampConfig) -> np.ndarray:
    """Return midpoint samples uniformly spaced over the input range."""

    low, high = config.input_range
    indices = np.arange(config.sample_count, dtype=float)
    return low + (indices + 0.5) * (high - low) / config.sample_count


@dataclass(frozen=True)
class CoherentSineConfig:
    sample_rate_hz: float
    sample_count: int
    tone_bin: int
    amplitude_peak: float
    offset: float = 0.0
    phase_radians: float = 0.0
    input_range: tuple[float, float] = (-1.0, 1.0)
    require_full_phase_set: bool = True

    def __post_init__(self) -> None:
        if not isfinite(self.sample_rate_hz) or self.sample_rate_hz <= 0:
            raise ValueError("sample rate must be finite and positive")
        if self.sample_count < 4 or self.sample_count % 2:
            raise ValueError("sample count must be an even integer of at least four")
        if self.tone_bin <= 0 or self.tone_bin >= self.sample_count // 2:
            raise ValueError("tone bin must lie strictly inside the first Nyquist zone")
        if self.require_full_phase_set and gcd(self.tone_bin, self.sample_count) != 1:
            raise ValueError("tone bin and sample count must be coprime")
        if not isfinite(self.amplitude_peak) or self.amplitude_peak <= 0:
            raise ValueError("amplitude must be finite and positive")
        if not isfinite(self.offset) or not isfinite(self.phase_radians):
            raise ValueError("offset and phase must be finite")
        low, high = self.input_range
        if not all(isfinite(value) for value in self.input_range) or high <= low:
            raise ValueError("input range must be finite and increasing")
        if self.offset - self.amplitude_peak < low:
            raise ValueError("sine record exceeds the lower input limit")
        if self.offset + self.amplitude_peak >= high:
            raise ValueError("sine record reaches or exceeds the upper input limit")

    @property
    def tone_frequency_hz(self) -> float:
        return self.sample_rate_hz * self.tone_bin / self.sample_count


def coherent_sine(config: CoherentSineConfig) -> np.ndarray:
    """Return an integer-cycle sine record with no windowing requirement."""

    indices = np.arange(config.sample_count, dtype=float)
    phase = (
        2.0 * pi * config.tone_bin * indices / config.sample_count
        + config.phase_radians
    )
    return config.offset + config.amplitude_peak * np.sin(phase)
