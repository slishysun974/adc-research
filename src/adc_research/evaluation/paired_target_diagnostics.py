"""Offline paired-target leakage; no target enters a digital contrast solve."""

from fractions import Fraction as F


def decompose_pair_targets(target_plus, target_minus, local_plus, local_minus, magnitude,
                           gate_plus=True, gate_minus=True):
    if any(not isinstance(x, F) for x in (target_plus, target_minus, local_plus, local_minus, magnitude)):
        raise TypeError("explicit Fraction targets, outputs and magnitude required")
    if magnitude <= 0 or any(not isinstance(g, bool) for g in (gate_plus, gate_minus)):
        raise ValueError("positive magnitude and Boolean gates required")
    target_mean = (target_plus+target_minus)/2
    target_difference = target_plus-target_minus
    mean_gate = F(int(gate_plus)+int(gate_minus), 2)
    gate_difference = int(gate_plus)-int(gate_minus)
    signal = magnitude*(gate_plus*target_plus-gate_minus*target_minus)/2
    mismatch = magnitude*mean_gate*target_difference/2
    selection = magnitude*gate_difference*target_mean/2
    error = magnitude*(gate_plus*(local_plus-target_plus)-gate_minus*(local_minus-target_minus))/2
    learning = magnitude*(gate_plus*local_plus-gate_minus*local_minus)/2
    assert signal == mismatch+selection
    assert learning == signal+error
    return {'target_signal_contribution': signal, 'target_mismatch_contribution': mismatch,
            'gate_mismatch_contribution': selection, 'error_contribution': error,
            'learning_contribution': learning,
            'signal_leakage_bound': magnitude*(abs(mean_gate*target_difference)+abs(gate_difference*target_mean))/2,
            'equal_target': target_plus == target_minus, 'shared_gate': gate_plus == gate_minus,
            'identities_verified': True}
