"""Check analytic mechanism examples; no Cadence data or ADC performance claim."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import math


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts/research/physical_evidence_20261009"


def reset_phase():
    rho_amp, rho_track, bias = F(1, 1000), F(1, 10), F(1, 2000)
    state = F(1, 3)
    initial = state
    kappa = rho_amp*rho_track
    forcing = []
    for n in range(64):
        u = F((37*n) % 101-50, 500)
        target = 4*u+F(2, 5)*u**3
        start = bias+rho_track*(state-bias)
        actual = target+rho_amp*(start-target)
        term = (1-rho_amp)*target+rho_amp*(1-rho_track)*bias
        forcing.append(term)
        recurrence = term+kappa*state
        closed = kappa**(n+1)*initial+sum(
            (kappa**(n-j)*value for j, value in enumerate(forcing)), F(0))
        assert actual == recurrence == closed
        state = actual
    direct_hold_difference = 2*rho_amp
    two_phase_difference = 2*kappa
    assert two_phase_difference == rho_track*direct_hold_difference
    return {
        "scope": "exact rational identities under an explicitly assumed two-phase first-order model",
        "records_checked": 64, "rho_amplification": str(rho_amp),
        "rho_tracking": str(rho_track), "memory_coefficient": str(kappa),
        "example_previous_state_difference": "2",
        "direct_hold_output_difference": str(direct_hold_difference),
        "two_phase_output_difference": str(two_phase_difference),
        "paper_anchor_diagnostic_only": {
            "main_11GHz_100ps_remaining_factor": math.exp(-2*math.pi*11e9*100e-12),
            "auxiliary_7GHz_80ps_remaining_factor": math.exp(-2*math.pi*7e9*80e-12),
            "main_if_tracking_also_11GHz_100ps_memory_factor": math.exp(-2*math.pi*11e9*200e-12),
            "auxiliary_if_tracking_7GHz_100ps_memory_factor": math.exp(-2*math.pi*7e9*180e-12),
            "tracking_duration_and_bandwidth_are_assumed": True,
        },
    }


def effective_thresholds():
    main = lambda u: 4*u
    auxiliary = lambda u: F(19, 5)*u+F(2, 5)*u**3+F(1, 200)
    nominal = tuple(F(2*j-7, 16) for j in range(8))
    trimmed = tuple(auxiliary(t/4) for t in nominal)
    assert all(a < b for a, b in zip(trimmed, trimmed[1:]))
    inputs = [F(-1, 8)+F(j, 4*8192) for j in range(8193)]
    epsilon = F(1, 10**80)
    inputs += [t/4+step for t in nominal for step in (-epsilon, F(0), epsilon)]
    for u in inputs:
        reference = sum(main(u) >= t for t in nominal)
        corrected = sum(auxiliary(u) >= t for t in trimmed)
        assert reference == corrected
    # An untrimmed history-dependent auxiliary offset moves the decision,
    # despite exact matching at the calibration history.
    u = F(1, 64)-F(1, 100000)
    actual_main = main(u)
    original_code = sum(auxiliary(u) >= t for t in trimmed)-4
    changed_code = sum(auxiliary(u)+F(1, 1000) >= t for t in trimmed)-4
    assert original_code == 0 and changed_code == 1
    residue = actual_main-F(changed_code, 8)+F(1, 64)
    assert abs(residue) < F(1, 8)
    return {
        "scope": "analytic nonlinear monotone paths, invented for theorem verification; not chip curves",
        "inputs_checked": len(inputs), "boundary_epsilon": str(epsilon),
        "main_function": "4*u", "auxiliary_function": "(19/5)*u+(2/5)*u^3+1/200",
        "nominal_main_referenced_thresholds_volt": [str(t) for t in nominal],
        "trimmed_auxiliary_thresholds_volt": [str(t) for t in trimmed],
        "history_counterexample": {
            "input_volt": str(u), "main_volt": str(actual_main),
            "auxiliary_added_history_offset_volt": "1/1000",
            "reference_symbol": original_code, "changed_symbol": changed_code,
            "second_stage_preamp_residue_with_candidate_dither_volt": str(residue),
            "no_overload_under_nominal_gain_four": True,
        },
    }


def decimation_phases():
    checked = 0
    for period in range(1, 512):
        divisor = math.gcd(period, 120)
        for phase in (0, 17, 29):
            for initial in (0, 7):
                per_lane = [{(120*b+4*phase+lane+initial) % period for b in range(period)}
                            for lane in range(4)]
                assert all(len(states) == period//divisor for states in per_lane)
                union = set().union(*per_lane)
                assert len(union) == min(4, divisor)*period//divisor
                checked += 1
    examples = []
    for period in (31, 63, 120, 255):
        divisor = math.gcd(period, 120)
        examples.append({"period": period, "gcd_with_120": divisor,
                         "states_per_selected_lane": period//divisor,
                         "states_across_four_selected_lanes": min(4, divisor)*period//divisor})
    dither = [1]*60+[-1]*60
    full_correlation = F(sum(dither), 120)
    selected_correlation = F(sum(dither[lane] for lane in range(4)), 4)
    assert full_correlation == 0 and selected_correlation == 1
    return {
        "scope": "point-decimation candidate only; no inference of the unpublished chip decimator",
        "index_rule": "n=120*b+4*r+lane+n0; lane permutation is arbitrary",
        "periods_checked": 511, "phase_and_initial_offset_configurations_checked": checked,
        "examples": examples,
        "first_gate_always_on_counterexample": {
            "period": 120, "dither_rule": "first 60 signs positive, next 60 negative",
            "learning_output": "constant 1", "selected_phase": 0,
            "full_record_mean_dither_times_output": str(full_correlation),
            "selected_four_lane_mean_dither_times_output": str(selected_correlation),
            "not_claimed_as_a_real_PRNG_sequence": True,
        },
    }


def run():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    summary = {
        "date": "2026-10-09", "cadence_used": False, "new_physical_measurements": False,
        "scope": "source_constrained_mechanism_research_and_conditional_derivations",
        "reset_phase": reset_phase(), "effective_thresholds": effective_thresholds(),
        "decimation_phases": decimation_phases(),
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            ROOT/"references/local/OJSSCS2026_Gu.pdf",
            ROOT/"references/local/ISSCC2025_Gu_Slides.pdf",
            Path(__file__).resolve(),
        )},
    }
    (OUTPUT/"mechanism_checks.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run()
