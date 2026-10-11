"""Independent augmented-matrix fixtures for source-controlled DC flow replay."""
import unittest

import numpy as np

from dc_control import controlled_predict, network, phase_response


def case():
    bus = np.zeros((3, 13)); bus[:, 0] = [11, 23, 37]; bus[:, 1] = [3, 1, 1]
    bus[:, 7] = 1
    gen = np.zeros((1, 21)); gen[0, 0] = 11; gen[0, 7] = 1
    branch = np.zeros((3, 13)); branch[:, :2] = [[11, 23], [23, 37], [11, 37]]
    branch[:, 3] = [.12, .18, .31]; branch[:, 8] = [1.07, 0, .98]
    branch[:, 9] = [3.5, -2, 0]; branch[:, 10] = 1
    dc = np.zeros((1, 17)); dc[0, :3] = [11, 37, 1]
    return dict(baseMVA=100., bus=bus, gen=gen, branch=branch, dcline=dc)


class ControlTests(unittest.TestCase):
    def test_augmented_solution_with_taps_phases_and_signed_dc(self):
        c = case(); net = network(c)
        loads = np.array([[0., 70., 30.], [0., 40., 80.]])
        pg = np.array([[100.], [120.]])
        dc = np.array([[12.], [-8.]])
        targets = np.array([15., -20.])
        got = controlled_predict(c, loads, pg, dc, 1, targets)
        # Independently solve angles and an absolute phase in a bordered system.
        inc = np.array([[1., -1., 0.], [0., 1., -1.], [1., 0., -1.]])
        tap = np.array([1.07, 1., .98]); k = 100. / (c["branch"][:, 3] * tap)
        nodal = inc.T @ np.diag(k) @ inc
        fixed_phase = np.deg2rad(c["branch"][:, 9].copy()); fixed_phase[0] = 0
        offset = -k * fixed_phase
        a = np.zeros((3, 3)); a[:2, :2] = nodal[1:, 1:]
        a[:2, 2] = -k[0] * inc[0, 1:]
        a[2, :2] = k[0] * inc[0, 1:]; a[2, 2] = -k[0]
        for h in range(2):
            injection = np.array([pg[h, 0] - dc[h, 0], -loads[h, 1], -loads[h, 2] + dc[h, 0]])
            rhs = np.r_[(injection - inc.T @ offset)[1:], targets[h]]
            answer = np.linalg.solve(a, rhs)
            theta = np.r_[0., answer[:2]]
            phase = fixed_phase.copy(); phase[0] = answer[2]
            expected_flow = k * (inc @ theta - phase)
            np.testing.assert_allclose(got["flow"][h], expected_flow, atol=1e-10)
            np.testing.assert_allclose(got["angle_deg"][h], np.rad2deg(theta), atol=1e-10)
            self.assertAlmostEqual(got["equivalent_shift_deg"][h], np.rad2deg(answer[2]), places=10)
        np.testing.assert_allclose(got["result_pg"], pg, atol=1e-10, rtol=0)

    def test_rejects_bridge_control(self):
        c = case(); c["branch"] = c["branch"][:2]
        with self.assertRaisesRegex(ValueError, "fixed by a cut"):
            phase_response(network(c), 1)

    def test_rejects_missing_controls_and_unbalanced_dispatch(self):
        c = case(); pd = np.array([[0., 70., 30.]])
        with self.assertRaisesRegex(ValueError, "finite value"):
            controlled_predict(c, pd, np.array([[100.]]), np.array([[0.]]), 1, [np.nan])
        with self.assertRaisesRegex(ValueError, "balanced|nodal balance"):
            controlled_predict(c, pd, np.array([[90.]]), np.array([[0.]]), 1, [10.])


if __name__ == "__main__":
    unittest.main()
