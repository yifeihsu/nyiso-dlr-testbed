"""Focused preservation, weak-edge, and affine DC recovery checks."""
import copy
import unittest

import numpy as np
import pandas as pd
from scipy.io import loadmat

from build_slim_network import (DEFAULT, SOURCE_CASES, VARIANTS, KEEP_ADDED,
                                dc, reduce_added_components, zone_operators)


def simple_case(ids, branches):
    bus = np.zeros((len(ids), 13))
    bus[:, 0] = ids
    bus[:, 1], bus[:, 7], bus[:, 9] = 1, 1, 345
    return dict(baseMVA=100., bus=bus, branch=np.array(branches, float),
                gen=np.empty((0,21)), dcline=np.empty((0,17)))


def row(a,b,x,tap=0,shift=0):
    return [a,b,0,x,0,0,0,0,tap,shift,1,-360,360]


def realize(case, keep, reduced):
    candidate = copy.deepcopy(case)
    candidate["bus"] = case["bus"][reduced["retained_indices"]]
    branches = case["branch"][reduced["direct_rows"]].tolist()
    for (a,b), edge in reduced["edges"].items():
        branches.append(row(a,b,edge["x_pu"],1.,edge["shift_degree"]))
    candidate["branch"] = np.asarray(branches)
    return candidate


class ComponentPhysics(unittest.TestCase):
    def test_nonunity_taps_phase_shifts_and_retained_direct_row(self):
        case = simple_case([1,2,3,10,11], [row(1,2,.05,1.05,3), row(1,10,.1,1.11,7),
                    row(10,2,.2,0,-2), row(10,11,.06,1.02,4), row(11,3,.13,0,-6), row(2,11,.4,0,1)])
        reduced = reduce_added_components(case,[1,2,3])
        candidate = realize(case,[1,2,3],reduced)
        np.testing.assert_array_equal(candidate["branch"][0],case["branch"][0])
        self.assertGreater(np.max(abs(candidate["branch"][1:,9])), 0)
        np.testing.assert_allclose(dc(candidate)["B"],reduced["Schur_B"],atol=1e-10,rtol=0)
        np.testing.assert_allclose(dc(candidate)["phase_bus"],reduced["Schur_phase"],atol=1e-10,rtol=0)
        theta = np.random.default_rng(601).normal(size=(20,3))*.05
        lift = theta@reduced["angle_lift"].T+reduced["angle_offset"]
        full=dc(case)
        actual_flow=lift@full["F"].T+full["phase_branch"]
        recovered=theta@reduced["branch_angle_matrix"].T+reduced["branch_flow_offset"]
        np.testing.assert_allclose(actual_flow,recovered,atol=1e-10,rtol=0)
        injection=actual_flow@full["C"]
        np.testing.assert_allclose(injection[:,3:],0,atol=1e-10,rtol=0)

    def test_weak_structural_edge_is_never_threshold_pruned(self):
        case=simple_case([1,2,10],[row(1,10,1e14),row(10,2,1e14)])
        reduced=reduce_added_components(case,[1,2])
        self.assertEqual(set(reduced["edges"]),{(1,2)})
        self.assertLess(reduced["edges"][(1,2)]["weight"],1e-10)
        self.assertAlmostEqual(reduced["edges"][(1,2)]["x_pu"]/2e14,1.)

    def test_single_port_phase_leaf_has_no_port_effect_but_offset_recovers(self):
        case=simple_case([1,2,10],[row(1,2,.1),row(1,10,.2,1.1,9)])
        reduced=reduce_added_components(case,[1,2])
        self.assertEqual(reduced["edges"],{})
        self.assertGreater(abs(reduced["angle_offset"][2]),0)
        np.testing.assert_allclose(reduced["Schur_phase"],0,atol=1e-10,rtol=0)

    def test_interior_injections_and_nonpassive_edges_are_rejected(self):
        base=simple_case([1,2,10],[row(1,10,.1),row(10,2,.2)])
        for column in [2,3,4,5]:
            changed=copy.deepcopy(base);changed["bus"][2,column]=1
            with self.assertRaises(ValueError):reduce_added_components(changed,[1,2])
        changed=copy.deepcopy(base);changed["gen"]=np.zeros((1,21));changed["gen"][0,0]=10
        with self.assertRaises(ValueError):reduce_added_components(changed,[1,2])
        changed=copy.deepcopy(base);changed["branch"][0,3]=-.1
        with self.assertRaises(ValueError):reduce_added_components(changed,[1,2])


