"""Designed-intervention attribution for known simulator factors."""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations
from math import factorial
from typing import Callable, Iterable

from .metrics import SpectrumMetrics, spectrum_metrics
from .pipeline import MismatchRealization, PipelineConfig, simulate


@dataclass(frozen=True)
class InterventionFactor:
    name: str
    active_value: float


def powerset(items: Iterable[str]) -> list[frozenset[str]]:
    values = tuple(items)
    return [
        frozenset(subset)
        for size in range(len(values) + 1)
        for subset in combinations(values, size)
    ]


def run_factorial_interventions(
    base_config: PipelineConfig,
    factors: list[InterventionFactor],
    n_samples: int,
    tone_bin: int,
    realization: MismatchRealization,
) -> dict[frozenset[str], dict[str, float | int]]:
    """Run all factor subsets with a shared mismatch/noise realization."""

    allowed = set(base_config.__dataclass_fields__)
    names = [factor.name for factor in factors]
    if len(names) != len(set(names)):
        raise ValueError("Factor names must be unique.")
    if not set(names).issubset(allowed):
        raise ValueError("Every factor must name a PipelineConfig field.")

    values_by_name = {factor.name: factor.active_value for factor in factors}
    results: dict[frozenset[str], dict[str, float | int]] = {}
    for active in powerset(names):
        changes = {name: values_by_name[name] if name in active else 0.0 for name in names}
        config = replace(base_config, **changes)
        simulation = simulate(config, n_samples, tone_bin, realization)
        metrics: SpectrumMetrics = spectrum_metrics(simulation.output_signal, tone_bin)
        results[active] = {
            **metrics.to_dict(),
            "threshold_crossing_rate": simulation.threshold_crossing_rate,
            "overload_rate": simulation.overload_rate,
        }
    return results


def exact_shapley(
    subset_values: dict[frozenset[str], float],
    factor_names: list[str],
) -> dict[str, float]:
    """Compute exact Shapley values for a complete factorial response surface."""

    n_factors = len(factor_names)
    expected = set(powerset(factor_names))
    if set(subset_values) != expected:
        raise ValueError("subset_values must contain every factor subset exactly once.")

    attributions: dict[str, float] = {}
    for factor in factor_names:
        others = [name for name in factor_names if name != factor]
        contribution = 0.0
        for subset in powerset(others):
            size = len(subset)
            weight = factorial(size) * factorial(n_factors - size - 1) / factorial(n_factors)
            contribution += weight * (
                subset_values[subset | {factor}] - subset_values[subset]
            )
        attributions[factor] = contribution
    return attributions


def metric_loss_values(
    factorial_results: dict[frozenset[str], dict[str, float | int]],
    metric: str,
) -> dict[frozenset[str], float]:
    """Convert a higher-is-better metric into loss relative to ideal."""

    ideal = float(factorial_results[frozenset()][metric])
    return {
        subset: ideal - float(result[metric])
        for subset, result in factorial_results.items()
    }

