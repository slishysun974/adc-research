"""A compact, event-observable two-stage pipeline ADC behavioral model.

The model is intentionally small enough for analytical work.  It is not a
transistor-level simulator: mismatch magnitudes are normalized to the stage-1
LSB and are controlled independently so that interventions are reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]


@dataclass(frozen=True)
class PipelineConfig:
    stage1_bits: int = 3
    stage2_bits: int = 9
    amplitude: float = 0.90
    gain_error: float = 0.0
    cdac_mismatch_lsb: float = 0.0
    comparator_offset_lsb: float = 0.0
    residue_cubic: float = 0.0
    noise_std: float = 0.0
    seed: int = 20260914

    def validate(self) -> None:
        if self.stage1_bits < 1 or self.stage2_bits < 1:
            raise ValueError("Both stages must have at least one bit.")
        if not 0.0 < self.amplitude <= 1.0:
            raise ValueError("Amplitude must lie in (0, 1].")
        if self.noise_std < 0.0:
            raise ValueError("noise_std must be non-negative.")


@dataclass(frozen=True)
class MismatchRealization:
    """Unit-normalized random directions shared by all interventions."""

    threshold_direction: FloatArray
    dac_code_direction: FloatArray
    noise_direction: FloatArray

    @classmethod
    def sample(
        cls,
        config: PipelineConfig,
        n_samples: int,
    ) -> "MismatchRealization":
        rng = np.random.default_rng(config.seed)
        levels1 = 2**config.stage1_bits
        threshold_direction = rng.normal(size=levels1 - 1)
        dac_code_direction = _remove_affine_component(rng.normal(size=levels1))
        noise_direction = rng.normal(size=n_samples)
        return cls(threshold_direction, dac_code_direction, noise_direction)

    def validate(self, config: PipelineConfig, n_samples: int) -> None:
        levels1 = 2**config.stage1_bits
        if self.threshold_direction.shape != (levels1 - 1,):
            raise ValueError("Threshold realization has the wrong shape.")
        if self.dac_code_direction.shape != (levels1,):
            raise ValueError("DAC realization has the wrong shape.")
        if self.noise_direction.shape != (n_samples,):
            raise ValueError("Noise realization has the wrong shape.")


@dataclass(frozen=True)
class SimulationResult:
    input_signal: FloatArray
    output_signal: FloatArray
    stage1_code: IntArray
    ideal_stage1_code: IntArray
    nominal_stage1_level: FloatArray
    actual_dac_level: FloatArray
    residue: FloatArray
    stage2_level: FloatArray
    threshold_crossing_mask: NDArray[np.bool_]
    overload_mask: NDArray[np.bool_]

    @property
    def threshold_crossing_rate(self) -> float:
        return float(np.mean(self.threshold_crossing_mask))

    @property
    def overload_rate(self) -> float:
        return float(np.mean(self.overload_mask))


def _remove_affine_component(values: FloatArray) -> FloatArray:
    """Keep only code-dependent DAC error, removing offset and gain terms."""

    x = np.linspace(-1.0, 1.0, values.size)
    design = np.column_stack((np.ones(values.size), x))
    coeff, *_ = np.linalg.lstsq(design, values, rcond=None)
    residual = values - design @ coeff
    rms = np.sqrt(np.mean(residual**2))
    return residual if rms == 0.0 else residual / rms


def _midrise_quantize(
    values: FloatArray,
    bits: int,
    thresholds: FloatArray | None = None,
) -> tuple[IntArray, FloatArray]:
    levels = 2**bits
    step = 2.0 / levels
    if thresholds is None:
        thresholds = -1.0 + step * np.arange(1, levels)
    codes = np.searchsorted(thresholds, values, side="right")
    codes = np.clip(codes, 0, levels - 1).astype(np.int64)
    recon = -1.0 + step * (codes.astype(float) + 0.5)
    return codes, recon


def _perturbed_thresholds(config: PipelineConfig, realization: MismatchRealization) -> FloatArray:
    levels = 2**config.stage1_bits
    step = 2.0 / levels
    nominal = -1.0 + step * np.arange(1, levels)
    perturbed = nominal + config.comparator_offset_lsb * step * realization.threshold_direction

    # Prevent a behavioral parameter sweep from creating an invalid comparator
    # ordering.  The small spacing is far below the intended experiment range.
    lower = -1.0 + 1e-9
    for index in range(perturbed.size):
        perturbed[index] = max(perturbed[index], lower)
        lower = perturbed[index] + 1e-9
    upper = 1.0 - 1e-9
    for index in range(perturbed.size - 1, -1, -1):
        perturbed[index] = min(perturbed[index], upper)
        upper = perturbed[index] - 1e-9
    return perturbed


def simulate(
    config: PipelineConfig,
    n_samples: int = 32768,
    tone_bin: int = 127,
    realization: MismatchRealization | None = None,
) -> SimulationResult:
    """Simulate a coherent sine through a two-stage pipeline ADC.

    The stage-1 nominal residue gain is ``2**stage1_bits``.  Stage-2 clipping
    therefore exposes residue folding/overload created by gain, DAC, threshold,
    or nonlinear errors.  Digital reconstruction always uses nominal weights.
    """

    config.validate()
    if n_samples < 16:
        raise ValueError("n_samples must be at least 16.")
    if tone_bin <= 0 or tone_bin >= n_samples // 2:
        raise ValueError("tone_bin must be inside the positive Nyquist band.")
    if np.gcd(tone_bin, n_samples) != 1:
        raise ValueError("tone_bin and n_samples must be coprime for coherent coverage.")

    if realization is None:
        realization = MismatchRealization.sample(config, n_samples)
    realization.validate(config, n_samples)

    sample_index = np.arange(n_samples)
    input_signal = config.amplitude * np.sin(2.0 * np.pi * tone_bin * sample_index / n_samples)

    levels1 = 2**config.stage1_bits
    stage1_lsb = 2.0 / levels1
    nominal_gain = float(levels1)

    ideal_code, _ = _midrise_quantize(input_signal, config.stage1_bits)
    thresholds = _perturbed_thresholds(config, realization)
    stage1_code, nominal_stage1_level = _midrise_quantize(
        input_signal,
        config.stage1_bits,
        thresholds,
    )

    dac_error = (
        config.cdac_mismatch_lsb
        * stage1_lsb
        * realization.dac_code_direction[stage1_code]
    )
    actual_dac_level = nominal_stage1_level + dac_error

    ideal_scaled_residue = nominal_gain * (input_signal - actual_dac_level)
    residue = (
        (1.0 + config.gain_error) * ideal_scaled_residue
        + config.residue_cubic * ideal_scaled_residue**3
        + config.noise_std * realization.noise_direction
    )
    overload_mask = np.abs(residue) > 1.0

    _, stage2_level = _midrise_quantize(residue, config.stage2_bits)
    output_signal = nominal_stage1_level + stage2_level / nominal_gain

    return SimulationResult(
        input_signal=input_signal,
        output_signal=output_signal,
        stage1_code=stage1_code,
        ideal_stage1_code=ideal_code,
        nominal_stage1_level=nominal_stage1_level,
        actual_dac_level=actual_dac_level,
        residue=residue,
        stage2_level=stage2_level,
        threshold_crossing_mask=stage1_code != ideal_code,
        overload_mask=overload_mask,
    )
