"""Focused source-gate adversarial fixtures; frozen sources are read-only.

The fixture rewrites only temporary copies of new Ontario input CSV/receipts.
No dispatch or power-flow build is invoked by these source tests.
"""
from contextlib import contextmanager
from datetime import datetime,timezone
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("western_reconstruct_under_test",HERE/"reconstruct_dispatch.py")
MODULE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PRODUCTION=ROOT/"output/nygrid_2025_western_audit"
EXPECTED_EXCLUSIONS=np.array([1150,1151,1152,1703,1704,5040])


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory(prefix="western-source-review-") as tmp:
        out=Path(tmp);folder=out/"ontario";folder.mkdir()
        for path in (PRODUCTION/"ontario").iterdir():
            if path.is_file() and path.suffix in {".json",".csv"}:
                (folder/path.name).write_bytes(path.read_bytes())
        for name in ["review","corrected"]:
            target=out/name;target.mkdir()
            for path in (PRODUCTION/name).glob("*"):
                if path.is_file() and path.suffix in {".json",".csv"}:
                    (target/path.name).write_bytes(path.read_bytes())
        (folder/"raw").mkdir()
        raw="PUB_IntertieScheduleFlowYear_2025.csv"
        (folder/"raw"/raw).write_bytes((PRODUCTION/"ontario/raw"/raw).read_bytes())
        # Preserve canonical manifest identities while routing editable derived
        # inputs to temporary copies. All hash checks of immutable dependency
        # files still read the real original paths; no large MAT is copied.
        class LogicalFixturePath(type(Path())):
            def relative_to(self,*other,**kwargs):
                p=Path(str(self))
                if p.is_relative_to(out):
                    p=PRODUCTION/p.relative_to(out)
                return p.relative_to(*other,**kwargs)
        source=pd.read_csv(folder/"hourly_actual_exchange.csv")
        times=source.timestamp_utc.to_numpy(str)
        with patch.object(MODULE,"OUT",LogicalFixturePath(out)):
            yield folder,times


def read_json(path):return json.loads(path.read_text())


def write_json(path,value):path.write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8")


def reseal_quality(folder):
    """Make changed child metadata internally consistent, leaving raw proof fixed."""
    receipt=read_json(folder/"source_quality_receipt.json")
    receipt["original_csv_sha256"]=MODULE.sha(folder/"hourly_actual_exchange.csv")
    receipt["actual_input_sha256"]=receipt["original_csv_sha256"]
    receipt["quality_child_sha256"]=MODULE.sha(folder/"hourly_exchange_quality.csv")
    write_json(folder/"source_quality_receipt.json",receipt)
    audit=read_json(folder/"ontario_audit_summary.json")
    audit["actual_input_sha256"]=receipt["original_csv_sha256"]
    audit["source_quality_child_sha256"]=receipt["quality_child_sha256"]
    audit["source_quality_receipt_sha256"]=MODULE.sha(folder/"source_quality_receipt.json")
    write_json(folder/"ontario_audit_summary.json",audit)


