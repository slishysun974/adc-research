"""Independent exact controls for ordered periodic comparison tubes."""
from fractions import Fraction as F
from itertools import product
import unittest

from adc_research.theory.triangular_cascade_bounds import (
    cascade_bound, periodic_cascade_tube, tube_fits_caps,
)


# Explicitly assumed comparison maps, not fitted Gu parameters.
PHASES = ((2, F(1,2), 1, F(1,8), F(1,16)),
          (F(1,4), F(1,2), 0, F(1,8), F(1,16)))


class PeriodicCascadeTubeTests(unittest.TestCase):
    def test_hand_calculated_period_and_intermediate_radii(self):
        tube = periodic_cascade_tube(PHASES)
        self.assertEqual((tube.period_front, tube.period_rear,
                          tube.period_coupling), (F(1,2), F(1,4), F(1,4)))
        self.assertEqual((tube.period_error_front, tube.period_error_rear),
                         (F(5,32), F(3,32)))
        self.assertEqual(tube.front, (F(3,8), F(1), F(3,8)))
        self.assertEqual(tube.rear, (F(1,8), F(1,8), F(1,8)))

    def test_all_initial_corners_and_disturbance_signs_four_steps(self):
        tube = periodic_cascade_tube(PHASES)
        attained = []
        for initial in product((-1,1), repeat=2):
            for signs in product((-1,1), repeat=8):
                front, rear = initial[0]*F(3,8), initial[1]*F(1,8)
                for m in range(4):
                    f1, f2, b, d1, d2 = PHASES[m % 2]
                    front, rear = (f1*front + b*rear + signs[2*m]*d1,
                                   f2*rear + signs[2*m+1]*d2)
                    self.assertLessEqual(abs(front), tube.front[(m+1) % 2])
                    self.assertLessEqual(abs(rear), tube.rear[(m+1) % 2])
                attained.append((front,rear))
        self.assertEqual(attained[-1], (F(3,8), F(1,8)))

    def test_phase_rotation_preserves_the_same_tube_with_shifted_origin(self):
        forward = periodic_cascade_tube(PHASES)
        shifted = periodic_cascade_tube(PHASES[1:]+PHASES[:1])
        self.assertEqual(shifted.front, (forward.front[1],forward.front[0],forward.front[1]))
        self.assertEqual(shifted.rear, (forward.rear[1],forward.rear[0],forward.rear[1]))
        # Coupling and forcing change when the origin changes.
        self.assertEqual(shifted.period_coupling, F(1,2))
        self.assertNotEqual(shifted.period_error_front, forward.period_error_front)

    def test_all_phases_must_fit_protected_caps(self):
        tube = periodic_cascade_tube(PHASES)
        self.assertTrue(tube_fits_caps(tube, ((F(3,8),F(1,8)), (1,F(1,8)))))
        # Cycle endpoints fit, but the front radius reaches 1 in between.
        self.assertFalse(tube_fits_caps(tube, ((F(3,8),F(1,8)), (F(3,8),F(1,8)))))

    def test_moving_reference_defect_is_required(self):
        # Reference centers rear 0->1->0, maps T0(x)=x/2+1,
        # T1(x)=x/2-1/2 form an exact period with no common fixed point.
        centers = (F(0),F(1),F(0))
        offsets = (F(1),F(-1,2))
        defects = tuple(abs(centers[j]/2+offsets[j]-centers[j+1]) for j in range(2))
        self.assertEqual(defects, (0,0))
        tube = periodic_cascade_tube(((F(1,2),F(1,2),0,0,0),)*2)
        self.assertEqual(tube.rear, (0,0,0))
        wrong_centers = (F(0),F(0),F(0))
        wrong = tuple(abs(wrong_centers[j]/2+offsets[j]-wrong_centers[j+1]) for j in range(2))
        self.assertEqual(wrong, (1,F(1,2)))
        perturbed = periodic_cascade_tube(tuple((F(1,2),F(1,2),0,0,x) for x in wrong))
        self.assertEqual(perturbed.rear, (F(4,3),F(5,3),F(4,3)))

    def test_constant_period_reproduces_original_error_floor(self):
        tube = periodic_cascade_tube(((F(1,2),F(1,4),3,F(1,8),F(1,16)),))
        old = cascade_bound(F(1,2),F(1,4),3,F(1,8),F(1,16),0,0,0)
        self.assertEqual((tube.front[0],tube.rear[0]), (old.front_limit,old.rear_limit))
        self.assertEqual(tube.front[0],tube.front[-1])

    def test_ordered_coupling_matches_direct_matrix_composition(self):
        # Exercise old-rear timing and three distinct phases independently.
        rows = ((F(3,2),F(2,3),2,F(1,7),F(1,8)),
                (F(1,3),F(3,2),1,F(1,9),F(1,10)),
                (F(1,2),F(1,3),3,F(1,11),F(1,12)))
        tube = periodic_cascade_tube(rows)
        columns = []
        for start in ((1,0),(0,1)):
            f,r = map(F,start)
            for a,d,b,_,_ in rows: f,r = a*f+b*r,d*r
            columns.append((f,r))
        self.assertEqual(columns, [(tube.period_front,0),
                                  (tube.period_coupling,tube.period_rear)])
        f,r = F(0),F(0)
        for a,d,b,u,v in rows: f,r = a*f+b*r+u,d*r+v
        self.assertEqual((f,r), (tube.period_error_front,tube.period_error_rear))

    def test_diagonal_cycle_stability_and_input_conditions_are_required(self):
        for rows in ((), ((1,F(1,2),0,0,0),), ((F(1,2),2,0,0,0),),
                     ((-1,F(1,2),0,0,0),), ((F(1,2),F(1,2),0,0),)):
            with self.assertRaises(ValueError): periodic_cascade_tube(rows)
        tube = periodic_cascade_tube(PHASES)
        for caps in ((), ((1,1),), ((1,1),(-1,1)), ((1,1),(1,))):
            with self.assertRaises(ValueError): tube_fits_caps(tube,caps)


if __name__ == '__main__': unittest.main()
