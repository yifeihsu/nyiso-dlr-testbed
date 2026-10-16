"""Source-only, hydro-balanced Niagara allocation counterfactual inputs.

No interface observations, prior scoring results, or power-flow solver are read.
The frozen all-boundary dispatch is the reference. Only Robert Moses Niagara
and an explicitly enumerated conventional-hydro donor pool may change. Load,
external generation, St Lawrence and every pumped-storage output remain fixed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
from scipy.io import loadmat

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_western_counterfactuals"
INPUTS = OUT / "inputs"
WEST = ROOT / "output/nygrid_2025_western_audit"
BASE = WEST / "dispatch/all_boundary_actual_dispatch.mat"
MASK = WEST / "replay/paired_common_mask.npy"
BOUNDS = ROOT / "output/nygrid_2025_dispatch/dispatch/dispatch_bounds.mat"
WEIGHTS = ROOT / "output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat"
REGISTER = WEST / "corrected/model_generator_register.csv"
FLEET = WEST / "corrected/fleet_register.csv"
BUS_META = ROOT / "output/nygrid_2025_dispatch/fleet/source_parent/npcc.csv"
HOURS = ROOT / "output/nygrid_2025_inputs/load_source/hour_catalog.csv"
P63 = ROOT / "output/nygrid_2025_inputs/generation_source/statewide_fuelmix_hourly.csv"
EIA = WEST / "generation/target_EIA923_final_monthly.csv"
EIA_RECEIPT = WEST / "generation/sources/f923_2025_final.receipt.json"
REPORT = ROOT / "NYGRID_2025_WESTERN_SOURCE_AUDIT.md"
PROJECTION_CODE = ROOT / "scripts/nygrid_2025_dispatch/build_dispatch.py"
TOL = 1e-7
POOLS = ["outside_ab", "all_other"]
MODES = ["legacy_literal", "legacy_bounded", "month_shape_literal", "month_shape_constrained"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def rel(path):
    return Path(path).relative_to(ROOT).as_posix()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def csv_write(frame, name):
    path = INPUTS/name
    if name.endswith(".gz"):
        frame.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%SZ", lineterminator="\n",
                     compression={"method":"gzip", "mtime":0})
    else:
        frame.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%SZ", lineterminator="\n")


def plan():
    return dict(schema_version=1, experiment="source_only_Niagara_hydro_redistribution", year=2025,
        baseline_git_revision="8290ced50354c81eb572a87f0f90eb87278c3cfe",
        baseline_dispatch=dict(path=rel(BASE), sha256=sha(BASE)),
        fixed_experiment_mask=dict(path=rel(MASK), sha256=sha(MASK), expected_hours=8651),
        target_plant_id=2693, fixed_StLawrence_plant_id=2694, fixed_Lewiston_plant_id=2692,
        held_fixed=["all 28 external equivalents", "PD and QD", "all six original DC/P34 transfers", "St Lawrence unit PG", "every PS/Lewiston unit PG", "all non-HY unit PG", "generator terminals and topology"],
        donor_policies={
            "outside_ab":"Admitted conventional HY with frozen corrected generator landing outside electrical zones A and B; exclude2693/2694 and all PS.",
            "all_other":"All other admitted conventional HY; exclude2693/2694 and all PS. Balancing-location sensitivity, not the preferred western-cut isolation."},
        target_policies={
            "legacy_literal":"RMN = 0.8 * public P63 Hydro - fixed current StLawrence PG. Literal requested target; infeasible hours unavailable. This is a partial legacy-share recipe, not a complete 2019-method swap.",
            "legacy_bounded":"Project the legacy hypothesis target into the hourly jointly feasible RMN interval. Record requested/applied differences; source observations are never rewritten.",
            "month_shape_literal":"EIA2693 full-month net MWh / physical local-calendar month hours, times baselineRMN/mean(baselineRMN on the fixed eligible month cohort). Reject infeasible hourly requests.",
            "month_shape_constrained":"Nearest unweighted hourly vector to that same monthly-shaped request, subject to joint hourly RMN intervals and exact cohort sum = source monthly mean * fixed eligible hours. An infeasible monthly sum rejects the whole affected cohort month."},
        balancing_objective="For each feasible hourly RMN and donor aggregate, minimize0.5*sum(original objective_weight*(unitPG-current baselinePG)^2) within original native unit bounds.",
        conserved_total="Current baseline hourly statewide Hydro PG, including fixed PS; the P63 Hydro source is separately exposed and is not substituted for this preserved total.",
        monthly_scope="America/New_York physical calendar hours (March743, November721). Source EIA monthly energy is rescaled to the fixed eligible-hour count by a representative-missing-hours assumption. No full-month or full-year energy claim for incomplete cohorts.",
        fixed_cohort_policy="Main comparisons require all8651fixedhours. Literal/infeasible variants remain restricted diagnostics; no error-based hour selection or silent filling.",
        scenarios=[f"niagara_{mode}_{pool}" for pool in POOLS for mode in MODES],
        internal_interface_observations_read=False, power_flow_run=False,
        output_contract=dict(layout="compact_changed_generator_rows", fields=["gen_rows_1based", "gen_pg_changed", "qualified", "requested_RMN_model_mw", "applied_RMN_model_mw", "hour_index", "timestamp_utc", "gamma"],
                             reconstruction="Load the hash-bound all-boundary baseline, overwrite gen_rows_1based with gen_pg_changed, and set every PG row outside qualified to NaN."))


def write_plan():
    OUT.mkdir(parents=True, exist_ok=True); INPUTS.mkdir(parents=True, exist_ok=True)
    expected=plan(); path=OUT/"niagara_plan.json"
    if path.exists():
        existing=json.loads(path.read_text())
        existing.pop("preregistered_utc", None)
        require(existing==expected, "Existing Niagara plan differs; do not silently revise the experiment")
    else:
        expected["preregistered_utc"]=utc_now()
        path.write_text(json.dumps(expected, indent=2)+"\n", encoding="utf-8")
    return path


def load_projection():
    spec=importlib.util.spec_from_file_location("frozen_niagara_projection", PROJECTION_CODE)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.bounded_projection


def projected_groups(project, pg, lo, hi, weights, rows, target, q):
    result=np.full((8760, len(rows)), np.nan); dual=np.full(8760, np.nan)
    ix=np.flatnonzero(q)
    if len(ix):
        values, lam, feasible=project(pg[np.ix_(ix,rows)], lo[np.ix_(ix,rows)], hi[np.ix_(ix,rows)],
                                     target[ix], weights[np.ix_(ix,rows)])
        require(feasible.all(), "Prequalified aggregate unexpectedly infeasible at unit level")
        result[ix]=values; dual[ix]=lam
        kkt=np.clip(pg[np.ix_(ix,rows)]+lam[:,None]/weights[np.ix_(ix,rows)], lo[np.ix_(ix,rows)], hi[np.ix_(ix,rows)])
        require(np.max(abs(kkt-values))<TOL, "Projected group does not satisfy original-weight KKT condition")
    return result, dual


def main():
    started=utc_now(); plan_path=write_plan()
    paths=[BASE, MASK, BOUNDS, WEIGHTS, REGISTER, FLEET, BUS_META, HOURS, P63, EIA, EIA_RECEIPT,
           WEST/"dispatch/all_boundary_dispatch_receipt.json", WEST/"generation/generation_audit.json",
           WEST/"generation/source_manifest.csv", ROOT/"output/nygrid_2025_par_controls/controls/inputs.npz",
           REPORT, PROJECTION_CODE]
    proof=json.loads(EIA_RECEIPT.read_text())
    paths.append(ROOT/proof["workbook"])
    require(sha(ROOT/proof["workbook"])==proof["workbook_sha256"], "Final EIA923 workbook changed")
    frozen={rel(p):sha(p) for p in paths}
    baseline_receipt=json.loads((WEST/"dispatch/all_boundary_dispatch_receipt.json").read_text())
    require(baseline_receipt["passed"] and baseline_receipt["dispatch_file_sha256"]==sha(BASE), "Baseline is not the sealed all-boundary dispatch")
    require(json.loads((WEST/"generation/generation_audit.json").read_text())["passed"], "Generation source audit has not passed")
    base=loadmat(BASE, simplify_cells=True, variable_names=["hour_index", "timestamp_utc", "gen_pg", "qualified", "gamma", "native_generator_rows_1based", "external_generator_rows_1based"])
    bounds=loadmat(BOUNDS, simplify_cells=True, variable_names=["hour_index", "gen_pmin", "gen_pmax", "native_fleet_ids"])
    priors=loadmat(WEIGHTS, simplify_cells=True, variable_names=["hour_index", "objective_weights", "native_fleet_ids"])
    pg=np.asarray(base["gen_pg"],float); gamma=float(base["gamma"])
    lo,hi=np.asarray(bounds["gen_pmin"],float),np.asarray(bounds["gen_pmax"],float)
    weights=np.asarray(priors["objective_weights"],float)
    mask=np.load(MASK,allow_pickle=False)
    require(mask.dtype==bool and mask.shape==(8760,) and mask.sum()==8651, "Fixed experiment cohort changed")
    require(np.asarray(base["qualified"],bool)[mask].all(), "Experiment includes unavailable baseline hour")
    require(pg.shape==lo.shape==hi.shape==(8760,1464) and weights.shape==(8760,1436), "Generator or weight axis changed")
    require(np.array_equal(base["hour_index"],np.arange(1,8761)) and np.array_equal(bounds["hour_index"],base["hour_index"])
            and np.array_equal(priors["hour_index"],base["hour_index"]), "Physical-hour axes differ")
    require(np.array_equal(base["native_generator_rows_1based"],np.arange(1,1437))
            and np.array_equal(base["external_generator_rows_1based"],np.arange(1437,1465)), "Native/external identities changed")
    require(np.isfinite(pg[mask]).all() and np.isfinite(weights[mask]).all() and (weights[mask]>0).all(), "Baseline or weights nonfinite")
    require(np.max(lo[mask,:1436]-pg[mask,:1436])<TOL and np.max(pg[mask,:1436]-hi[mask,:1436])<TOL, "Baseline exceeds original native bounds")
    register=pd.read_csv(REGISTER,keep_default_na=False)
    fleet=pd.read_csv(FLEET,keep_default_na=False)
    require(register.device_key.is_unique and np.array_equal(register.gen_row,np.arange(1,1465)), "Generator identities not unique/ordered")
    joined=register.merge(fleet[["device_key","prime_mover","plant_name","is_pumped_hydro"]],on="device_key",how="left",validate="one_to_one")
    bus=pd.read_csv(BUS_META,keep_default_na=False).set_index("idx")
    joined["electrical_landing_zone"]=joined.bus_id.map(bus.zone)
    plant=pd.to_numeric(joined.plant_id,errors="coerce").to_numpy()
    native=joined.role.eq("native").to_numpy()
    hydro=native & joined.fuel_category.eq("Hydro").to_numpy()
    conventional=hydro & joined.prime_mover.eq("HY").to_numpy()
    rmn=np.flatnonzero(conventional & (plant==2693)); stl=np.flatnonzero(conventional & (plant==2694))
    ps=np.flatnonzero(hydro & joined.prime_mover.eq("PS").to_numpy())
    all_donors=np.flatnonzero(conventional & ~np.isin(plant,[2693,2694]))
    outside_donors=all_donors[~joined.iloc[all_donors].electrical_landing_zone.isin(["A","B"]).to_numpy()]
    require(len(rmn)==13 and len(stl)==15 and len(ps)==15 and len(all_donors)==320, "Declared hydro unit set changed")
    require(joined.iloc[rmn].bus_id.eq(55).all() and joined.iloc[rmn].electrical_landing_zone.eq("A").all(), "RMN project landing differs")
    require(joined.iloc[outside_donors].electrical_landing_zone.isin(list("CDEFGHIJK")).all(), "Donor landing not identified outside A/B")
    donors={"outside_ab":outside_donors,"all_other":all_donors}
    ids=joined.loc[conventional|np.isin(np.arange(1464),ps),["gen_row","device_key","plant_id","plant_name","prime_mover","bus_id","zone","electrical_landing_zone"]].copy()
    ids["RMN_target"]=ids.gen_row.isin(rmn+1);ids["fixed_StLawrence"]=ids.gen_row.isin(stl+1)
    ids["fixed_PS"]=ids.gen_row.isin(ps+1);ids["outside_ab_donor"]=ids.gen_row.isin(outside_donors+1);ids["all_other_donor"]=ids.gen_row.isin(all_donors+1)
    csv_write(ids,"niagara_generator_scope.csv")
    hours=pd.read_csv(HOURS,usecols=["hour_index","timestamp_utc"])
    require(np.array_equal(hours.timestamp_utc.astype(str),np.asarray(base["timestamp_utc"]).astype(str)), "Canonical UTC axis differs")
    times=pd.to_datetime(hours.timestamp_utc,utc=True); local=times.dt.tz_convert("America/New_York"); months=local.dt.month.to_numpy()
    physical_counts=pd.Series(months).value_counts().sort_index()
    require(physical_counts.loc[3]==743 and physical_counts.loc[11]==721 and physical_counts.sum()==8760, "Physical DST month-hour counts differ")
    p63=pd.read_csv(P63,usecols=["hour_index","timestamp_utc","fuel_category","generation_mw","coverage_qualified"])
    p63=p63.loc[p63.fuel_category.eq("Hydro")].sort_values("hour_index")
    require(np.array_equal(p63.hour_index,base["hour_index"]) and np.array_equal(p63.timestamp_utc,hours.timestamp_utc), "P63 Hydro hour axis differs")
    H=p63.generation_mw.to_numpy(float)*gamma
    require(np.isfinite(H[mask]).all() and p63.coverage_qualified.astype(bool).to_numpy()[mask].all(), "Fixed cohort contains missing P63 Hydro source")
    E=pd.read_csv(EIA)
    E=E.loc[E.plant_id.eq(2693)&E.prime_mover.eq("HY")&E.sheet.eq("Page 1 Generation and Fuel Data")].sort_values("month")
    require(np.array_equal(E.month,np.arange(1,13)) and E.respondent_frequency.eq("M").all(), "Monthly EIA RMN target identity/observation differs")
    r0=pg[:,rmn].sum(axis=1); s0=pg[:,stl].sum(axis=1); hyd0=pg[:,hydro].sum(axis=1)
    legacy=np.full(8760,np.nan);legacy[mask]=.8*H[mask]-s0[mask]
    shaped=np.full(8760,np.nan);month_rows=[]
    for month in range(1,13):
        selected=mask&(months==month);n=int(selected.sum());physical_n=int(physical_counts.loc[month]);energy=float(E.loc[E.month.eq(month),"net_generation_mwh"].iloc[0])
        require(n>0 and energy>=0 and np.mean(r0[selected])>0, "Monthly shape reference/target invalid")
        desired_mean=energy/physical_n*gamma
        shaped[selected]=r0[selected]/np.mean(r0[selected])*desired_mean
        require(abs(shaped[selected].sum()-desired_mean*n)<1e-6, "Requested monthly shape did not preserve its declared cohort mean")
        month_rows.append(dict(month=month,physical_calendar_hours=physical_n,fixed_cohort_hours=n,missing_from_fixed_cohort=physical_n-n,
                               EIA_full_month_net_mwh=energy,source_calendar_mean_public_mw=energy/physical_n,
                               assumed_cohort_energy_target_public_mwh=energy*n/physical_n,
                               baseline_RMN_cohort_mean_public_mw=float(r0[selected].mean()/gamma),
                               complete_month_energy_claim=False))
    project=load_projection();scenario_rows=[];hourly_rows=[];monthly_rows=[];identity_errors=[]
    for pool, donor in donors.items():
        donor0=pg[:,donor].sum(axis=1);combined0=r0+donor0
        lower=np.full(8760,np.nan);upper=lower.copy()
        lower[mask]=np.maximum(lo[mask][:,rmn].sum(axis=1),combined0[mask]-hi[mask][:,donor].sum(axis=1))
        upper[mask]=np.minimum(hi[mask][:,rmn].sum(axis=1),combined0[mask]-lo[mask][:,donor].sum(axis=1))
        require(np.all(lower[mask]<=r0[mask]+TOL) and np.all(upper[mask]>=r0[mask]-TOL), "Baseline not inside joint feasible RMN interval")
        identity,_=projected_groups(project,pg,lo,hi,weights,donor,donor0,mask)
        identity_errors.append(float(np.max(abs(identity[mask]-pg[mask][:,donor]))))
        changed=np.sort(np.r_[rmn,donor]);rmn_position=np.searchsorted(changed,rmn);donor_position=np.searchsorted(changed,donor)
        for mode in MODES:
            name=f"niagara_{mode}_{pool}";requested=legacy.copy() if mode.startswith("legacy") else shaped.copy()
            applied=np.full(8760,np.nan);q=mask.copy();month_constraints=[]
            requested_feasible=mask & (requested>=lower-TOL) & (requested<=upper+TOL)
            if mode.endswith("literal"):
                q=requested_feasible;applied[q]=requested[q]
            elif mode=="legacy_bounded":
                applied[mask]=np.clip(requested[mask],lower[mask],upper[mask])
            elif mode=="month_shape_constrained":
                for month in range(1,13):
                    ix=np.flatnonzero(mask&(months==month));energy=requested[ix].sum()
                    values,dual,ok=project(requested[ix][None,:],lower[ix][None,:],upper[ix][None,:],np.array([energy]),np.ones((1,len(ix))))
                    accepted=bool(ok[0]);q[ix]=accepted
                    if accepted:applied[ix]=values[0]
                    month_constraints.append(dict(month=month,feasible=accepted,requested_cohort_energy_model_mwh=float(energy),
                        lower_feasible_cohort_energy_model_mwh=float(lower[ix].sum()),upper_feasible_cohort_energy_model_mwh=float(upper[ix].sum())))
            else:raise ValueError("Unknown preregistered variant")
            r_values,r_dual=projected_groups(project,pg,lo,hi,weights,rmn,applied,q)
            donor_target=np.full(8760,np.nan);donor_target[q]=combined0[q]-applied[q]
            d_values,d_dual=projected_groups(project,pg,lo,hi,weights,donor,donor_target,q)
            values=np.full((8760,len(changed)),np.nan);values[:,rmn_position]=r_values;values[:,donor_position]=d_values
            require(q.sum()>0, f"Variant has no feasible hours: {name}")
            require(np.isfinite(values[q]).all() and np.isnan(values[~q]).all(), "Missing-hour or finite-value policy failed")
            bound_error=float(max(0,np.max(lo[q][:,changed]-values[q]),np.max(values[q]-hi[q][:,changed])))
            delta=values[q]-pg[q][:,changed]
            balance_error=float(np.max(abs(delta.sum(axis=1))))
            r_error=float(np.max(abs(values[q][:,rmn_position].sum(axis=1)-applied[q])))
            require(max(bound_error,balance_error,r_error)<TOL, "Counterfactual violates hydro balance or native bounds")
            require(not np.intersect1d(changed,np.r_[stl,ps,np.arange(1436,1464)]).size, "A held-fixed unit entered the changed set")
            if pool=="outside_ab":require(joined.iloc[donor].electrical_landing_zone.isin(["A","B"]).sum()==0,"Primary donors entered western zone cuts")
            adjustments=np.zeros(8760);adjustments[q]=applied[q]-requested[q]
            adjustment_mask=q&(np.abs(adjustments)>TOL)
            path=INPUTS/(name+".npz")
            np.savez_compressed(path,gen_rows_1based=changed+1,gen_pg_changed=values,qualified=q,
                requested_RMN_model_mw=requested,applied_RMN_model_mw=applied,
                requested_target_feasible=requested_feasible,fixed_experiment_mask=mask,
                feasible_RMN_lower_model_mw=lower,feasible_RMN_upper_model_mw=upper,
                RMN_generator_rows_1based=rmn+1,donor_generator_rows_1based=donor+1,
                RMN_projection_dual=r_dual,donor_projection_dual=d_dual,
                hour_index=np.arange(1,8761),timestamp_utc=hours.timestamp_utc.to_numpy(str),gamma=gamma,
                source_month=months,variant_name=name,donor_policy=pool)
            scenario_rows.append(dict(name=name,file=rel(path),sha256=sha(path),qualified_hours=int(q.sum()),
                scope="full_fixed_8651_cohort" if q.sum()==8651 else "restricted_feasibility_diagnostic_not_annual",
                full_fixed_cohort=bool(q.sum()==8651),donor_policy=pool,target_policy=mode,
                donor_generator_count=len(donor),changed_generator_count=len(changed),
                infeasible_requested_hour_count=int((mask&~requested_feasible).sum()),
                applied_hypothesis_adjusted_hour_count=int(adjustment_mask.sum()),
                maximum_hypothesis_adjustment_public_mw=float(np.max(abs(adjustments[q]))/gamma),
                mean_absolute_hypothesis_adjustment_public_mw=float(np.mean(abs(adjustments[q]))/gamma),
                raw_source_values_clipped_or_overwritten=False,native_bound_violation_model_mw=bound_error,
                hourly_total_Hydro_and_global_PG_change_model_mw=balance_error,
                held_fixed_generator_rows_not_saved_or_changed=True,monthly_sum_constraints=month_constraints))
            row=hours.copy();row["scenario"]=name;row["source_month"]=months;row["fixed_experiment_qualified"]=mask;row["qualified"]=q
            row["requested_RMN_public_mw"]=requested/gamma;row["applied_RMN_public_mw"]=applied/gamma
            row["baseline_RMN_public_mw"]=np.where(mask,r0/gamma,np.nan)
            row["baseline_StLawrence_public_mw"]=np.where(mask,s0/gamma,np.nan)
            row["P63_Hydro_public_mw"]=np.where(mask,H/gamma,np.nan)
            row["baseline_all_Hydro_public_mw"]=np.where(mask,hyd0/gamma,np.nan)
            row["P63_minus_preserved_baseline_Hydro_public_mw"]=np.where(mask,(H-hyd0)/gamma,np.nan)
            row["feasible_RMN_lower_public_mw"]=lower/gamma;row["feasible_RMN_upper_public_mw"]=upper/gamma
            row["RMN_change_public_mw"]=np.where(q,(applied-r0)/gamma,np.nan)
            row["donor_change_public_mw"]=np.where(q,(donor_target-donor0)/gamma,np.nan)
            for zone in ["A","B"]:
                positions=np.flatnonzero(joined.iloc[donor].electrical_landing_zone.eq(zone).to_numpy())
                diff=np.full(8760,np.nan);diff[q]=(d_values[q][:,positions]-pg[q][:,donor][:,positions]).sum(axis=1)/gamma
                row[f"donor_zone_{zone}_change_public_mw"]=diff
            row["hypothesis_target_adjusted"]=adjustment_mask;row["requested_target_feasible"]=requested_feasible
            hourly_rows.append(row)
            for source_month in month_rows:
                m=source_month["month"];selected=q&(months==m)
                monthly_rows.append(dict(scenario=name,donor_policy=pool,**source_month,
                    variant_qualified_hours=int(selected.sum()),
                    applied_RMN_qualified_energy_public_mwh=float(applied[selected].sum()/gamma),
                    applied_RMN_qualified_mean_public_mw=float(applied[selected].mean()/gamma) if selected.any() else None,
                    fixed_cohort_month_fully_qualified=bool(selected.sum()==source_month["fixed_cohort_hours"]),
                    monthly_cohort_mean_constraint_claim=bool(mode=="month_shape_constrained" and selected.sum()==source_month["fixed_cohort_hours"])))
            print(json.dumps({k:scenario_rows[-1][k] for k in ["name","qualified_hours","scope","infeasible_requested_hour_count","applied_hypothesis_adjusted_hour_count"]}),flush=True)
    csv_write(pd.concat(hourly_rows,ignore_index=True),"niagara_hourly_changes.csv.gz")
    csv_write(pd.DataFrame(monthly_rows),"niagara_monthly_scope.csv")
    require(max(identity_errors)<TOL, "Unchanged-target donor control did not reproduce baseline")
    require(all(sha(ROOT/p)==value for p,value in frozen.items()), "An old artifact or the user-modified report changed")
    paths+=[plan_path,Path(__file__)]
    receipt=dict(passed=True,datasettype="generation",status="source_only_counterfactual_inputs_ready_for_independent_review",started_utc=started,completed_utc=utc_now(),
        baseline_dispatch_path=rel(BASE),baseline_dispatch_sha256=sha(BASE),
        current_git_head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        fixed_experiment_mask_sha256=sha(MASK),fixed_experiment_hours=8651,layout="compact_changed_generator_rows",
        compact_fields=["gen_rows_1based","gen_pg_changed"],
        unchanged_rows_policy="Every row outside gen_rows_1based is copied exactly from the sealed all-boundary baseline. Every PG row outside scenario qualified is unavailable.",
        source_only=True,internal_interface_observations_read=False,interface_score_based_selection=False,power_flow_run=False,
        scenarios=scenario_rows,primary_donor_policy="outside_ab",full_fixed_cohort_scenarios=[r["name"] for r in scenario_rows if r["full_fixed_cohort"]],
        fixed_groups=dict(StLawrence_rows_1based=(stl+1).tolist(),PS_rows_1based=(ps+1).tolist(),external_rows_1based=list(range(1437,1465))),
        identity_compensation_control_max_model_mw=max(identity_errors),
        all_old_dependency_hashes_unchanged=True,user_modified_old_report_preserved=True,user_modified_old_report_sha256=frozen[rel(REPORT)],
        source_month_policy=plan()["monthly_scope"],P63_Hydro_and_preserved_baseline_Hydro_distinction=plan()["conserved_total"],
        output_evidence=[dict(path=rel(INPUTS/name),sha256=sha(INPUTS/name)) for name in ["niagara_generator_scope.csv","niagara_hourly_changes.csv.gz","niagara_monthly_scope.csv"]],
        documentation_preservation_is_not_a_numerical_input=True,
        dependencies=[dict(path=rel(p),sha256=sha(p)) for p in paths if p != REPORT],
        limitations=["Controlled allocation hypotheses, not observed hourly Niagara dispatch or validated reservoir/commitment operations.",
                     "Monthly means on incomplete cohorts require representative missing-hour allocation; no full-month/year energy assertion.",
                     "The bounded legacy scenario changes the hypothesis target at its feasibility boundary; the literal scenario remains separately inspectable.",
                     "Compensation placement changes western zone-injection attribution. Outside-A/B donors are primary; all-other-HY donors are an explicit balancing sensitivity.",
                     "All reported feasibility comes only from original active-power boxes and accounting constraints. No power flow, thermal or AC verification is performed here."])
    (INPUTS/"niagara_receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(passed=True,scenarios=len(scenario_rows),full_fixed_cohort_scenarios=receipt["full_fixed_cohort_scenarios"],receipt_sha256=sha(INPUTS/"niagara_receipt.json")),indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--plan-only",action="store_true")
    args=parser.parse_args()
    if args.plan_only:print(write_plan())
    else:main()
