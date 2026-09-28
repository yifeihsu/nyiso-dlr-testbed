"""Export the matched NYgrid2019 inputs and independently verify the NY-only cut.

Run export_reference_snapshot.m first for the six development-hour components.
All annual boundary injections are model-derived terminal flows, not telemetry.
"""
from __future__ import annotations
import csv
import hashlib
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "output/nygrid_2019"
OUT = ROOT / "output/nygrid_compact_2019/reference"
UPSTREAM = ROOT / "tmp/nygrid_2019_reproduction/upstream"
spec = importlib.util.spec_from_file_location("independent_dc", ROOT / "scripts/nygrid_2019/replay_dc.py")
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)


def write_csv(name, rows):
    path = OUT / name
    with path.open("w", encoding="utf8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def aggregate(values, source_bus, target_bus):
    a = np.zeros((len(source_bus), len(target_bus)))
    lookup = {int(b): i for i, b in enumerate(target_bus)}
    for k, b in enumerate(source_bus):
        if int(b) in lookup: a[k, lookup[int(b)]] = 1
    return np.asarray(values) @ a


def export():
    OUT.mkdir(parents=True, exist_ok=True)
    chunks, manifests = [], []
    for part in range(1, 5):
        path = SOURCE / f"annual_{part}.mat"
        m, _, info = dc.load_complete(path)
        # Actual targets are exported for retrospective comparison, never used
        # by the independent NY-only nodal solve.
        m["actual"] = loadmat(path, simplify_cells=True, variable_names=["actual"])["actual"]
        chunks.append(m); manifests.append(info)
    hours = np.concatenate([np.arange(int(m["first_hour"]), int(m["last_hour"]) + 1) for m in chunks])
    assert np.array_equal(hours, np.arange(1, 8761))
    case = chunks[0]["base_case"]
    source_bus, source_branch, source_gen = [np.asarray(case[k], float) for k in ["bus", "branch", "gen"]]
    source_ids = source_bus[:, 0].astype(int)
    ids = np.arange(37, 83)
    ny = np.isin(source_ids, ids)
    assert np.array_equal(source_ids[ny], ids)
    fny = np.isin(source_branch[:, 0], ids); tny = np.isin(source_branch[:, 1], ids)
    internal, crossing = fny & tny, fny ^ tny
    source_rows = np.flatnonzero(internal) + 1
    crossing_rows = np.flatnonzero(crossing) + 1
    fuels = np.asarray(case["genfuel"]).astype(str).reshape(-1)
    gen_ny = np.isin(source_gen[:, 0], ids)
    hq = gen_ny & (fuels == "Import")
    assert np.array_equal(np.flatnonzero(hq), [270]) and source_gen[hq, 0] == 48
    native = gen_ny & ~hq
    assert (sum(internal), sum(crossing), sum(native)) == (67, 8, 243)
    branch = source_branch[internal, :13]
    pg = np.concatenate([np.atleast_2d(m["input_pg"]) for m in chunks])
    solved_pg = np.concatenate([np.atleast_2d(m["result_pg"]) for m in chunks])
    source_pd = np.concatenate([np.atleast_2d(m["bus_pd"]) for m in chunks])
    source_pf = np.concatenate([np.atleast_2d(m["branch_pf"]) for m in chunks])
    source_va = np.concatenate([np.atleast_2d(m["bus_va"]) for m in chunks])
    dc_pf = np.concatenate([np.atleast_2d(m["dc_pf"]) for m in chunks])
    corrected = np.concatenate([np.atleast_2d(m["corrected_sim"]) for m in chunks])
    actual = np.concatenate([np.atleast_2d(m["actual"]) for m in chunks])
    for m in chunks:
        c = m["base_case"]
        assert np.array_equal(c["branch"][:, :13], source_branch[:, :13])
        assert np.array_equal(c["bus"][:, [0, 1, 4, 8]], source_bus[:, [0, 1, 4, 8]])
        assert np.array_equal(c["gen"][:, [0, 7]], source_gen[:, [0, 7]])
    p_native = aggregate(pg[:, native], source_gen[native, 0], ids)
    p_solved = aggregate(solved_pg[:, native], source_gen[native, 0], ids)
    p_hq = aggregate(pg[:, hq], source_gen[hq, 0], ids)
    assert np.max(abs(pg[:, hq] - solved_pg[:, hq])) < 1e-9
    landing_ac = np.where(fny[crossing], source_branch[crossing, 0], source_branch[crossing, 1]).astype(int)
    external_ac = np.where(fny[crossing], source_branch[crossing, 1], source_branch[crossing, 0]).astype(int)
    ac_sign = np.where(fny[crossing], -1., 1.)
    ac_crossing_p = source_pf[:, crossing] * ac_sign
    p_ac = aggregate(ac_crossing_p, landing_ac, ids)
    dcline = np.asarray(case["dcline"], float)
    assert np.all(dcline[:, 2] == 1) and np.all(dcline[:, 15:17] == 0)
    assert np.all(~np.isin(dcline[:, 0], ids)) and np.all(np.isin(dcline[:, 1], ids))
    p_dc = aggregate(dc_pf, dcline[:, 1], ids) - aggregate(dc_pf, dcline[:, 0], ids)
    total_boundary = p_ac + p_dc + p_hq
    net_pd = source_pd[:, ny]
    # Keep only originalNY buses/branches/native generators. Every external
    # contribution is applied once as an explicit negative demand.
    ny_case = dict(baseMVA=float(case["baseMVA"]), bus=source_bus[ny, :13], branch=branch,
                   gen=source_gen[native, :21], dcline=np.empty((0, 17)))
    net = dc.network(ny_case)
    replay = dc.predict(net, net_pd - total_boundary, pg[:, native], np.empty((8760, 0)))
    branch_error = np.max(abs(replay["flow"] - source_pf[:, internal]), axis=1)
    angle_error = np.max(abs(replay["angle_deg"] - source_va[:, ny]), axis=1)
    slack_error = np.max(abs(replay["result_pg"] - solved_pg[:, native]), axis=1)
    imap = np.asarray(case["if"]["map"])
    full_operator = dc.operator([imap[imap[:, 0] == j, 1] for j in [1, 2, 3, 4, 5, 8, 10]], 94)
    assert np.all(full_operator[:, ~internal] == 0)
    op = full_operator[:, internal]
    interface_error = np.max(abs(replay["flow"] @ op.T - corrected), axis=1)
    assert max(branch_error.max(), slack_error.max(), interface_error.max(), replay["nodal_residual_mw"].max()) <= 1e-7
    arrays = dict(hour_index=hours, bus_ids=ids, source_bus_ids=source_ids,
        base_mva=np.array(case["baseMVA"]), bus=source_bus[ny, :13], branch=branch,
        native_gen=source_gen[native, :21], native_generator_source_rows=np.flatnonzero(native) + 1,
        source_branch=source_branch[:, :13], source_branch_rows=source_rows,
        net_pd_mw=net_pd, native_input_pg_bus_mw=p_native, native_solved_pg_bus_mw=p_solved,
        all_input_pg_with_hq_bus_mw=p_native + p_hq, all_solved_pg_with_hq_bus_mw=p_solved + p_hq,
        slack_adjustment_bus_mw=p_solved - p_native,
        boundary_ac_bus_mw=p_ac, boundary_dc_bus_mw=p_dc, boundary_hq_bus_mw=p_hq,
        boundary_total_bus_mw=total_boundary,
        effective_pd_for_native_only_mw=net_pd - total_boundary,
        crossing_source_rows=crossing_rows, crossing_ny_bus=landing_ac, crossing_external_bus=external_ac,
        crossing_pf_to_ny_injection_sign=ac_sign, boundary_ac_crossing_injection_mw=ac_crossing_p,
        dcline=dcline, dc_schedule_mw=dc_pf, branch_pf_mw=source_pf[:, internal],
        source_branch_pf_mw=source_pf, bus_va_deg=source_va[:, ny],
        operator_coefficients=op, source_operator_coefficients=full_operator,
        corrected_interface_mw=corrected, observed_interface_mw=actual,
        interface_names=np.asarray(dc.INTERFACES, dtype='U32'))
    np.savez_compressed(OUT / "annual_reference.npz", **arrays)
    # MATLAB transfer artifact uses the same explicitly named numeric arrays.
    savemat(OUT / "annual_reference.mat", arrays, do_compression=True)
    source_roles = {}
    with (UPSTREAM / "Data/npcc_new.csv").open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream): source_roles[int(row["idx"])] = row
    bus_rows = []
    for i, b in enumerate(source_ids):
        role = "original_NY_bus" if b in ids else "retained_external_boundary_bus"
        if b == 21: role = "retained_external_NE_auxiliary_generator_and_DC_sender"
        if b == 132: role = "retained_external_PJM_auxiliary_load_and_generator_aggregate"
        bus_rows.append(dict(source_bus=int(b), source_name=source_roles[b]["name"],
            released_allocation_zone=source_roles[b]["zone"], source_area=source_roles[b]["area"],
            retained_in_NY_only=b in ids, representation_role=role,
            physical_zone_verified=False, ny_only_row=int(np.flatnonzero(ids == b)[0] + 1) if b in ids else ""))
    write_csv("source_bus_role_register.csv", bus_rows)
    parallel_count = {}; branch_rows = []; row_lookup = {}
    for i, br in enumerate(source_branch):
        pair = tuple(sorted((int(br[0]), int(br[1])))); parallel_count[pair] = parallel_count.get(pair, 0) + 1
        key = f"NYGRID2019:BRANCH:{i+1}:F{int(br[0])}:T{int(br[1])}:PAR{parallel_count[pair]}"
        row_lookup[i + 1] = key
        role = "NY_internal" if internal[i] else "NY_external_crossing" if crossing[i] else "external_Ward_network"
        branch_rows.append(dict(source_branch_row=i+1, stable_key=key, from_bus=int(br[0]), to_bus=int(br[1]),
            parallel_ordinal=parallel_count[pair], role=role, ny_only_row=int(np.flatnonzero(source_rows == i+1)[0]+1) if internal[i] else "",
            r_pu=br[2], x_pu=br[3], b_pu=br[4], rate_a=br[5], tap=br[8], shift_deg=br[9], status=int(br[10]),
            physical_circuit_identity_verified=False, identity_scope="pinned_reduced_model_record_not_owner_circuit_identifier"))
    write_csv("source_branch_register.csv", branch_rows)
    coefficients = []
    for j, name in enumerate(dc.INTERFACES):
        for i in np.flatnonzero(full_operator[j]):
            coefficients.append(dict(interface=name, source_branch_row=int(i+1), stable_key=row_lookup[i+1],
                from_bus=int(source_branch[i, 0]), to_bus=int(source_branch[i, 1]),
                coefficient=float(full_operator[j, i]), ny_only_branch_row=int(np.flatnonzero(source_rows == i+1)[0]+1),
                metered_quantity="DC_from_terminal_PF", origin="released_if_map_semantic_operator_correction"))
    write_csv("corrected_interface_coefficients.csv", coefficients)
    write_csv("annual_ny_only_replay.csv", [dict(hour_index=int(h), timestamp=(datetime(2019,1,1)+timedelta(hours=int(h)-1)).isoformat(),
        max_internal_branch_error_mw=branch_error[k], max_interface_error_mw=interface_error[k],
        max_angle_error_deg=angle_error[k], max_native_solved_pg_error_mw=slack_error[k],
        max_nodal_residual_mw=replay["nodal_residual_mw"][k], passed=True) for k,h in enumerate(hours)])
    component_manifest = export_components(arrays, case, native, hq, row_lookup)
    provenance_paths = ['output/nygrid_2019/upstream_manifest.json', 'output/nygrid_2019/toolbox_manifest.json',
        'output/nygrid_2019/cached_upstream_manifest.json', 'output/nygrid_2019/verification_manifest.json',
        'output/nygrid_2019/unmodified_smoke_mirror_legacy.mat', 'output/nygrid_2019/annual_reproduction_input_manifest.csv',
        'scripts/nygrid_compact_2019/export_reference_snapshot.m', 'scripts/nygrid_compact_2019/export_reference.py',
        'scripts/nygrid_2019/replay_dc.py']
    write_csv('source_chain_manifest.csv', [dict(path=p,sha256_raw=dc.sha_file(ROOT/p)) for p in provenance_paths])
    summary = dict(complete_2019_hours=8760, original_NY_buses=46, NY_internal_AC_branch_records=67,
        native_generator_records=243, HQ_boundary_generator_records=1, AC_crossing_records=8, DC_records=4,
        annual_NY_only_exact_DC_replay_passed=True, tolerance_mw=1e-7,
        max_branch_error_mw=float(branch_error.max()), max_interface_error_mw=float(interface_error.max()),
        max_angle_error_deg=float(angle_error.max()), max_native_generation_error_mw=float(slack_error.max()),
        units="actual_2019_MW_unscaled", boundary_observed=False,
        boundary_policy="nativePG plus ACcrossing plus DC plus HQ exactlyonce; allPGwithHQ is an alternativeaccount, neveraddHQagain",
        auxiliary_bus_policy="21and132 remain in source57reference but are removed from NY-only after freezing all actual model terminal exchanges",
        result_scope="DC algebraic preservation only; external response, AC voltages/Q/capability and operating-limit compliance not established",
        annual_source_manifests=manifests, development_snapshot_components=component_manifest,
        exporter_sha256=dc.sha_file(Path(__file__)), independent_solver_sha256=dc.sha_file(ROOT/'scripts/nygrid_2019/replay_dc.py'))
    summary["outputs"] = [{"path": p.relative_to(ROOT).as_posix(), "sha256": dc.sha_file(p)}
                          for p in sorted(OUT.iterdir()) if p.is_file() and p.suffix in {".csv", ".mat", ".npz"}]
    (OUT / "reference_export_summary.json").write_text(json.dumps(summary, indent=2)+'\n', encoding='utf8')
    print(json.dumps({k:summary[k] for k in ["complete_2019_hours", "annual_NY_only_exact_DC_replay_passed", "max_branch_error_mw", "max_interface_error_mw"]},indent=2))


