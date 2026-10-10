"""Candidate-A digital adapter for an ordered eight-comparator flash output.

The paper draws eight raw comparator lines but does not publish their bit
ordering, polarity, endpoint encoding, or the word used by its calibration
engine.  This adapter defines those choices only for the research candidate.
"""

from __future__ import annotations


def decode_candidate_flash_thermometer(raw: int) -> int:
    """Map D[7:0] to q=-4..4, with D[0] at the lowest threshold.

    A set bit means the input is at or above that threshold.  Legal words
    therefore have a contiguous run of ones starting at bit zero.  Invalid
    patterns are rejected rather than silently converted into a valid state.
    """

    if type(raw) is not int or not 0 <= raw <= 0xFF:
        raise ValueError("raw flash word must be an eight-bit integer")
    if raw & (raw + 1):
        raise ValueError("raw flash word is not a candidate thermometer code")
    return raw.bit_count() - 4