class SourceGateTests(unittest.TestCase):
    def reject(self,folder,times):
        with self.assertRaises((ValueError,KeyError,FileNotFoundError,AssertionError)):
            MODULE.source_inputs(times)

    def mutate_audit(self,field,value):
        with fixture() as (folder,times):
            audit=read_json(folder/"ontario_audit_summary.json");audit[field]=value
            write_json(folder/"ontario_audit_summary.json",audit)
            self.reject(folder,times)

    def test_valid_source_gate_preserves_six_exclusions(self):
        with fixture() as (folder,times):
            source,valid,receipt=MODULE.source_inputs(times)
            self.assertEqual(int(valid.sum()),8754)
            np.testing.assert_array_equal(np.flatnonzero(~valid)+1,EXPECTED_EXCLUSIONS)
            self.assertEqual(int((source.actual_ontario_to_ny_mw.eq(0)&valid).sum()),2)

    def test_reject_wrong_direction(self):self.mutate_audit("positive_direction","NewYork_to_Ontario")
    def test_reject_wrong_units(self):self.mutate_audit("actual_units","model_MW")
    def test_reject_wrong_clock(self):self.mutate_audit("source_time_basis","America/New_York_DST_hour_ending")
    def test_reject_wrong_border(self):self.mutate_audit("source_zone","MICHIGAN")
    def test_reject_schedule_as_actual_field(self):self.mutate_audit("source_actual_field","Exp")
    def test_reject_internal_fit(self):self.mutate_audit("source_sign_or_timing_fitted_to_internal_flows",True)
    def test_reject_wrong_year(self):self.mutate_audit("year",2019)
    def test_reject_unqualified_source_status(self):self.mutate_audit("status","incomplete_unverified")

    def test_reject_empty_manifest(self):
        with fixture() as (folder,times):
            pd.DataFrame(columns=["path","url","sha256"]).to_csv(folder/"source_manifest.csv",index=False)
            self.reject(folder,times)

    def test_reject_incomplete_manifest(self):
        with fixture() as (folder,times):
            table=pd.read_csv(folder/"source_manifest.csv")
            table.iloc[:1].to_csv(folder/"source_manifest.csv",index=False)
            self.reject(folder,times)

    def test_reject_dropped_annual_raw_proof(self):
        with fixture() as (folder,times):
            table=pd.read_csv(folder/"source_manifest.csv")
            table=table.loc[~table.path.str.contains("Year_2025",regex=False)]
            table.to_csv(folder/"source_manifest.csv",index=False)
            self.reject(folder,times)

    def test_reject_changed_source_hash(self):
        with fixture() as (folder,times):
            table=pd.read_csv(folder/"source_manifest.csv");table.loc[0,"sha256"]="0"*64
            table.to_csv(folder/"source_manifest.csv",index=False)
            self.reject(folder,times)

    def test_reject_duplicate_manifest(self):
        with fixture() as (folder,times):
            table=pd.read_csv(folder/"source_manifest.csv")
            pd.concat([table,table.iloc[:1]]).to_csv(folder/"source_manifest.csv",index=False)
            self.reject(folder,times)

    def test_reject_dropped_frozen_dependencies(self):
        with fixture() as (folder,times):
            audit=read_json(folder/"ontario_audit_summary.json")
            audit["frozen_inputs"]=audit["frozen_inputs"][:1]
            write_json(folder/"ontario_audit_summary.json",audit)
            self.reject(folder,times)

    def test_reject_missing_quality_receipt(self):
        with fixture() as (folder,times):
            (folder/"source_quality_receipt.json").unlink()
            self.reject(folder,times)

    def test_reject_dropped_DOE_sign_proof(self):
        with fixture() as (folder,times):
            path=folder.parent/"review/pre_promotion_review.json";review=read_json(path)
            rows=review["source_review"]["dependencies"]
            review["source_review"]["dependencies"]=[r for r in rows if not r["path"].endswith("DOE2025_intertie_sign_source.pdf")]
            write_json(path,review);self.reject(folder,times)

    def test_reject_unqualified_independent_review(self):
        with fixture() as (folder,times):
            path=folder.parent/"review/pre_promotion_review.json";review=read_json(path)
            review["status"]="unqualified";write_json(path,review);self.reject(folder,times)

    def test_reject_changed_independent_proof_hash(self):
        with fixture() as (folder,times):
            path=folder.parent/"review/pre_promotion_review.json";review=read_json(path)
            rows=review["source_review"]["dependencies"]
            next(r for r in rows if r["path"].endswith("DOE2025_intertie_sign_source.pdf"))["sha256"]="0"*64
            write_json(path,review);self.reject(folder,times)

    def test_reject_dropped_quality_raw_proof(self):
        with fixture() as (folder,times):
            r=read_json(folder/"source_quality_receipt.json");r["raw_sources"]=r["raw_sources"][:1]
            write_json(folder/"source_quality_receipt.json",r);reseal_quality(folder)
            self.reject(folder,times)

    def test_reject_quality_chosen_from_internal_residuals(self):
        with fixture() as (folder,times):
            r=read_json(folder/"source_quality_receipt.json");r["quality_predicate_fitted_to_internal_flows"]=True
            write_json(folder/"source_quality_receipt.json",r);reseal_quality(folder)
            self.reject(folder,times)

    def test_reject_omission_of_all_six_suspect_hours(self):
        with fixture() as (folder,times):
            q=pd.read_csv(folder/"hourly_exchange_quality.csv")
            q["source_quality_qualified"]=True;q["all_intertie_actual_zero"]=False
            q.to_csv(folder/"hourly_exchange_quality.csv",index=False)
            r=read_json(folder/"source_quality_receipt.json");r["suspect_count"]=0;r["excluded_hour_indices"]=[]
            write_json(folder/"source_quality_receipt.json",r);reseal_quality(folder)
            self.reject(folder,times)

    def test_reject_excluding_ordinary_NY_zero_hours(self):
        with fixture() as (folder,times):
            s=pd.read_csv(folder/"hourly_actual_exchange.csv");q=pd.read_csv(folder/"hourly_exchange_quality.csv")
            zero=s.actual_ontario_to_ny_mw.eq(0)
            q["all_intertie_actual_zero"]=zero;q["source_quality_qualified"]=~zero
            q.to_csv(folder/"hourly_exchange_quality.csv",index=False)
            r=read_json(folder/"source_quality_receipt.json");r["suspect_count"]=int(zero.sum());r["excluded_hour_indices"]=(np.flatnonzero(zero)+1).tolist()
            write_json(folder/"source_quality_receipt.json",r);reseal_quality(folder)
            self.reject(folder,times)

    def mutate_values(self,transform):
        with fixture() as (folder,times):
            s=pd.read_csv(folder/"hourly_actual_exchange.csv")
            s["actual_ontario_to_ny_mw"]=transform(s.actual_ontario_to_ny_mw.to_numpy(float))
            s["actual_minus_original_schedule_mw"]=s.actual_ontario_to_ny_mw-s.original_nyiso_schedule_mw
            s.to_csv(folder/"hourly_actual_exchange.csv",index=False)
            reseal_quality(folder)
            self.reject(folder,times)

    def test_reject_wrong_actual_scale_even_with_resealed_child(self):self.mutate_values(lambda v:v*1.25)
    def test_reject_wrong_actual_sign_even_with_resealed_child(self):self.mutate_values(lambda v:-v)
    def test_reject_shifted_actual_values_with_unchanged_time_labels(self):self.mutate_values(lambda v:np.roll(v,1))

    def test_reject_UTC_axis_offset(self):
        with fixture() as (folder,times):
            changed=pd.DatetimeIndex(pd.to_datetime(times,utc=True))+pd.Timedelta(hours=1)
            self.reject(folder,changed.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy())


