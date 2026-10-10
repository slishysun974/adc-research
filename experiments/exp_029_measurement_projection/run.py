"""Show what a single selected, decimated channel cannot reveal.

This is an illustrative measurement projection, not Gu's unpublished
decimator implementation. Coefficients are treated as frozen.
"""

from __future__ import annotations

import json

import numpy as np

from adc_research.metrics.spectral import analyze_coherent_tone


def run() -> dict:
    sample_count = 61_440
    full_rate_hz = 3_000_000_000.0
    tone_bin = 20_577
    index = np.arange(sample_count)

    reference = np.rint(
        2048
        + 1000 * np.sin(2 * np.pi * tone_bin * index / sample_count)
        + 0.1 * np.sin(2 * np.pi * 3 * tone_bin * index / sample_count)
    ).astype(np.int64)
    changed = reference.copy()
    changed[index % 4 == 1] += 8
    if reference.min() < 0 or changed.max() > 4095:
        raise AssertionError("constructed records must remain 12-bit codes")

    # One explicit candidate: keep every 30th result of serial phase 0.
    # The paper does not specify the decimator transfer function or phase.
    selected_index = np.arange(0, sample_count, 4 * 30)
    selected_reference = reference[selected_index]
    selected_changed = changed[selected_index]
    if not np.array_equal(selected_reference, selected_changed):
        raise AssertionError("the selected-channel records must be identical")

    def score(values: np.ndarray, rate_hz: float, bin_index: int) -> dict:
        metric = analyze_coherent_tone(
            values, sample_rate_hz=rate_hz, fundamental_bin=bin_index
        ).metrics
        return {
            "sample_count": metric.sample_count,
            "sndr_db": metric.sndr_db,
            "sfdr_dbc": metric.sfdr_dbc,
            "worst_spur_bin": metric.worst_spur_bin,
        }

    selected_bin = tone_bin % selected_index.size
    return {
        "claim": "single_selected_channel_does_not_identify_full_rate_spectrum",
        "scope": "frozen_coefficients_and_illustrative_keep_every_30th_decimation",
        "full_rate_hz": full_rate_hz,
        "input_frequency_hz": full_rate_hz * tone_bin / sample_count,
        "selected_rate_hz": full_rate_hz / 120,
        "selected_channel": 0,
        "changed_channel": 1,
        "changed_channel_offset_codes": 8,
        "selected_records_identical": True,
        "reference_full": score(reference, full_rate_hz, tone_bin),
        "changed_full": score(changed, full_rate_hz, tone_bin),
        "reference_selected": score(
            selected_reference, full_rate_hz / 120, selected_bin
        ),
        "changed_selected": score(
            selected_changed, full_rate_hz / 120, selected_bin
        ),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
