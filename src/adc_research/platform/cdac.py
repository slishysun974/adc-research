"""Logical, table-driven CDAC reconstruction for the reference platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable, Mapping


@dataclass(frozen=True)
class CdacConfig:
    nominal_levels: Mapping[Hashable, float]
    dither_levels: Mapping[Hashable, float] = field(default_factory=dict)


@dataclass(frozen=True)
class CdacMismatch:
    code_level_errors: Mapping[Hashable, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DacResult:
    symbol: Hashable
    nominal_value: float
    mismatch_contribution: float
    actual_dac_value: float
    dither_symbol: Hashable | None
    dither_contribution: float


def reconstruct(
    symbol: Hashable,
    dither_symbol: Hashable | None,
    config: CdacConfig,
    mismatch: CdacMismatch | None = None,
) -> DacResult:
    """Return nominal, mismatch, and dither terms without hiding their signs."""

    if symbol not in config.nominal_levels:
        raise KeyError(f"CDAC symbol has no configured level: {symbol!r}")
    nominal = config.nominal_levels[symbol]
    mismatch_value = (
        mismatch.code_level_errors.get(symbol, 0.0) if mismatch else 0.0
    )

    if dither_symbol is None:
        dither_value = 0.0
    else:
        if dither_symbol not in config.dither_levels:
            raise KeyError(
                f"dither symbol has no configured level: {dither_symbol!r}"
            )
        dither_value = config.dither_levels[dither_symbol]

    return DacResult(
        symbol=symbol,
        nominal_value=nominal,
        mismatch_contribution=mismatch_value,
        actual_dac_value=nominal + mismatch_value,
        dither_symbol=dither_symbol,
        dither_contribution=dither_value,
    )