def numerical_fixture():
    h=np.arange(1,4);ids=np.array([11,12]);times=np.array(["2025-01-01T05:00:00Z","2025-01-01T06:00:00Z","2025-01-01T07:00:00Z"])
    data=dict(hour_index=h,native_fleet_ids=ids,timestamp_utc=times,gamma=.25,gen_pg=np.ones((3,10)),dispatch_qualified=np.ones(3,bool))
    bounds=dict(hour_index=h.copy(),native_fleet_ids=ids.copy(),gen_pmin=np.zeros((3,10)),gen_pmax=np.full((3,10),10.))
    priors=dict(hour_index=h.copy(),native_fleet_ids=ids.copy(),prior_pg=np.ones((3,10)),objective_weights=np.ones((3,2)))
    register=pd.DataFrame(dict(gen_row=np.arange(1,11),fleet_id=[11,12]+[0]*8,role=["native"]*2+["fixed_external"]*8))
    public=np.array([[1.,2.],[3.,4.],[5.,6.]])
    par=dict(hour_index=h.copy(),timestamp_utc=times.copy(),gamma=.25,observed_direction_verified=True,direction_ontario_to_NY_multiplier=np.array([1,1]),observed_public_mw=public,observed_model_mw=public*.25)
    allocation=pd.DataFrame(dict(region=["ONTARIO"]*6,generator_row=np.arange(101,107),generation_share=np.ones(6)/6))
    return data,bounds,priors,register,par,allocation