def export_components(arrays, annual_case, native, hq, branch_keys):
    path = OUT / "matched_snapshot_components.mat"
    source = loadmat(path, simplify_cells=True, variable_names=["snapshots"])["snapshots"]
    snapshots = list(source) if isinstance(source, (list, np.ndarray)) else [source]
    ids = arrays["bus_ids"]; records = []; generation = []; boundaries = []; dcrows = []; overview = []
    component_arrays = {k: [] for k in ["gross_pd_mw", "gross_qd_mvar", "wind_injection_mw", "other_renewable_injection_mw",
        "recorded_thermal_pg_bus_mw", "allocated_thermal_pg_bus_mw", "thermal_residual_pg_bus_mw", "nuclear_input_pg_bus_mw",
        "hydro_input_pg_bus_mw", "ward_net_load_adjustment_mw"]}
    selected = []
    for s in snapshots:
        dt = datetime.fromisoformat(str(s["timestamp"])); h = int((dt-datetime(2019,1,1)).total_seconds()/3600)
        selected.append(h+1); m=s["input_case"]; r=s["result_case"]
        bm=np.asarray(m["bus"],float); gm=np.asarray(m["gen"],float); gr=np.asarray(r["gen"],float)
        mask=np.isin(bm[:,0],ids)
        assert np.max(abs(bm[mask,2]-arrays["net_pd_mw"][h]))<1e-7
        assert np.max(abs(np.asarray(r["branch"])[:,13]-arrays["source_branch_pf_mw"][h]))<1e-7
        assert np.array_equal(bm[mask,0],ids)
        gross=aggregate(np.asarray(s["gross_pd_mw"]),s["gross_bus_ids"],ids)
        grossq=aggregate(np.asarray(s["gross_qd_mvar"]),s["gross_bus_ids"],ids)
        wind=aggregate(np.asarray(s["wind_injection_mw"]),s["renewable_bus_ids"],ids)
        other=aggregate(np.asarray(s["other_injection_mw"]),s["renewable_bus_ids"],ids)
        raw=np.asarray(s["thermal_source_recorded_pg_mw"],float)
        assert not np.isinf(raw).any()
        recorded=aggregate(np.nan_to_num(raw,nan=0),s["thermal_model_bus"],ids)
        thermal=aggregate(s["thermal_allocated_pg_mw"],s["thermal_model_bus"],ids)
        nr=np.asarray(s["nuclear_generator_rows"],int)-1; hr=np.asarray(s["hydro_generator_rows"],int)-1
        nuclear=aggregate(gm[nr,1],gm[nr,0],ids); hydro=aggregate(gm[hr,1],gm[hr,0],ids)
        ward=arrays["net_pd_mw"][h]-(gross-wind-other)
        values=[gross,grossq,wind,other,recorded,thermal,thermal-recorded,nuclear,hydro,ward]
        for key,value in zip(component_arrays,values):component_arrays[key].append(value)
        for i,b in enumerate(ids):
            row=dict(timestamp=dt.isoformat(),hour_index=h+1,source_bus=int(b))
            row.update({key:float(value[i]) for key,value in zip(component_arrays,values)})
            row.update(net_pd_mw=arrays["net_pd_mw"][h,i], native_input_pg_mw=arrays["native_input_pg_bus_mw"][h,i],
                native_solved_pg_mw=arrays["native_solved_pg_bus_mw"][h,i], slack_adjustment_mw=arrays["slack_adjustment_bus_mw"][h,i],
                boundary_ac_mw=arrays["boundary_ac_bus_mw"][h,i],boundary_dc_mw=arrays["boundary_dc_bus_mw"][h,i],
                boundary_hq_mw=arrays["boundary_hq_bus_mw"][h,i],boundary_total_mw=arrays["boundary_total_bus_mw"][h,i])
            records.append(row)
        names=np.asarray(s["thermal_name"]).astype(str);ptids=np.asarray(s["thermal_ptid"]).astype(str)
        for i in range(len(gm)):
            role='native_thermal' if i<227 else 'native_nuclear' if i in nr else 'native_hydro' if i in hr else 'HQ_boundary' if hq[i] else 'external_Ward_generator'
            generation.append(dict(timestamp=dt.isoformat(),source_gen_row=i+1,source_bus=int(gm[i,0]),
                stable_key=f'NYGRID2019:GEN:{i+1}:BUS:{int(gm[i,0])}',role=role,
                NYISO_name=str(names[i]) if i<227 else '', PTID=str(ptids[i]) if i<227 else '',
                raw_thermal_recorded_pg_mw=float(raw[i]) if i<227 and np.isfinite(raw[i]) else '',
                raw_thermal_record_missing=bool(i<227 and not np.isfinite(raw[i])),
                input_pg_mw=gm[i,1],solved_pg_mw=gr[i,1],slack_adjustment_mw=gr[i,1]-gm[i,1],
                pmax_mw=gm[i,8],pmin_mw=gm[i,9],qmax_mvar=gm[i,3],qmin_mvar=gm[i,4],status=int(gm[i,7]),
                reactive_bounds_physical_verified=False))
        for j,source_row in enumerate(arrays['crossing_source_rows']):
            boundaries.append(dict(timestamp=dt.isoformat(),source_branch_row=int(source_row),stable_key=branch_keys[source_row],
                ny_bus=int(arrays['crossing_ny_bus'][j]),external_bus=int(arrays['crossing_external_bus'][j]),
                ny_injection_mw=arrays['boundary_ac_crossing_injection_mw'][h,j],source_pf_mw=arrays['source_branch_pf_mw'][h,source_row-1],
                pf_to_ny_injection_sign=arrays['crossing_pf_to_ny_injection_sign'][j],basis='NYgrid_solved_DC_flow_on_AC_branch_not_terminal_telemetry'))
        for j,line in enumerate(arrays['dcline']):
            dcrows.append(dict(timestamp=dt.isoformat(),source_dc_row=j+1,from_bus=int(line[0]),to_bus=int(line[1]),
                schedule_mw=arrays['dc_schedule_mw'][h,j],loss0=line[15],loss1=line[16],
                channel=['NE_1385_plus_CSC','PJM_Neptune','PJM_HTP','PJM_VFT'][j],basis='released_hourly_mean_SCH_series'))
        overview.append(dict(timestamp=dt.isoformat(),hour_index=h+1,gross_load_mw=float(gross.sum()),
            thermal_recorded_mw=float(recorded.sum()),thermal_allocated_mw=float(thermal.sum()),thermal_residual_mw=float((thermal-recorded).sum()),
            statewide_hydro_mw=float(s['statewide_hydro_mw']),monthly_st_lawrence_cf=float(s['monthly_st_lawrence_capacity_factor']),
            monthly_st_lawrence_mw=float(s['monthly_st_lawrence_generation_mw']),nuclear_input_mw=float(nuclear.sum()),
            source_time_policy='released_hourly_mean_prepared_tables_with_their_existing_missing_hour_interpolation',
            raw_five_minute_samples_or_forward_hold_used_here=False,independently_observed_zonal_generation=False))
    write_csv('matched_bus_components.csv',records);write_csv('matched_generator_input_and_solution.csv',generation)
    write_csv('matched_AC_boundary_terminal_injections.csv',boundaries);write_csv('matched_DC_schedules.csv',dcrows)
    write_csv('matched_component_summary.csv',overview)
    for name,rows in [('jan08_bus_components.csv',records),('jan08_generator_input_and_solution.csv',generation),
        ('jan08_AC_boundary_terminal_injections.csv',boundaries),('jan08_DC_schedules.csv',dcrows)]:
        write_csv(name,[r for r in rows if r['timestamp']=='2019-01-08T15:00:00'])
    comp={key:np.vstack(values) for key,values in component_arrays.items()}
    comp.update(bus_ids=ids,hour_index=np.asarray(selected),timestamps=np.asarray([s['timestamp'] for s in snapshots],dtype='U19'))
    np.savez_compressed(OUT/'matched_components.npz',**comp)
    savemat(OUT/'matched_components.mat',comp,do_compression=True)
    return dict(snapshot_mat_sha256=dc.sha_file(path),snapshot_exporter_sha256=dc.sha_file(ROOT/'scripts/nygrid_compact_2019/export_reference_snapshot.m'),
                hours=selected,all_snapshots_are_previously_examined_development_examples=True,max_abs_Ward_NY_load_adjustment_mw=float(np.max(abs(comp['ward_net_load_adjustment_mw']))))


if __name__ == '__main__': export()
