"""Independent saved-input checks for hydro-only Niagara counterfactuals.

Checks source targets, physical month hours, fixed-unit preservation, separate
literal/bounded hypothesis policies, and the declared original-weight optimum.
Does not call the builder, a power flow, or read interface observations/scores.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd
from scipy.io import loadmat

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"output/nygrid_2025_western_counterfactuals"
INPUTS=OUT/"inputs"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


class NiagaraInputChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt=json.loads((INPUTS/"niagara_receipt.json").read_text())
        cls.base=loadmat(ROOT/cls.receipt["baseline_dispatch_path"],simplify_cells=True,
                         variable_names=["gen_pg","gamma","timestamp_utc"])
        cls.pg=cls.base["gen_pg"];cls.gamma=float(cls.base["gamma"])
        cls.bounds=loadmat(ROOT/"output/nygrid_2025_dispatch/dispatch/dispatch_bounds.mat",simplify_cells=True,
                           variable_names=["gen_pmin","gen_pmax"])
        cls.weights=loadmat(ROOT/"output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat",simplify_cells=True,
                            variable_names=["objective_weights"])["objective_weights"]
        cls.mask=np.load(ROOT/"output/nygrid_2025_western_audit/replay/paired_common_mask.npy",allow_pickle=False)
        cls.scope=pd.read_csv(INPUTS/"niagara_generator_scope.csv")
        cls.eia=pd.read_csv(ROOT/"output/nygrid_2025_western_audit/generation/target_EIA923_final_monthly.csv")
        cls.eia=cls.eia.loc[cls.eia.plant_id.eq(2693)&cls.eia.prime_mover.eq("HY")&cls.eia.sheet.eq("Page 1 Generation and Fuel Data")].set_index("month")
        cls.times=pd.to_datetime(np.asarray(cls.base["timestamp_utc"]).astype(str),utc=True)
        cls.months=cls.times.tz_convert("America/New_York").month.to_numpy()
        cls.fuel=pd.read_csv(ROOT/"output/nygrid_2025_inputs/generation_source/statewide_fuelmix_hourly.csv",
                             usecols=["hour_index","fuel_category","generation_mw"])
        cls.H=cls.fuel.loc[cls.fuel.fuel_category.eq("Hydro")].sort_values("hour_index").generation_mw.to_numpy()*cls.gamma
        cls.data={s["name"]:dict(np.load(ROOT/s["file"],allow_pickle=False)) for s in cls.receipt["scenarios"]}
        cls.held=np.r_[cls.receipt["fixed_groups"]["StLawrence_rows_1based"],cls.receipt["fixed_groups"]["PS_rows_1based"],cls.receipt["fixed_groups"]["external_rows_1based"]]-1
        cls.rmn=cls.scope.loc[cls.scope.RMN_target,"gen_row"].to_numpy(int)-1
        cls.stl=cls.scope.loc[cls.scope.fixed_StLawrence,"gen_row"].to_numpy(int)-1

    def test_sealed_baseline_and_dependency_hashes(self):
        self.assertTrue(self.receipt["passed"])
        self.assertEqual(sha(ROOT/self.receipt["baseline_dispatch_path"]),self.receipt["baseline_dispatch_sha256"])
        self.assertEqual(self.receipt["fixed_experiment_mask_sha256"],sha(ROOT/"output/nygrid_2025_western_audit/replay/paired_common_mask.npy"))
        for record in self.receipt["dependencies"]+self.receipt["output_evidence"]:
            self.assertEqual(sha(ROOT/record["path"]),record["sha256"],record["path"])
        for record in self.receipt["scenarios"]:
            self.assertEqual(sha(ROOT/record["file"]),record["sha256"],record["name"])

    def test_fixed_hour_masks_and_unavailable_rows(self):
        self.assertEqual(int(self.mask.sum()),8651)
        for s in self.receipt["scenarios"]:
            d=self.data[s["name"]];q=d["qualified"]
            self.assertEqual(q.dtype,bool)
            self.assertFalse(np.any(q&~self.mask))
            self.assertEqual(int(q.sum()),s["qualified_hours"])
            self.assertTrue(np.array_equal(d["fixed_experiment_mask"],self.mask))
            self.assertTrue(np.array_equal(d["hour_index"],np.arange(1,8761)))
            self.assertTrue(np.array_equal(d["timestamp_utc"],np.asarray(self.base["timestamp_utc"]).astype(str)))
            self.assertTrue(np.isfinite(d["gen_pg_changed"][q]).all())
            self.assertTrue(np.isnan(d["gen_pg_changed"][~q]).all())
            if s["full_fixed_cohort"]:
                self.assertTrue(np.array_equal(q,self.mask))
            else:
                self.assertEqual(s["scope"],"restricted_feasibility_diagnostic_not_annual")

    def test_donor_scope_fixed_units_and_corrected_landing(self):
        lookup=self.scope.set_index("gen_row")
        self.assertEqual(len(self.rmn),13)
        self.assertEqual(len(self.stl),15)
        for s in self.receipt["scenarios"]:
            d=self.data[s["name"]];changed=d["gen_rows_1based"]-1;donor=d["donor_generator_rows_1based"]-1
            self.assertEqual(np.intersect1d(changed,self.held).size,0)
            self.assertTrue(np.array_equal(changed,np.unique(np.r_[self.rmn,donor])))
            self.assertTrue(lookup.loc[changed+1,"prime_mover"].eq("HY").all())
            self.assertFalse(lookup.loc[donor+1,"plant_id"].isin([2693,2694]).any())
            if s["donor_policy"]=="outside_ab":
                self.assertFalse(lookup.loc[donor+1,"electrical_landing_zone"].isin(["A","B"]).any())
                self.assertEqual(len(donor),314)
            else:self.assertEqual(len(donor),320)

    def test_native_bounds_and_hourly_hydro_global_balance(self):
        for d in self.data.values():
            q=d["qualified"];rows=d["gen_rows_1based"]-1;v=d["gen_pg_changed"][q]
            self.assertLessEqual(float(np.max(self.bounds["gen_pmin"][q][:,rows]-v)),1e-7)
            self.assertLessEqual(float(np.max(v-self.bounds["gen_pmax"][q][:,rows])),1e-7)
            self.assertLess(float(np.max(abs((v-self.pg[q][:,rows]).sum(axis=1)))),1e-7)
            # Changed rows are all conventional HY; zero sum thus preserves
            # both total native PG and statewide Hydro including fixed PS.
            positions=np.searchsorted(rows,self.rmn)
            self.assertLess(float(np.max(abs(v[:,positions].sum(axis=1)-d["applied_RMN_model_mw"][q]))),1e-7)

    def test_legacy_uses_reported_H_and_fixed_current_StLawrence(self):
        expected=.8*self.H-self.pg[:,self.stl].sum(axis=1)
        for name,d in self.data.items():
            if "legacy" not in name:continue
            self.assertLess(float(np.max(abs(d["requested_RMN_model_mw"][self.mask]-expected[self.mask]))),1e-7)
            self.assertTrue(np.isnan(d["requested_RMN_model_mw"][~self.mask]).all())

    def test_literal_rejection_and_bounded_hypothesis_are_distinct(self):
        for pool in ["outside_ab","all_other"]:
            literal=self.data[f"niagara_legacy_literal_{pool}"];bounded=self.data[f"niagara_legacy_bounded_{pool}"]
            request=literal["requested_RMN_model_mw"];low=literal["feasible_RMN_lower_model_mw"];high=literal["feasible_RMN_upper_model_mw"]
            feasible=self.mask&(request>=low-1e-7)&(request<=high+1e-7)
            self.assertTrue(np.array_equal(literal["qualified"],feasible))
            self.assertEqual(int((self.mask&~feasible).sum()),277)
            self.assertTrue(np.array_equal(bounded["qualified"],self.mask))
            self.assertLess(float(np.max(abs(bounded["applied_RMN_model_mw"][self.mask]-np.clip(request[self.mask],low[self.mask],high[self.mask])))),1e-7)
            self.assertLess(float(np.max(abs(literal["applied_RMN_model_mw"][feasible]-request[feasible]))),1e-7)
            # Every rejected literal request exceeds the independently read
            # original RMN group upper bound; none is discarded by scoring.
            self.assertTrue(np.all(request[self.mask&~feasible]>self.bounds["gen_pmax"][self.mask&~feasible][:,self.rmn].sum(axis=1)))

    def test_physical_month_energy_scope_and_preserved_shape(self):
        counts=pd.Series(self.months).value_counts()
        self.assertEqual(int(counts[3]),743);self.assertEqual(int(counts[11]),721)
        reference=self.pg[:,self.rmn].sum(axis=1)
        for name,d in self.data.items():
            if "month_shape" not in name:continue
            for month in range(1,13):
                ix=self.mask&(self.months==month);n=int(ix.sum())
                mean=float(self.eia.loc[month,"net_generation_mwh"])/int(counts[month])*self.gamma
                expected=reference[ix]/reference[ix].mean()*mean
                self.assertLess(float(np.max(abs(d["requested_RMN_model_mw"][ix]-expected))),1e-7)
                if "constrained" in name:
                    self.assertTrue(d["qualified"][ix].all())
                    self.assertAlmostEqual(float(d["applied_RMN_model_mw"][ix].sum()),mean*n,places=6)

    def test_original_weight_current_baseline_KKT(self):
        for d in self.data.values():
            q=d["qualified"];rows=d["gen_rows_1based"]-1
            for key,dual_key in [("RMN_generator_rows_1based","RMN_projection_dual"),("donor_generator_rows_1based","donor_projection_dual")]:
                group=d[key]-1;position=np.searchsorted(rows,group)
                result=d["gen_pg_changed"][q][:,position]
                expected=np.minimum(np.maximum(self.pg[q][:,group]+d[dual_key][q,None]/self.weights[q][:,group],
                                                self.bounds["gen_pmin"][q][:,group]),self.bounds["gen_pmax"][q][:,group])
                self.assertLess(float(np.max(abs(result-expected))),1e-7)


def write_audit(result):
    c=NiagaraInputChecks;records=[];largest=[]
    for pool in ["outside_ab","all_other"]:
        d=c.data[f"niagara_legacy_bounded_{pool}"];q=d["qualified"];donor=d["donor_generator_rows_1based"]-1
        request=d["requested_RMN_model_mw"];applied=d["applied_RMN_model_mw"];changed=q&(abs(request-applied)>1e-7)
        rlo=c.bounds["gen_pmin"][:,c.rmn].sum(axis=1);rhi=c.bounds["gen_pmax"][:,c.rmn].sum(axis=1)
        total=c.pg[:,c.rmn].sum(axis=1)+c.pg[:,donor].sum(axis=1)
        dlow=total-c.bounds["gen_pmax"][:,donor].sum(axis=1);dhigh=total-c.bounds["gen_pmin"][:,donor].sum(axis=1)
        records.append(dict(donor_policy=pool,adjusted_hours=int(changed.sum()),
            request_above_RMN_capacity_hours=int((changed&(request>rhi+1e-7)).sum()),
            request_below_RMN_minimum_hours=int((changed&(request<rlo-1e-7)).sum()),
            request_above_donor_balance_maximum_hours=int((changed&(request>dhigh+1e-7)).sum()),
            request_below_donor_balance_minimum_hours=int((changed&(request<dlow-1e-7)).sum()),
            RMN_capacity_is_tighter_binding_upper_bound_every_adjusted_hour=bool((rhi[changed]<=dhigh[changed]+1e-7).all())))
        ix=np.flatnonzero(changed);ix=ix[np.argsort(abs(request[ix]-applied[ix]))[::-1][:5]]
        for h in ix:largest.append(dict(donor_policy=pool,hour_index=int(h+1),timestamp_utc=str(d["timestamp_utc"][h]),
            requested_public_mw=float(request[h]/c.gamma),applied_public_mw=float(applied[h]/c.gamma),
            original_RMN_upper_public_mw=float(rhi[h]/c.gamma),donor_balance_maximum_public_mw=float(dhigh[h]/c.gamma),
            hypothesis_reduction_public_mw=float((request[h]-applied[h])/c.gamma)))
    audit=dict(passed=result.wasSuccessful(),created_utc=datetime.now(timezone.utc).isoformat(),
        datasettype="generation_input_validation",tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        source_receipt_sha256=sha(INPUTS/"niagara_receipt.json"),validation_code_sha256=sha(Path(__file__)),
        internal_interface_observations_read=False,power_flow_run=False,
        meaningful_checks=["sealed source/output hashes", "fixed cohort and unavailable rows", "electrical donor landing and held-fixed units", "all-hour bounds and hydro/global conservation", "P63 rather than reconstructed-H legacy target", "literal infeasibility versus explicit bounded hypothesis", "physical DST month means and partial-cohort energy scope", "original-weight current-reference projection KKT"],
        legacy_feasibility_causes=records,largest_adjusted_targets=largest,
        all_old_dependency_hashes_unchanged=all(sha(ROOT/x["path"])==x["sha256"] for x in c.receipt["dependencies"]))
    (INPUTS/"niagara_input_validation.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in audit.items() if k not in {"largest_adjusted_targets","meaningful_checks"}},indent=2))


if __name__=="__main__":
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(NiagaraInputChecks)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if hasattr(NiagaraInputChecks,"data"):write_audit(result)
    raise SystemExit(0 if result.wasSuccessful() else 1)