class DispatchSourceGateTests(unittest.TestCase):
    def test_valid_small_array_fixture(self):MODULE.verify_dispatch_sources(*numerical_fixture())

    def reject_change(self,change):
        values=numerical_fixture();change(*values)
        with self.assertRaises((ValueError,KeyError,AssertionError)):MODULE.verify_dispatch_sources(*values)

    def test_reject_wrong_gamma(self):
        for value in [0,-1,np.nan,.5]:
            with self.subTest(gamma=value):self.reject_change(lambda d,b,p,r,c,a:d.update(gamma=value))

    def test_reject_wrong_PAR_scale(self):self.reject_change(lambda d,b,p,r,c,a:c.update(observed_model_mw=c["observed_model_mw"]*2))
    def test_reject_unverified_PAR_sign(self):self.reject_change(lambda d,b,p,r,c,a:c.update(observed_direction_verified=False))
    def test_reject_reversed_PAR_sign(self):self.reject_change(lambda d,b,p,r,c,a:c.update(direction_ontario_to_NY_multiplier=np.array([-1,1])))
    def test_reject_PAR_clock(self):self.reject_change(lambda d,b,p,r,c,a:c.update(timestamp_utc=np.roll(c["timestamp_utc"],1)))
    def test_reject_bound_hour_axis(self):self.reject_change(lambda d,b,p,r,c,a:b.update(hour_index=np.array([2,1,3])))
    def test_reject_prior_fleet_axis(self):self.reject_change(lambda d,b,p,r,c,a:p.update(native_fleet_ids=np.array([12,11])))
    def test_reject_model_fleet_axis(self):self.reject_change(lambda d,b,p,r,c,a:r.loc.__setitem__((0,"fleet_id"),13))
    def test_reject_nonpositive_weight(self):self.reject_change(lambda d,b,p,r,c,a:p["objective_weights"].__setitem__((0,0),0))
    def test_reject_nonfinite_P0(self):self.reject_change(lambda d,b,p,r,c,a:p["prior_pg"].__setitem__((0,0),np.nan))
    def test_reject_reversed_bounds(self):self.reject_change(lambda d,b,p,r,c,a:b["gen_pmax"].__setitem__((0,0),-1))
    def test_reject_duplicate_Ontario_row(self):self.reject_change(lambda d,b,p,r,c,a:a.loc.__setitem__((0,"generator_row"),102))
    def test_reject_bad_Ontario_share_sum(self):self.reject_change(lambda d,b,p,r,c,a:a.loc.__setitem__((0,"generation_share"),.2))
    def test_reject_negative_Ontario_share(self):
        def change(d,b,p,r,c,a):a.loc[0,"generation_share"]=-.1;a.loc[1,"generation_share"]+=1/6+.1
        self.reject_change(change)


class FrozenDependencyGateTests(unittest.TestCase):
    def test_valid_frozen_delivery_manifests(self):MODULE.verify_frozen_dependencies()

    def mutate_manifest(self,relative,mutator):
        path=ROOT/relative;content=json.loads(path.read_text());key="entries" if "entries" in content else "files"
        content[key]=mutator(content[key]);original=Path.read_text
        def fake_read(p,*args,**kwargs):return json.dumps(content) if p==path else original(p,*args,**kwargs)
        with patch.object(Path,"read_text",fake_read):
            with self.assertRaises((ValueError,KeyError,AssertionError)):MODULE.verify_frozen_dependencies()

    def test_reject_dropped_numeric_bound_proof(self):
        self.mutate_manifest("output/nygrid_2025_dispatch/delivery_manifest.json",lambda r:[x for x in r if not x["path"].endswith("dispatch_bounds.mat")])

    def test_reject_changed_prior_hash(self):
        def change(rows):
            for r in rows:
                if r["path"].endswith("dispatch_priors.mat"):r["sha256"]="0"*64
            return rows
        self.mutate_manifest("output/nygrid_2025_dispatch/delivery_manifest.json",change)

    def test_reject_dropped_Ontario_allocation_proof(self):
        self.mutate_manifest("output/nygrid_2025_inputs/delivery_manifest.json",lambda r:[x for x in r if not x["path"].endswith("external_generator_allocation.csv")])

    def test_reject_changed_solver_code_hash(self):
        def change(rows):
            for r in rows:
                if r["path"].endswith("build_dispatch.py"):r["sha256"]="0"*64
            return rows
        self.mutate_manifest("output/nygrid_2025_dispatch/delivery_manifest.json",change)


