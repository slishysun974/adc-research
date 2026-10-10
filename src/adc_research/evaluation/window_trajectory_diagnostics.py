"""Offline attribution of actual fixed-window updates; no learner changes."""

from fractions import Fraction as F

from adc_research.calibration.fixed_four_lane_window import FixedFourLaneWindowResult
from adc_research.calibration.observation import DigitalCalibrationSample


def digital_front_window(samples, result, config):
    """Prepare gate/support evidence using digital observations only."""
    samples = tuple(samples)
    if (not isinstance(result, FixedFourLaneWindowResult)
            or len(samples) != len(result.calibrations)
            or any(not isinstance(s, DigitalCalibrationSample) for s in samples)):
        raise ValueError("aligned digital samples and an actual window result required")
    selected = set(result.selected_conversion_ids)
    width = config.cascade.stage1_pwl.slice_width_scaled
    rows = []
    for offset, (sample, calibration, local) in enumerate(zip(
            samples, result.calibrations, result.stage1_learning_outputs_scaled, strict=True)):
        rows.append({
            "selected": result.first_conversion_id+offset in selected,
            "dither": calibration.stage1_dither_scaled,
            "local": local,
            "coarse": config.cascade.stage1_symbol_weight_scaled*sample.stage1_symbol,
            "raw": calibration.stage1_raw_scaled,
            "gates": tuple(i == 0 or abs(local) >= threshold
                           for i, threshold in enumerate(result.stage1_update.thresholds_scaled)),
            "support": tuple(abs(calibration.stage1_raw_scaled) > i*width for i in range(4)),
        })
    sums = tuple(sum(r["dither"]*r["local"] for r in rows if r["selected"] and r["gates"][i])
                 for i in range(4))
    if sums != result.stage1_update.selected_product_sums:
        raise AssertionError("independent gate reconstruction disagrees with the core")
    return tuple(rows)


def offline_front_attribution(digital_rows, ideal_codes, result, config):
    """D*Y*G = D*T*G + D*(Y-T)*G on the actual Q3 gates.

    T = 8*ideal_code - offset - stage1_coarse. Targets arrive only in this
    offline call. Integer-code targets include the declared ideal quantizer;
    its sub-code error is not attributed to analog distortion alone.
    """
    rows, targets = tuple(digital_rows), tuple(ideal_codes)
    if (not rows or len(rows) != len(targets)
            or any(isinstance(t, bool) or not isinstance(t, int) or not 0 <= t <= 4095
                   for t in targets)):
        raise ValueError("aligned nonempty ideal integer codes required")
    data_scale = 1 << config.cascade.data_fractional_bits
    offset = config.cascade.output_offset_scaled
    enriched = tuple((row, data_scale*target-offset-row["coarse"])
                     for row, target in zip(rows, targets, strict=True))
    evidence = []
    update = result.stage1_update
    for i, step in enumerate(config.stage1_lms.step_sizes):
        chosen = tuple((row, target) for row, target in enriched
                       if row["selected"] and row["gates"][i])
        signal = sum(row["dither"]*target for row, target in chosen)
        error = sum(row["dither"]*(row["local"]-target) for row, target in chosen)
        full = sum(row["dither"]*row["local"] for row, target in enriched if row["gates"][i])
        learning = signal+error
        if learning != update.selected_product_sums[i]:
            raise AssertionError("target/error identity failed")
        factor = -step*update.product_multiplier*(1 << config.stage1_lms.accumulator_fractional_bits)/data_scale**2
        signal_delta, error_delta = factor*signal, factor*error
        rounding = F(update.requested_deltas[i])-signal_delta-error_delta
        clipping = update.applied_deltas[i]-update.requested_deltas[i]
        if abs(rounding) > F(1, 2):
            raise AssertionError("unexpected nearest-even rounding residual")
        zero = tuple(row for row, target in chosen if not row["support"][i])
        evidence.append({
            "gate_index": i, "selected_gate_count": len(chosen),
            "all_gate_count": sum(row["gates"][i] for row in rows),
            "zero_basis_selected_count": len(zero),
            "zero_basis_product_sum": sum(row["dither"]*row["local"] for row in zero),
            "learning_product_sum": learning, "target_product_sum": signal,
            "error_product_sum": error, "all_product_sum_at_same_state": full,
            "scaled_selection_difference": update.product_multiplier*learning-full,
            "target_delta_q22": signal_delta, "error_delta_q22": error_delta,
            "rounding_delta_q22": rounding, "clipping_delta_q22": clipping,
            "applied_delta_q22": update.applied_deltas[i],
            "target_opposes_error": signal*error < 0,
            "learning_opposes_error": learning*error < 0,
            "selection_opposes_full": learning*full < 0,
        })
    return tuple(evidence)


def code_error_stats(codes, ideal_codes):
    codes, targets = tuple(codes), tuple(ideal_codes)
    if not codes or len(codes) != len(targets):
        raise ValueError("aligned nonempty code records required")
    errors = tuple(a-b for a, b in zip(codes, targets, strict=True))
    return {"count": len(errors), "mae_codes": F(sum(map(abs, errors)), len(errors)),
            "mse_codes_squared": F(sum(e*e for e in errors), len(errors)),
            "maximum_error_codes": max(map(abs, errors)), "bias_codes": F(sum(errors), len(errors))}