class DeliveredSlim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slim=loadmat(DEFAULT/"network_cases.mat",simplify_cells=True)
        cls.full=loadmat(SOURCE_CASES,simplify_cells=True)
        cls.reg=pd.read_csv(DEFAULT/"branch_register.csv",keep_default_na=False)

    def test_original_grid_devices_and_direct_source_rows_unchanged(self):
        np.testing.assert_array_equal(self.slim["kept_bus_ids"],list(range(1,141))+KEEP_ADDED)
        self.assertEqual(len(self.slim["eliminated_bus_ids"]),43)
        self.assertTrue(np.all(self.slim["eliminated_bus_ids"]>140))
        for name in VARIANTS:
            a,b=self.slim[name+"_case"],self.full[name+"_case"]
            np.testing.assert_array_equal(a["bus"][:140],b["bus"][:140])
            np.testing.assert_array_equal(a["branch"][:225],b["branch"][:225])
            np.testing.assert_array_equal(a["gen"],b["gen"])
            np.testing.assert_array_equal(a["dcline"],b["dcline"])
            for r in self.reg.loc[self.reg.full191_branch_row.gt(0)].itertuples():
                np.testing.assert_array_equal(a["branch"][r.model_branch_row-1],b["branch"][r.full191_branch_row-1])
            equivalent=self.reg.role.eq("passive_DC_Schur_equivalent").to_numpy()
            self.assertTrue(np.all(a["branch"][equivalent][:,[2,4,5,6,7]]==0))
            self.assertTrue(np.all(a["branch"][equivalent,3]>0))

    def test_random_retained_injections_reproduce_full_solution_and_all_flows(self):
        for name in VARIANTS:
            small,big=self.slim[name+"_case"],self.full[name+"_case"]
            ns,nf=dc(small),dc(big);r=self.slim["recovery"][name]
            keep=self.slim["kept_bus_ids"].astype(int);rows=np.array([nf["lookup"][bid] for bid in keep])
            p=np.random.default_rng(771).normal(size=(25,148))*40;p-=p.mean(axis=1)[:,None]
            theta=np.zeros_like(p);theta[:,1:]=np.linalg.solve(ns["B"][1:,1:],(p[:,1:]-ns["phase_bus"][1:]).T).T
            q=np.zeros((25,191));q[:,rows]=p
            full_theta=np.zeros_like(q);full_theta[:,1:]=np.linalg.solve(nf["B"][1:,1:],(q[:,1:]-nf["phase_bus"][1:]).T).T
            recovered_theta=theta@r["angle_lift"].T+r["angle_offset"]
            np.testing.assert_allclose(recovered_theta,full_theta,atol=1e-10,rtol=0)
            expected=full_theta@nf["F"].T+nf["phase_branch"]
            flow=theta@r["branch_angle_matrix"].T+r["branch_flow_offset"]
            np.testing.assert_allclose(flow,expected,atol=1e-7,rtol=0)
            direct_interface=expected@r["full_interface_branch_matrix"].T
            exact_interface=theta@r["interface_angle_matrix"].T+r["interface_flow_offset"]
            np.testing.assert_allclose(exact_interface,direct_interface,atol=1e-7,rtol=0)

    def test_Dunwoodie_local_cut_is_not_mislabeled_as_recovered_operator(self):
        for name in VARIANTS:
            case=self.slim[name+"_case"];r=self.slim["recovery"][name]
            self.assertEqual(set(case["if"]["map"][:,0]),{1,2,3,4,5,8})
            self.assertEqual(np.atleast_1d(case["if"]["omitted_interface_ids"]).tolist(),[10])
            self.assertGreater(np.max(abs(r["interface_angle_matrix"][6]-r["local_interface_angle_matrix"][6])),1)
            np.testing.assert_allclose(r["interface_angle_matrix"][:6],r["local_interface_angle_matrix"][:6],atol=1e-8,rtol=0)


if __name__=="__main__":
    unittest.main()
