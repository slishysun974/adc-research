"""Digital-only phase schedules for the declared 30-point lane window.

The existing Gu products, gates, arithmetic and commits are unchanged.
The xorshift schedule is a deterministic research candidate, not chip PRNG
evidence or a source of independent uniform random phases.
"""

from dataclasses import dataclass
from typing import Literal

MASK32 = (1 << 32)-1


def xorshift32(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MASK32:
        raise ValueError("nonzero unsigned 32-bit state required")
    value ^= (value << 13) & MASK32
    value ^= value >> 17
    value ^= (value << 5) & MASK32
    return value & MASK32


@dataclass(frozen=True)
class WindowPhaseSchedule:
    mode: Literal["fixed", "rotate", "xorshift32"]
    state: int = 0

    def __post_init__(self):
        if isinstance(self.state, bool) or not isinstance(self.state, int):
            raise ValueError("integer phase state required")
        if self.mode == "fixed":
            if not 0 <= self.state < 30:
                raise ValueError("fixed phase must be in 0..29")
        elif self.mode == "rotate":
            if not 0 <= self.state < 30:
                raise ValueError("rotation state must be in 0..29")
        elif self.mode == "xorshift32":
            if not 1 <= self.state <= MASK32:
                raise ValueError("nonzero unsigned 32-bit seed required")
        else:
            raise ValueError("unknown phase schedule")

    @property
    def phase(self) -> int:
        return self.state % 30

    def advance(self):
        """Advance once after a complete window, without reading samples."""
        if self.mode == "fixed":
            return self
        if self.mode == "rotate":
            return WindowPhaseSchedule(self.mode, (self.state+1) % 30)
        return WindowPhaseSchedule(self.mode, xorshift32(self.state))
