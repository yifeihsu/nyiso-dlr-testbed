import unittest
import numpy as np

from dc_model import DCModel, map_bus_values, port_injection_map, score


def fixture():
    bus = np.zeros((3, 13))
    bus[:, 0] = [74, 80, 82]
    branch = np.zeros((3, 13))
    branch[:, :2] = [[74, 80], [80, 82], [74, 82]]
    branch[:, 3] = [.1, .2, .3]
    branch[:, 10] = 1
    return bus, branch


class DCChecks(unittest.TestCase):
    def test_two_bus_tap_phase_and_explicit_balance(self):
        bus, branch = fixture()
        branch = branch[:1]
        branch[0, 8:10] = [2, 5]
        r = DCModel(bus[:2], branch).solve([[40, -50]])
        self.assertAlmostEqual(r['flow'][0, 0], 50)
        self.assertAlmostEqual(r['slack_adjustment_mw'][0], 10)
        self.assertAlmostEqual(r['angle_deg'][0, 1], -5 - np.rad2deg(.1))

    def test_complete_cut_depends_on_net_injection(self):
        bus, branch = fixture()
        for x in [.05, .5]:
            branch[1, 3] = x
            m = DCModel(bus, branch)
            r = m.solve([[70, -20, -50]])
            np.testing.assert_allclose(r['flow'] @ m.cut([74]), [70], atol=1e-10)

    def test_consistent_power_scaling(self):
        bus, branch = fixture()
        m = DCModel(bus, branch)
        p = np.array([[70, -20, -50]])
        np.testing.assert_allclose(m.solve(p * .358)['flow'], m.solve(p)['flow'] * .358, atol=1e-10)

    def test_missing_nonzero_terminal_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'missing terminal'):
            map_bus_values([[1, 2]], [74, 77], [74, 80])

    def test_missing_zero_terminal_can_be_omitted(self):
        np.testing.assert_equal(map_bus_values([[1, 0]], [74, 77], [80, 74]), [[0, 1]])

    def test_disconnected_network_is_rejected(self):
        bus, branch = fixture()
        branch[1:, 10] = 0
        with self.assertRaisesRegex(ValueError, 'Disconnected'):
            DCModel(bus, branch)

    def test_near_zero_and_reverse_flows_remain_visible(self):
        r = score(np.array([[1., 2.]]), np.array([[-.01, 100.]]))
        self.assertAlmostEqual(r['absolute_error_pct'][0, 0], 10100)
        self.assertTrue(r['wrong_direction'][0, 0])

    def test_nonfinite_predictions_are_not_excluded(self):
        with self.assertRaises(ValueError):
            score(np.array([[np.nan]]), np.array([[1.]]))

    def test_internal_generation_is_split_by_exact_port_equations(self):
        bus, branch = fixture()
        branch[0,3] = branch[1,3] = .2
        net = DCModel(bus,branch)
        mapping, _, _, _ = port_injection_map(net,[74,82])
        np.testing.assert_allclose(mapping[:,1],[.5,.5],atol=1e-12)
        np.testing.assert_allclose(mapping.sum(axis=0),1,atol=1e-12)

    def test_phase_mapping_requires_explicit_offset_handling(self):
        bus, branch = fixture()
        branch[0,9] = 5
        with self.assertRaisesRegex(ValueError,'phase-offset'):
            port_injection_map(DCModel(bus,branch),[74,82])


if __name__ == '__main__':
    unittest.main()
