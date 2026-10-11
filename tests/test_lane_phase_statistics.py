from fractions import Fraction as F
from itertools import product
import unittest

from adc_research.theory.lane_phase_statistics import lane_phase_moments, is_positive_semidefinite
from adc_research.theory.static_fixed_contract import readout


def enumerated_moments(rows, lanes, choices):
    values = [tuple(sum((rows[p*lanes+l][i] for l, p in enumerate(choice)), F(0))/lanes
                    for i in range(len(rows[0]))) for choice in choices]
    mean = tuple(sum(v[i] for v in values)/len(values) for i in range(len(values[0])))
    cov = tuple(tuple(sum((v[i]-mean[i])*(v[j]-mean[j]) for v in values)/len(values)
                      for j in range(len(mean))) for i in range(len(mean)))
    return mean, cov


class LanePhaseStatisticsTests(unittest.TestCase):
    def test_all_joint_choices_match_formula_and_shared_enumeration(self):
        rows = [(F(p-l), F((p+1)*(l+1))) for p in range(3) for l in range(4)]
        result = lane_phase_moments(rows)
        m, c = enumerated_moments(rows, 4, product(range(3), repeat=4))
        self.assertEqual(m, result.full_mean)
        self.assertEqual(c, result.independent_covariance)
        m, c = enumerated_moments(rows, 4, [(p,)*4 for p in range(3)])
        self.assertEqual(m, result.full_mean)
        self.assertEqual(c, result.shared_covariance)

    def test_digital_in_phase_control_independent_is_quarter(self):
        rows = []
        for phase in range(2):
            for lane in range(4):
                z = readout(0, 0, F(15+2*phase), 1, 1, (F(1),)*8, data_q3=True)
                rows.append(tuple(d*y*int(g) for d,y,gs in
                                  [(F(16),z.y2,z.gates[1]), (F(64),z.y1,z.gates[0])] for g in gs))
        result = lane_phase_moments(rows)
        self.assertEqual(result.independent_covariance,
                         tuple(tuple(x/4 for x in row) for row in result.shared_covariance))
        self.assertTrue(any(x for row in result.shared_covariance for x in row))
        self.assertTrue(is_positive_semidefinite(result.cross_contribution))

    def test_digital_cancellation_control_independent_worsens(self):
        rows = []
        for phase in range(2):
            for lane in range(4):
                backend = F(16 + (-1)**(phase+lane))
                z = readout(0, 0, backend, 1, 1, (F(1),)*8, data_q3=True)
                rows.append(tuple(d*y*int(g) for d,y,gs in
                                  [(F(16),z.y2,z.gates[1]), (F(64),z.y1,z.gates[0])] for g in gs))
        result = lane_phase_moments(rows)
        self.assertTrue(all(x == 0 for row in result.shared_covariance for x in row))
        self.assertTrue(any(x for row in result.independent_covariance for x in row))
        self.assertFalse(is_positive_semidefinite(result.cross_contribution))

    def test_zero_cross_covariance_equal_and_fixed_bias_is_not_variance(self):
        rows = [(F(1),),(F(0),),(F(0),),(F(0),),
                (F(-1),),(F(0),),(F(0),),(F(0),)]
        result = lane_phase_moments(rows)
        self.assertEqual(result.shared_covariance, result.independent_covariance)
        self.assertEqual(result.full_mean, (F(0),))
        self.assertEqual(result.shared_covariance, ((F(1,16),),))
        self.assertEqual(sum(r[0] for r in rows[:4])/4, F(1,4))

    def test_psd_handles_zero_pivots_singular_and_mixed_directions(self):
        for a in [((0,0),(0,0)), ((0,0),(0,2)), ((1,2),(2,4)), ((2,1),(1,2))]:
            self.assertTrue(is_positive_semidefinite(a))
        for a in [((0,1),(1,0)), ((1,2),(2,1)), ((-1,0),(0,3))]:
            self.assertFalse(is_positive_semidefinite(a))

    def test_coordinate_mixing_transforms_covariance_without_changing_order(self):
        rows = [(F(phase-lane), F(phase*lane)) for phase in range(3) for lane in range(4)]
        mixed = [(a+2*b, 3*a-b) for a,b in rows]
        result, transformed = lane_phase_moments(rows), lane_phase_moments(mixed)
        t = ((1,2),(3,-1))
        for original, actual in [(result.shared_covariance, transformed.shared_covariance),
                                 (result.independent_covariance, transformed.independent_covariance)]:
            expected = tuple(tuple(sum(F(t[i][a])*original[a][b]*t[j][b]
                                      for a in range(2) for b in range(2))
                                   for j in range(2)) for i in range(2))
            self.assertEqual(expected, actual)

    def test_rejects_float_ragged_and_asymmetric_contracts(self):
        with self.assertRaises(TypeError):
            lane_phase_moments([(0.1,)]*4)
        for rows in [[], [(1,)]*3, [(1,),(1,2),(1,),(1,)]]:
            with self.assertRaises(ValueError):
                lane_phase_moments(rows)
        with self.assertRaises(ValueError):
            is_positive_semidefinite(((1,2),(0,1)))


if __name__ == '__main__':
    unittest.main()
