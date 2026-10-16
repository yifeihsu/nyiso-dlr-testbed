"""Independent all-hour counterfactual controls, DC laws and interaction audit.

Does not call the experiment solver, source builders or score functions. The
five optional guard probes call only the runner's input reader with in-memory
metadata mutations; no source artifact is modified. No observations are read.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.linalg import lu_factor, lu_solve
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_western_counterfactuals"
WEST = ROOT / "output/nygrid_2025_western_audit"
BASE = ROOT / "output/nygrid_2025_dispatch/dispatch"
SLIM = ROOT / "output/nygrid_2025_slim/network/network_cases.mat"
FULL = ROOT / "output/nygrid_2025_downstate/network/network_cases.mat"
PAR = ROOT / "output/nygrid_2025_par_controls/controls/inputs.npz"
TOL = 1e-7


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def error(actual, expected, label, tol=TOL):
    actual, expected = np.asarray(actual), np.asarray(expected)
    require(actual.shape == expected.shape, label + ": shape mismatch")
    require(np.isfinite(actual).all() and np.isfinite(expected).all(), label + ": nonfinite value")
    result = float(np.max(abs(actual - expected), initial=0.))
    require(result <= tol, label + ": " + str(result))
    return result


def records(rows):
    require(rows and len({r["path"] for r in rows}) == len(rows), "Empty/duplicated dependency manifest")
    paths = []
    for row in rows:
        path = ROOT / row["path"]
        require(path.is_file() and sha(path) == row["sha256"], "Changed dependency: " + row["path"])
        paths.append(path)
    return paths


def axis(data, times, q, gamma, bus_ids=None):
    require(np.array_equal(data["hour_index"], np.arange(1, 8761)), "Counterfactual hour axis differs")
    require(np.array_equal(data["timestamp_utc"].astype(str), times), "Counterfactual UTC axis differs")
    require(data["qualified"].dtype == bool and np.array_equal(data["qualified"], q), "Counterfactual fixed cohort differs")
    require(float(data["gamma"]) == gamma, "Counterfactual gamma differs")
    if bus_ids is not None:
        require(np.array_equal(data["bus_ids"], bus_ids), "Load retained-bus IDs differ")


def equation_system(case, gen_buses):
    """Direct branch laws and sparse KCL maps, independent of replay helpers."""
    bus, branch = np.asarray(case["bus"]), np.asarray(case["branch"]).copy()
    require(np.array_equal(branch[210, :2], [48, 100]), "Controlled aggregate identity changed")
    branch[210, 10] = 0
    ids = bus[:, 0].astype(int); lookup = {value: j for j, value in enumerate(ids)}
    require(len(lookup) == len(ids), "Duplicate bus identity")
    f = np.array([lookup[int(v)] for v in branch[:, 0]])
    t = np.array([lookup[int(v)] for v in branch[:, 1]])
    C = csr_matrix((np.r_[np.ones(len(branch)), -np.ones(len(branch))],
                    (np.r_[np.arange(len(branch)), np.arange(len(branch))], np.r_[f, t])), shape=(len(branch), len(bus)))
    active = branch[:, 10] == 1
    graph = csr_matrix((np.ones(active.sum() * 2), (np.r_[f[active], t[active]], np.r_[t[active], f[active]])), shape=(len(bus), len(bus)))
    require(connected_components(graph, directed=False)[0] == 1, "Controlled network disconnected")
    tap = np.where(branch[:, 8] == 0, 1., branch[:, 8]); k = np.zeros(len(branch))
    k[active] = float(case["baseMVA"]) / (branch[active, 3] * tap[active])
    G = csr_matrix((np.asarray(case["gen"])[:, 7], (np.arange(len(gen_buses)), [lookup[int(v)] for v in gen_buses])),
                   shape=(len(gen_buses), len(bus)))
    old_dc = np.asarray(case["dcline"])
    require(old_dc.shape == (4, 17) and np.all(old_dc[:, 15:17] == 0), "Original DC records/losses changed")
    D = np.zeros((6, len(bus)))
    for j, row in enumerate(old_dc):
        D[j, lookup[int(row[0])]] = -row[2]; D[j, lookup[int(row[1])]] = row[2]
    D[4:, lookup[100]] = -1.; D[4:, lookup[48]] = 1.
    return dict(bus=bus, branch=branch, C=C, k=k, f=f, t=t, G=G, D=D, lookup=lookup,
                B=(C.T @ C.multiply(k[:, None])).toarray())


def flows(eq, theta):
    return (theta[:, eq["f"]] - theta[:, eq["t"]] - np.deg2rad(eq["branch"][:, 9])) * eq["k"]


def metadata_guard_probes(b, gen_record, load_record):
    """Probe actual runner guards with five small parsed-view mutations."""
    import run_experiments as runner
    originals = {}
    for item in [gen_record, load_record]:
        with np.load(ROOT / item["file"], allow_pickle=False) as values:
            originals[item["file"]] = {k: values[k] for k in values.files}
    specs = [("generation_hour_axis", gen_record, "hour_index"),
             ("generation_UTC_axis", gen_record, "timestamp_utc"),
             ("generation_gamma", gen_record, "gamma"),
             ("load_noncontiguous_bus_axis", load_record, "bus_ids"),
             ("load_fixed_cohort", load_record, "qualified")]
    real_load = np.load; checks = []
    class View:
        def __init__(self, data): self.data = data
        def __enter__(self): return self.data
        def __exit__(self, *args): return False
    for name, item, key in specs:
        data = dict(originals[item["file"]]); data[key] = np.array(data[key], copy=True)
        if key == "hour_index": data[key][0] += 1
        elif key == "timestamp_utc": data[key][0] = "2025-01-01T06:00:00Z"
        elif key == "gamma": data[key] = data[key] * 2
        elif key == "bus_ids": data[key] = np.arange(1, 149)
        elif key == "qualified": data[key][np.flatnonzero(data[key])[0]] = False
        target = (ROOT / item["file"]).resolve()
        def mocked(path, *args, **kwargs):
            return View(data) if Path(path).resolve() == target else real_load(path, *args, **kwargs)
        rejected = False; reason = ""
        with patch.object(np, "load", side_effect=mocked):
            try:
                runner.inputs(b, generation=item if item is gen_record else None, demand=item if item is load_record else None)
            except ValueError as exc:
                rejected = True; reason = str(exc)
        require(rejected, "Runner failed metadata guard: " + name)
        checks.append(dict(probe=name, rejected=True, reason=reason, files_mutated=False, power_flow_run=False))
    return checks


def validate():
    start = datetime.now(timezone.utc).isoformat()
    replay = read(OUT / "replay/replay_receipt.json")
    require(replay["passed"] and not replay["internal_observations_read"] and replay["fixed_qualified_hours"] == 8651,
            "Counterfactual replay is unqualified")
    dependencies = records(replay["dependencies"])
    gen_receipt = read(OUT / "inputs/niagara_receipt.json"); load_receipt = read(OUT / "inputs/load_receipt.json")
    require(gen_receipt["passed"] and load_receipt["passed"] and gen_receipt["source_only"]
            and not gen_receipt["internal_interface_observations_read"] and load_receipt["no_internal_interface_observation_access"], "Source family isolation flags differ")
    dependencies += records(gen_receipt["dependencies"]) + records(load_receipt["dependencies"])
    definitions = read(OUT / "design/experiment_plan.json")
    catalog = read(OUT / "replay/candidate_catalog.json")
    require(definitions["constraints"]["no_internal_flow_fitting"] and catalog["all_internal_observation_access_deferred"], "Sealed experiment source boundary differs")
    full_gen = [x for x in gen_receipt["scenarios"] if x["full_fixed_cohort"]]
    literal = [x for x in gen_receipt["scenarios"] if not x["full_fixed_cohort"]]
    expected = {"baseline"} | {x["name"] for x in full_gen + load_receipt["scenarios"]} | {x["name"] + "__load_original_B" for x in full_gen}
    require(len(expected) == 16 and {x["name"] for x in replay["cases"]} == expected, "Final16-scenario catalog differs")
    require({x["name"] for x in catalog["cases"]} == expected, "Runtime catalog differs from sealed candidates")
    require({x["name"] for x in replay["excluded_unscored_cases"]} == {x["name"] for x in literal}
            and not ({x["name"] for x in literal} & expected), "Incomplete literal hypothesis entered full-cohort replay")
    for x in literal:
        require(x["qualified_hours"] == 8374 and not x["full_fixed_cohort"], "Literal feasibility disclosure changed")
    model = loadmat(SLIM, simplify_cells=True); full = loadmat(FULL, simplify_cells=True)
    d = loadmat(BASE / "dispatch.mat", simplify_cells=True,
        variable_names=["hour_index", "timestamp_utc", "bus_pd", "bus_qd", "dc_pf", "gamma", "base_case", "reference_bus"])
    baseline_pg = loadmat(WEST / "dispatch/all_boundary_actual_dispatch.mat", simplify_cells=True, variable_names=["gen_pg"])["gen_pg"]
    parent = loadmat(WEST / "replay/dated_combined.mat", simplify_cells=True,
        variable_names=["bus_va", "interface_pf", "network_state_ids", "common_scoring_mask", "corrected_generator_buses"])
    bounds = loadmat(BASE / "dispatch_bounds.mat", simplify_cells=True, variable_names=["gen_pmin", "gen_pmax"])
    register = pd.read_csv(WEST / "corrected/model_generator_register.csv", keep_default_na=False)
    fleet_path = WEST / "corrected/fleet_register.csv"
    fleet = pd.read_csv(fleet_path, keep_default_na=False).set_index("fleet_id")
    native_meta = fleet.loc[pd.to_numeric(register.iloc[:1436].fleet_id).to_numpy(int)]
    conventional = native_meta.prime_mover.eq("HY").to_numpy()
    ids = pd.to_numeric(register.plant_id, errors="coerce").to_numpy()
    RMN = np.flatnonzero(ids == 2693)
    held_fixed = np.r_[~conventional | (ids[:1436] == 2694), np.ones(28, bool)]
    q = np.load(WEST / "replay/paired_common_mask.npy", allow_pickle=False)
    require(q.dtype == bool and q.shape == (8760,) and q.sum() == 8651 and np.array_equal(q, parent["common_scoring_mask"].astype(bool)), "Fixed physical cohort differs")
    times = np.asarray(d["timestamp_utc"]).astype(str); gamma = float(d["gamma"])
    bus_ids = np.asarray(model["kept_bus_ids"], int); zone_labels = np.asarray(model["bus_zones"]).astype(str)
    states = np.asarray(parent["network_state_ids"]).astype(str)
    native_bus = register.bus_id.to_numpy(int)
    require(np.array_equal(native_bus, parent["corrected_generator_buses"]), "Corrected generator terminal order changed")
    with np.load(PAR, allow_pickle=False) as par:
        dc = np.column_stack([d["dc_pf"], par["observed_model_mw"]])
    pd0 = np.pad(d["bus_pd"], ((0, 0), (0, 8))); qd0 = np.pad(d["bus_qd"], ((0, 0), (0, 8)))
    dependencies += [OUT / "replay/replay_receipt.json", OUT / "replay/candidate_catalog.json", fleet_path, Path(__file__)]
    for item in replay["cases"]:
        require(sha(ROOT / item["file"]) == item["sha256"], "Saved counterfactual output changed")
        dependencies.append(ROOT / item["file"])
    dependencies = list(dict.fromkeys(dependencies))
    before = {p: sha(p) for p in dependencies}
    systems = {key: (equation_system(model[key], native_bus), equation_system(full[key], native_bus),
                    model["recovery"][key.removesuffix("_case")]) for key in sorted(set(states[q]))}
    frames, audits = {}, []
    for item in replay["cases"]:
        pg = baseline_pg.copy(); pd_new, qd_new = pd0.copy(), qd0.copy()
        gen = item["generation"]; demand = item["demand"]
        if gen is not None:
            require(sha(ROOT / gen["file"]) == gen["sha256"], "Sealed generation input changed")
            with np.load(ROOT / gen["file"], allow_pickle=False) as candidate:
                axis(candidate, times, q, gamma)
                require(str(candidate["variant_name"]) == gen["name"] and str(candidate["donor_policy"]) == gen["donor_policy"], "Generation source identity/policy differs")
                rows = candidate["gen_rows_1based"] - 1
                require(np.array_equal(rows, rows.astype(int)) and len(set(rows)) == len(rows) and np.isin(rows, np.arange(1436)).all(), "Changed generation identity invalid")
                donors = candidate["donor_generator_rows_1based"].astype(int) - 1
                require(np.array_equal(candidate["RMN_generator_rows_1based"] - 1, RMN), "RobertMoses generator identity differs")
                require(set(rows) == set(RMN) | set(donors) and not set(RMN).intersection(donors), "Generator composition differs from source scope")
                require(conventional[donors].all() and not np.isin(ids[donors], [2693, 2694]).any(), "Compensation includes prohibited plant/type")
                if gen["donor_policy"] == "outside_ab":
                    require(~register.iloc[donors].zone.isin(["A", "B"]).any(), "OutsideAB donor pool contains A/B")
                pg[:, rows.astype(int)] = candidate["gen_pg_changed"]
        if demand is not None:
            require(sha(ROOT / demand["file"]) == demand["sha256"], "Sealed load input changed")
            with np.load(ROOT / demand["file"], allow_pickle=False) as candidate:
                axis(candidate, times, q, gamma, bus_ids)
                require(str(candidate["scenario"]) == demand["name"], "Load source scenario identity differs")
                pd_new, qd_new = candidate["bus_pd"], candidate["bus_qd"]
            other = ~np.isin(zone_labels, ["A", "B"])
            error(pd_new[:, other], pd0[:, other], "Other-zone active loads", 0)
            error(qd_new[:, other], qd0[:, other], "Other-zone reactive loads", 0)
            for zone in ["A", "B"]:
                select = zone_labels == zone
                error(pd_new[:, select].sum(axis=1), pd0[:, select].sum(axis=1), "ZonalPD conservation")
                error(qd_new[:, select].sum(axis=1), qd0[:, select].sum(axis=1), "ZonalQD conservation")
        error(pg[q][:, held_fixed], baseline_pg[q][:, held_fixed], "NonHY,StLawrence,pumped storage,andexternalPG fixed", 0)
        error(pg[q].sum(axis=1), baseline_pg[q].sum(axis=1), "Total generation fixed")
        error(pd_new[q].sum(axis=1), pd0[q].sum(axis=1), "Total load fixed")
        require((pg[q, :1436] >= bounds["gen_pmin"][q, :1436] - TOL).all()
                and (pg[q, :1436] <= bounds["gen_pmax"][q, :1436] + TOL).all(), "Native original bounds violated")
        with np.load(ROOT / item["file"], allow_pickle=False) as saved:
            require(np.array_equal(saved["hour_index"], np.arange(1, 8761)) and np.array_equal(saved["timestamp_utc"].astype(str), times)
                    and np.array_equal(saved["qualified"], q) and float(saved["gamma"]) == gamma, "Replay metadata axis differs")
            require(np.array_equal(saved["network_state_ids"].astype(str), states), "Dated topology state differs")
            angle = saved["bus_va"]; interface = saved["interface_pf"]
        require(np.isnan(angle[~q]).all() and np.isnan(interface[~q]).all(), "Unqualified replay hours were filled")
        frames[item["name"]] = (angle, interface)
        for state, (slim_eq, full_eq, recovery) in systems.items():
            ix = np.flatnonzero(q & (states == state)); theta = np.deg2rad(angle[ix])
            f = flows(slim_eq, theta)
            injection = pg[ix] @ slim_eq["G"] - pd_new[ix] - slim_eq["bus"][:, 4] + dc[ix] @ slim_eq["D"]
            kcl = error(f @ slim_eq["C"], injection, "Independent148 KCL")
            reconstructed = theta @ np.asarray(recovery["angle_lift"]).T + recovery["angle_offset"]
            f_full = flows(full_eq, reconstructed)
            pd_full = np.zeros((len(ix), 191))
            retained = np.asarray(recovery["retained_full_indices_1based"], int) - 1
            pd_full[:, retained] = pd_new[ix]
            injection_full = pg[ix] @ full_eq["G"] - pd_full - full_eq["bus"][:, 4] + dc[ix] @ full_eq["D"]
            kcl_full = error(f_full @ full_eq["C"], injection_full, "Independent191 KCL")
            if_full = f_full @ np.asarray(recovery["full_interface_branch_matrix"]).T
            if_error = error(interface[ix], if_full, "Full191 branch-based interface operators")
            direct = theta @ np.asarray(recovery["interface_angle_matrix"]).T + recovery["interface_flow_offset"]
            error(direct, interface[ix], "Saved angle-based interface operator")
            audits.append(dict(scenario=item["name"], family=item["family"], state=state, hours=len(ix),
                slim148_KCL_max_model_mw=kcl, recovered191_KCL_max_model_mw=kcl_full,
                full191_interface_max_error_model_mw=if_error,
                native_bounds_passed=True, external_PG_fixed=True, original_six_transfer_inputs_fixed=True))
    baseline = frames["baseline"]
    error(baseline[0][q], parent["bus_va"][q], "Fresh baseline retained angles")
    error(baseline[1][q], parent["interface_pf"][q], "Fresh baseline interfaces")
    null_error = error(frames["load_original_A"][1][q], baseline[1][q], "A-only exact no-op", 0)
    error(frames["load_original_A"][0][q], baseline[0][q], "A-only angle no-op", 0)
    alias_error = error(frames["load_original_AB"][1][q], frames["load_original_B"][1][q], "AB/B interface alias", 0)
    error(frames["load_original_AB"][0][q], frames["load_original_B"][0][q], "AB/B angle alias", 0)
    load_delta = frames["load_original_B"][1] - baseline[1]
    load_angle_delta = frames["load_original_B"][0] - baseline[0]
    interactions = []
    for gen in full_gen:
        combined = frames[gen["name"] + "__load_original_B"]
        alone = frames[gen["name"]]
        iface_error = error(combined[1][q] - alone[1][q], load_delta[q], "Generation/load interface superposition")
        angle_error = error(combined[0][q] - alone[0][q], load_angle_delta[q], "Generation/load angle superposition")
        interactions.append(dict(generation_scenario=gen["name"], interaction_hours=int(q.sum()),
            maximum_interface_superposition_error_model_mw=iface_error, maximum_angle_superposition_error_degree=angle_error,
            maximum_western_load_interaction_effect_public_mw=float(abs(combined[1][q, :2] - alone[1][q, :2]).max() / gamma)))
    # Independently predict the actual B-only response directly from deltaPD.
    with np.load(ROOT / next(x["file"] for x in load_receipt["scenarios"] if x["name"] == "load_original_B"), allow_pickle=False) as load_b:
        delta_pd = load_b["bus_pd"] - pd0
    linear_errors = []
    for state, (eq, _, recovery) in systems.items():
        ix = np.flatnonzero(q & (states == state))
        ref = np.flatnonzero(eq["bus"][:, 1] == 3)[0]
        nonref = np.flatnonzero(np.arange(148) != ref)
        delta_theta = np.zeros((len(ix), 148))
        delta_theta[:, nonref] = lu_solve(lu_factor(eq["B"][np.ix_(nonref, nonref)]), -delta_pd[ix][:, nonref].T).T
        prediction = delta_theta @ np.asarray(recovery["interface_angle_matrix"]).T
        linear_errors.append(error(load_delta[ix], prediction, "Independent B-only linear response"))
    # Only input-reader negative probes import the production runner.
    b = dict(qualified=q, dispatch=dict(gen_pg=baseline_pg), data=d, bounds=bounds, times=times, gamma=gamma)
    guards = metadata_guard_probes(b, full_gen[0], next(x for x in load_receipt["scenarios"] if x["name"] == "load_original_B"))
    require(all(sha(p) == value for p, value in before.items()), "An immutable dependency changed during validation")
    folder = OUT / "validation"; folder.mkdir(exist_ok=True)
    pd.DataFrame(audits).to_csv(folder / "independent_counterfactual_equations.csv", index=False)
    pd.DataFrame(interactions).to_csv(folder / "independent_load_interactions.csv", index=False)
    pd.DataFrame(guards).to_csv(folder / "runner_axis_guard_checks.csv", index=False)
    summary = dict(passed=True, started_utc=start, completed_utc=datetime.now(timezone.utc).isoformat(),
        fixed_hours=8651, full_cohort_scenarios=len(frames), scenario_hour_checks=len(frames) * int(q.sum()),
        excluded_literal_hypotheses=len(literal), literal_cases_not_powerflowed_or_scored=True,
        source_axes_and_all_fixed_generation_load_boundary_controls_verified=True,
        maximum_slim148_KCL_error_model_mw=max(x["slim148_KCL_max_model_mw"] for x in audits),
        maximum_full191_KCL_error_model_mw=max(x["recovered191_KCL_max_model_mw"] for x in audits),
        maximum_full191_interface_error_model_mw=max(x["full191_interface_max_error_model_mw"] for x in audits),
        A_only_noop_error_model_mw=null_error, AB_B_alias_error_model_mw=alias_error,
        maximum_independent_load_linear_response_error_model_mw=max(linear_errors),
        maximum_western_B_only_change_public_mw=float(abs(load_delta[q, :2]).max() / gamma),
        generation_load_interactions=len(interactions),
        maximum_interface_interaction_error_model_mw=max(x["maximum_interface_superposition_error_model_mw"] for x in interactions),
        metadata_guard_mutations_rejected=len(guards), source_files_mutated=False, internal_interface_observations_read=False,
        independent_equations_use_production_solver=False, no_counterfactual_definition_or_source_values_changed=True,
        no_AC_thermal_feasibility_claim=True, dependencies=[dict(path=p.relative_to(ROOT).as_posix(), sha256=value) for p, value in before.items()])
    (folder / "independent_load_interaction_validation.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
