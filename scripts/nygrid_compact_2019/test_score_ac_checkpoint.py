"""Small mathematical counterexamples for AC terminal/error conventions."""
import unittest

import numpy as np

from score_ac_checkpoint import relative_error, terminal_coefficients, wape


class ScoreACCheckpointTest(unittest.TestCase):
    def test_reverse_terminal_includes_the_correct_side_of_losses(self):
        # Branch2 carries 100 MW from T to F, losing 2 MW. Its PF=-98 and
        # PT=100: the upstream T measurement must retain 100, not -PF=98.
        cf, ct = terminal_coefficients(np.array([[1, -1]], dtype=np.int8))
        pf = np.array([50., -98.]); pt = np.array([-49., 100.])
        self.assertEqual(float((cf@pf+ct@pt).item()),150.)
        self.assertEqual(float(((cf-ct)@pf).item()),148.)

    def test_exact_zero_undefined_and_near_zero_not_floored(self):
        actual=np.array([0.,.01,100.]);model=np.array([2.,.02,100.])
        error=relative_error(model,actual)
        self.assertTrue(np.isnan(error[0]));self.assertEqual(error[1],100.)
        self.assertAlmostEqual(wape(model,actual),100*2.01/100.01)
        self.assertIsNone(wape(np.array([1.]),np.array([0.])))

    def test_unsigned_wrapped_reverse_coefficient_rejected(self):
        with self.assertRaises(ValueError):
            terminal_coefficients(np.array([[0,255]],dtype=np.uint8))

    def test_uniform_power_scaling_preserves_percentages(self):
        actual=np.array([10.,-2.,100.]);model=np.array([9.,1.,103.]);gamma=.358662225381536
        np.testing.assert_allclose(relative_error(model,actual),relative_error(model*gamma,actual*gamma))
        self.assertAlmostEqual(wape(model,actual),wape(model*gamma,actual*gamma))


if __name__=='__main__':
    unittest.main()
