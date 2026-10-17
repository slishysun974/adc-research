"""Offline finite output criteria; no learner, platform or stopping rule.

Scores belong to equal-duration coherent blocks. Group powers and MSE are
arithmetic means; dB means remain a separate guard. No independence or
asymptotic convergence is inferred from these decisions.
"""

from fractions import Fraction
from math import isfinite


def _number(value):
    if isinstance(value, bool) or not isfinite(value):
        raise ValueError('finite numeric score required')
    return value if isinstance(value, Fraction) else Fraction(value)


def group_scores(scores, size=8):
    if not scores or size <= 0 or len(scores) % size:
        raise ValueError('nonempty complete equal-size groups required')
    fields = ('mse_codes_squared', 'residual_power', 'sndr_db')
    result = []
    for start in range(0, len(scores), size):
        group = {key: sum((_number(s[key]) for s in scores[start:start+size]),
                          Fraction(0))/size for key in fields}
        if group['mse_codes_squared'] < 0 or group['residual_power'] < 0:
            raise ValueError('nonnegative losses required')
        result.append(group)
    return result


def benefit(group, unit, margin=Fraction(1, 10)):
    if not 0 < margin < 1:
        raise ValueError('benefit margin must be between zero and one')
    # A zero reference cannot certify strictly positive improvement.
    return (unit['mse_codes_squared'] > 0 and unit['residual_power'] > 0
            and group['mse_codes_squared'] <= (1-margin)*unit['mse_codes_squared']
            and group['residual_power'] <= (1-margin)*unit['residual_power']
            and group['sndr_db'] >= unit['sndr_db'])


def recovery(carry, fresh, unit, gap=Fraction(1, 10), db_gap=Fraction(1)):
    if gap < 0 or db_gap < 0:
        raise ValueError('nonnegative pair tolerances required')
    return (benefit(carry, unit) and benefit(fresh, unit)
            and all(abs(carry[key]-fresh[key]) <= gap*fresh[key]
                    for key in ('mse_codes_squared', 'residual_power'))
            and abs(carry['sndr_db']-fresh['sndr_db']) <= db_gap)


def intervals(passed_groups, need=3, group_blocks=8, samples_per_block=30720):
    """First pass, every later violation, and terminal sustained suffix."""
    values = tuple(passed_groups)
    if need <= 0 or group_blocks <= 0 or samples_per_block <= 0:
        raise ValueError('positive lengths required')
    if len(values) < need or any(type(value) is not bool for value in values):
        raise ValueError('at least need boolean groups required')
    rows = [{'end_block_exclusive': end*group_blocks,
             'passed': all(values[end-need:end])}
            for end in range(need, len(values)+1)]
    first = next((row['end_block_exclusive'] for row in rows if row['passed']), None)
    trailing = 0
    for value in reversed(values):
        if not value:
            break
        trailing += 1
    return {
        'first_pass_block': first,
        'first_pass_conversion': None if first is None else first*samples_per_block,
        'later_violations': sum(not row['passed'] for row in rows
                                if first is not None and row['end_block_exclusive'] > first),
        'terminal_pass': rows[-1]['passed'],
        'terminal_good_groups': trailing,
        'terminal_good_conversions': trailing*group_blocks*samples_per_block,
        'intervals': rows,
        'asymptotic_convergence_proved': False,
    }
