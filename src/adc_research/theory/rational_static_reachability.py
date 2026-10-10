"""Exact rational specialization of the conditional static signal chain.

Require Fraction endpoints at every analog boundary. No float endpoint is
silently converted to a source number. The shared branch algorithm
then uses exact addition, subtraction, comparisons, division, and floor.
This checks arithmetic representation, not the physical envelope premises.
"""
from __future__ import annotations

from fractions import Fraction

from adc_research.theory.static_observation_reachability import (
    ClosedInterval, StaticCandidateArchitecture, StaticObservationEnvelope,
    TransferEnvelope, propagate_static_observations,
)


def require_rational_interval(value: ClosedInterval, label: str) -> ClosedInterval:
    if not isinstance(value, ClosedInterval) or not all(
        isinstance(endpoint, Fraction) for endpoint in (value.lower, value.upper)
    ):
        raise TypeError(f"{label} requires Fraction endpoints; floats are not certified")
    return value


def _validate_architecture(architecture: StaticCandidateArchitecture) -> None:
    if not isinstance(architecture, StaticCandidateArchitecture):
        raise TypeError("architecture must be StaticCandidateArchitecture")
    for name in ("stage1_thresholds", "stage2_thresholds", "stage1_dac_levels",
                 "stage2_dac_levels", "backend_thresholds"):
        for interval in getattr(architecture, name) or ():
            require_rational_interval(interval, name)
    for name in ("front_nominal_range", "backend_range"):
        if not all(isinstance(endpoint, Fraction) for endpoint in getattr(architecture, name)):
            raise TypeError(f"{name} requires Fraction endpoints")
    if type(architecture.backend_bits) is not int:
        raise TypeError("backend_bits must be an integer")
    if any(type(symbol) is not int for symbol in
           (*architecture.stage1_symbols, *architecture.stage2_symbols)):
        raise TypeError("digital symbols must be integers")


def propagate_rational_static_observations(
    input_voltage: ClosedInterval,
    dither1_preamp: ClosedInterval,
    dither2_preamp: ClosedInterval,
    architecture: StaticCandidateArchitecture,
    stage1_main: TransferEnvelope,
    stage1_auxiliary: TransferEnvelope,
    stage2_main: TransferEnvelope,
) -> StaticObservationEnvelope:
    """Enclose observations without binary floating-point voltage operations.

    Comparator equality reports high. Region closures may add unattainable
    endpoints and independent main/aux ranges may add impossible branches;
    both are conservative. Every callback must preserve Fraction endpoints
    and independently satisfy its coverage contract over the entire query.
    Endpoint types alone cannot certify a custom callback's internal math;
    it must be reviewed separately, as for the exact scan envelope adapter.
    """
    _validate_architecture(architecture)
    for interval, name in ((input_voltage, "input"), (dither1_preamp, "dither1"),
                           (dither2_preamp, "dither2")):
        require_rational_interval(interval, name)

    def checked(callback, name):
        def envelope(query):
            require_rational_interval(query, f"{name} query")
            return require_rational_interval(callback(query), f"{name} output")
        return envelope

    return propagate_static_observations(
        input_voltage, dither1_preamp, dither2_preamp, architecture,
        checked(stage1_main, "stage1_main"),
        checked(stage1_auxiliary, "stage1_auxiliary"),
        checked(stage2_main, "stage2_main"),
    )
