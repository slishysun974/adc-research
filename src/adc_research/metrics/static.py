"""Static ADC metrics from a uniform-input code-density record."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable


@dataclass(frozen=True)
class CodeDensityMetrics:
    minimum_code: int
    maximum_code: int
    sample_count: int
    ideal_count_per_code: float
    histogram: tuple[int, ...]
    dnl_lsb: tuple[float, ...]
    transition_inl_lsb: tuple[float, ...]
    missing_codes: tuple[int, ...]
    minimum_dnl_lsb: float
    maximum_dnl_lsb: float
    minimum_inl_lsb: float
    maximum_inl_lsb: float


def code_density_metrics(
    codes: Iterable[int],
    *,
    minimum_code: int,
    maximum_code: int,
) -> CodeDensityMetrics:
    """Compute histogram DNL and endpoint-referenced cumulative DNL.

    The input stimulus is assumed to be uniformly distributed over the full
    converter range.  DNL is the observed code-bin width divided by the mean
    code-bin width minus one. The cumulative DNL has one more entry than the
    code histogram. It is physical transition INL only for a monotone static
    transfer; this function sees codes but cannot infer that property from a
    histogram alone. ``transition_inl_lsb`` is retained as the protocol field.
    """

    if maximum_code < minimum_code:
        raise ValueError("maximum_code must not be smaller than minimum_code")
    level_count = maximum_code - minimum_code + 1
    histogram = [0] * level_count
    sample_count = 0
    for code in codes:
        if not isinstance(code, int):
            raise TypeError("ADC codes must be integers")
        if code < minimum_code or code > maximum_code:
            raise ValueError("ADC code lies outside the configured range")
        histogram[code - minimum_code] += 1
        sample_count += 1
    if sample_count == 0:
        raise ValueError("code-density record must not be empty")

    ideal_count = sample_count / level_count
    if not isfinite(ideal_count) or ideal_count <= 0:
        raise ValueError("invalid ideal code count")
    dnl = tuple(count / ideal_count - 1.0 for count in histogram)
    transition_inl = [0.0]
    cumulative = 0.0
    for value in dnl:
        cumulative += value
        transition_inl.append(cumulative)
    missing = tuple(
        minimum_code + index
        for index, count in enumerate(histogram)
        if count == 0
    )
    return CodeDensityMetrics(
        minimum_code=minimum_code,
        maximum_code=maximum_code,
        sample_count=sample_count,
        ideal_count_per_code=ideal_count,
        histogram=tuple(histogram),
        dnl_lsb=dnl,
        transition_inl_lsb=tuple(transition_inl),
        missing_codes=missing,
        minimum_dnl_lsb=min(dnl),
        maximum_dnl_lsb=max(dnl),
        minimum_inl_lsb=min(transition_inl),
        maximum_inl_lsb=max(transition_inl),
    )