class SavedAccountingTests(unittest.TestCase):
    """Read-only checks against the separately generated reconstruction."""
    @classmethod
    def setUpClass(cls):
        base=ROOT/"output/nygrid_2025_dispatch/dispatch"
        cls.old=loadmat(base/"dispatch.mat",simplify_cells=True)
        cls.new=loadmat(PRODUCTION/"dispatch/actual_Ontario_dispatch.mat",simplify_cells=True)
        cls.bounds=loadmat(base/"dispatch_bounds.mat",simplify_cells=True)
        cls.priors=loadmat(base/"dispatch_priors.mat",simplify_cells=True)
        cls.register=pd.read_csv(ROOT/"output/nygrid_2025_moses_audit/corrected/model_generator_register.csv")
        a=pd.read_csv(ROOT/"output/nygrid_2025_inputs/model/external_generator_allocation.csv")
        cls.ont=a.loc[a.region=="ONTARIO"]
        cls.native=np.flatnonzero(cls.register.role.eq("native"))
        cls.ext=np.flatnonzero(cls.register.role.eq("fixed_external"))
        cls.cols=cls.register.loc[cls.register.parent_gen_row.isin(cls.ont.generator_row)].gen_row.to_numpy(int)-1
        cls.q=np.asarray(cls.new["qualified"],bool)
        cls.ix=np.flatnonzero(cls.q)
        cls.delta=pd.read_csv(PRODUCTION/"ontario/hourly_actual_exchange.csv").actual_minus_original_schedule_mw.to_numpy()
        cls.gamma=float(cls.old["gamma"])

    def test_accounting_same_source_screened_cohort(self):
        quality=pd.read_csv(PRODUCTION/"ontario/hourly_exchange_quality.csv").source_quality_qualified.to_numpy(bool)
        with np.load(ROOT/"output/nygrid_2025_par_controls/controls/inputs.npz",allow_pickle=False) as par:
            expected=np.asarray(self.old["dispatch_qualified"],bool)&quality&np.asarray(par["observed_replay_qualified"],bool)
            self.assertEqual(float(par["gamma"]),self.gamma)
        np.testing.assert_array_equal(self.q,expected)
        self.assertEqual(int(self.q.sum()),8657)
        self.assertFalse(self.q[EXPECTED_EXCLUSIONS-1].any())

    def test_accounting_only_six_Ontario_equivalents_changed(self):
        np.testing.assert_array_equal(self.new["ontario_generator_rows_1based"],self.cols+1)
        np.testing.assert_allclose(self.new["ontario_generator_shares"],self.ont.generation_share,rtol=0,atol=1e-15)
        actual=self.new["gen_pg"][np.ix_(self.ix,self.cols)]-self.old["gen_pg"][np.ix_(self.ix,self.cols)]
        expected=self.gamma*self.delta[self.q,None]*self.ont.generation_share.to_numpy()[None,:]
        np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-9)
        others=np.setdiff1d(self.ext,self.cols)
        np.testing.assert_array_equal(self.new["gen_pg"][np.ix_(self.ix,others)],self.old["gen_pg"][np.ix_(self.ix,others)])

    def test_accounting_new_native_target_and_global_balance(self):
        expected=self.old["native_required_pg"][self.q]-self.gamma*self.delta[self.q]
        np.testing.assert_allclose(self.new["native_required_pg"][self.q],expected,rtol=0,atol=1e-7)
        pg=self.new["gen_pg"][self.q]
        np.testing.assert_allclose(pg[:,self.native].sum(axis=1),expected,rtol=0,atol=1e-7)
        demand=self.old["bus_pd"][self.q].sum(axis=1)+self.old["base_case"]["bus"][:,4].sum()
        np.testing.assert_allclose(pg.sum(axis=1),demand,rtol=0,atol=1e-7)

    def test_accounting_original_prior_weight_bounds_KKT(self):
        p=self.new["gen_pg"][np.ix_(self.ix,self.native)]
        p0=self.priors["prior_pg"][np.ix_(self.ix,self.native)]
        lo=self.bounds["gen_pmin"][np.ix_(self.ix,self.native)]
        hi=self.bounds["gen_pmax"][np.ix_(self.ix,self.native)]
        w=self.priors["objective_weights"][self.q]
        dual=self.new["dual_lambda"][self.q]
        expected=np.minimum(hi,np.maximum(lo,p0+dual[:,None]/w))
        np.testing.assert_allclose(p,expected,rtol=0,atol=1e-8)
        self.assertTrue((w>0).all())
        self.assertLessEqual(float(np.max(lo-p)),1e-8)
        self.assertLessEqual(float(np.max(p-hi)),1e-8)
        objective=.5*np.sum(w*(p-p0)**2,axis=1)
        np.testing.assert_allclose(self.new["objective_value"][self.q],objective,rtol=1e-13,atol=1e-8)

    def test_accounting_invalid_hours_are_not_promoted(self):
        self.assertTrue(np.isnan(self.new["gen_pg"][~self.q]).all())
        self.assertTrue(np.isnan(self.new["dual_lambda"][~self.q]).all())
        self.assertFalse((self.new["status_code"]==2).any())


