"""Projection checks against constraints, split invariance and independent QP."""
import unittest
import numpy as np
from scipy.optimize import minimize
from build_dispatch import bounded_projection


class BoundedDispatchTests(unittest.TestCase):
    def test_matches_independent_constrained_optimizer(self):
        prior = np.array([[4., 9., 3., 12.]])
        lo = np.zeros_like(prior); hi = np.array([[5., 10., 7., 13.]])
        weights = np.array([[.2, 2., 1., .5]])
        target = np.array([18.])
        p, _, ok = bounded_projection(prior, lo, hi, target, weights)
        oracle = minimize(lambda x: .5 * np.sum(weights[0] * (x-prior[0])**2),
            np.full(4, 4.5), jac=lambda x: weights[0]*(x-prior[0]), method="SLSQP",
            bounds=list(zip(lo[0], hi[0])), constraints={"type":"eq", "fun":lambda x:x.sum()-18,
                "jac":lambda x:np.ones(4)}, options={"ftol":1e-14, "maxiter":100})
        self.assertTrue(ok[0] and oracle.success)
        np.testing.assert_allclose(p[0], oracle.x, atol=1e-7)

    def test_no_relaxation_for_insufficient_capacity(self):
        p, dual, ok = bounded_projection(np.ones((1, 2)), np.zeros((1, 2)), np.ones((1, 2)), [3.], np.ones((1, 2)))
        self.assertFalse(ok[0]); self.assertTrue(np.isnan(p).all() and np.isnan(dual).all())

    def test_fixed_variable_and_exact_balance(self):
        p, _, ok = bounded_projection(np.array([[2., 3.]]), np.array([[2., 0.]]),
                                      np.array([[2., 8.]]), [7.], np.ones((1, 2)))
        self.assertTrue(ok[0]); np.testing.assert_allclose(p, [[2., 5.]], atol=1e-10)

    def test_capacity_weighted_objective_is_split_invariant(self):
        a, _, _ = bounded_projection(np.array([[20., 10.]]), np.zeros((1,2)),
                                     np.array([[40., 20.]]), [45.], np.array([[1/40, 1/20]]))
        b, _, _ = bounded_projection(np.array([[10., 10., 10.]]), np.zeros((1,3)),
                                     np.array([[20., 20., 20.]]), [45.], np.array([[1/20]*3]))
        np.testing.assert_allclose(a[0], [b[0,:2].sum(), b[0,2]], atol=1e-10)

    def test_nonfinite_or_inverted_bounds_are_rejected(self):
        for hi in [np.array([[np.nan, 2.]]), np.array([[-1., 2.]])]:
            with self.assertRaises(ValueError):
                bounded_projection(np.ones((1,2)), np.zeros((1,2)), hi, [1.], np.ones((1,2)))


if __name__ == "__main__":
    unittest.main()