def write_review_receipt():
    receipt_path=PRODUCTION/"dispatch/dispatch_receipt.json"
    dispatch_receipt=read_json(receipt_path)
    paths=[HERE/"test_western_sources.py",HERE/"reconstruct_dispatch.py",receipt_path,
        PRODUCTION/"dispatch/actual_Ontario_dispatch.mat",PRODUCTION/"review/pre_promotion_review.json"]
    paths += [ROOT/r["path"]for r in dispatch_receipt["dependencies"]]
    paths += [PRODUCTION/"ontario"/name for name in ["source_manifest.csv","source_quality_receipt.json","hourly_actual_exchange.csv","hourly_exchange_quality.csv"]]
    paths=list(dict.fromkeys(paths))
    before={p.relative_to(ROOT).as_posix():MODULE.sha(p)for p in paths}
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    unchanged=all(MODULE.sha(ROOT/p)==h for p,h in before.items())
    code="scripts/nygrid_2025_western_audit/reconstruct_dispatch.py"
    matches=next(r["sha256"]for r in dispatch_receipt["dependencies"]if r["path"]==code)==before[code]
    output=dict(status="passed"if result.wasSuccessful() and unchanged and matches else "requires_attention",
        created_utc=datetime.now(timezone.utc).isoformat(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        source_gate_and_saved_accounting_passed=result.wasSuccessful(),saved_dispatch_generated_by_current_code=matches,
        all_recorded_inputs_and_code_unchanged=unchanged,no_frozen_source_writes_or_solver_builds=True,
        test_output=stream.getvalue(),failure_tests=[t.id()for t,_ in result.failures],error_tests=[t.id()for t,_ in result.errors],
        dependencies=[dict(path=p,sha256=h)for p,h in before.items()])
    destination=PRODUCTION/"validation/source_gate_review.json";destination.parent.mkdir(exist_ok=True)
    write_json(destination,output)
    print(json.dumps({k:output[k]for k in ["status","tests","failures","errors","saved_dispatch_generated_by_current_code","all_recorded_inputs_and_code_unchanged"]},indent=2))
    return output["status"]=="passed"


if __name__=="__main__":
    if "--write-review-receipt" in sys.argv:
        raise SystemExit(0 if write_review_receipt() else 1)
    unittest.main(verbosity=2)
