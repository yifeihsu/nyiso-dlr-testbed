"""Exact AC zonal/cut accounting of the saved current 8,170-hour cohort.

All quantities are read from frozen inputs or saved solutions. No PF, OPF,
parameter fitting, or replacement of failed hours is performed.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output/nygrid_2025_remaining_errors/accounting"
STATES = ["pre_may", "may21", "may30", "post_dover"]
SCOPES = [("Dysinger_A", 0, "A"), ("WestCentral_AB", 1, "AB"),
          ("TotalEast_ABCDE", 2, "ABCDE"), ("Moses_D", 3, "D"),
          ("CentralEast_ABCDE", 4, "ABCDE"), ("UPNY_ABCDEFG", 5, "ABCDEFG"),
          ("SprainDunwoodie_I", 6, "I"), ("WestCentral_B_declared", 1, "B"),
          ("CentralEast_E_declared", 4, "E")]


def sha(p):
    with p.open("rb") as f: return hashlib.file_digest(f, "sha256").hexdigest()


def record(p): return {"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)}


def stats(pred, obs):
    e = pred - obs
    return {"n": len(e), "bias_public_MW": float(np.mean(e)), "MAE_public_MW": float(np.mean(abs(e))),
            "RMSE_public_MW": float(np.sqrt(np.mean(e * e))), "WAPE_percent": float(100 * np.sum(abs(e)) / np.sum(abs(obs)))}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    modeldir = ROOT / "output/nygrid_2025_latest_handoff/model"
    source_model = modeldir / "latest_model.mat"
    comparison_path = ROOT / "output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_arrays.npz"
    dc_path = ROOT / "output/nygrid_2025_western_counterfactuals/replay/baseline.npz"
    terms_path = ROOT / "output/nygrid_2025_acpf_profile_audit/alignment/interface_operator_terms.csv"
    map_path = ROOT / "output/nygrid_2025_latest_handoff/structure/runtime_branch_map.csv"
    intent_path = ROOT / "output/nygrid_2025_downstate/replay/interface_definitions.json"
    annual = ROOT / "output/nygrid_2025_ac_loss_revision/validation/annual/released_equivalent_boundary_consistent"
    monthly = [annual / f"monthly/profile_PF_2025_{j:02d}.mat" for j in range(1, 13)]
    profiles = [modeldir / "profiles_h0001_4380.mat", modeldir / "profiles_h4381_8760.mat"]
    inputs = [source_model, comparison_path, dc_path, terms_path, map_path, intent_path, *monthly, *profiles,
              ROOT / "scripts/nygrid_2025_ac_loss_revision/core/ac_loss_prepare_policy.m",
              ROOT / "scripts/nygrid_2025_ac_loss_revision/core/ac_loss_apply_budget.m"]
    before = {p: sha(p) for p in inputs}
    model = loadmat(source_model, simplify_cells=True)["model"]
    saved = np.load(comparison_path, allow_pickle=False); dc = np.load(dc_path, allow_pickle=False)
    q = saved["revised_qualified"]; gamma = float(saved["gamma"]); times = saved["timestamp_utc"]
    assert q.sum() == 8170 and np.isfinite(saved["observed"][q]).all()
    assert np.array_equal(times, dc["timestamp_utc"]) and dc["qualified"][q].all() and float(dc["gamma"]) == gamma
    names = saved["interface_names"].tolist(); terms = pd.read_csv(terms_path)
    maps = pd.read_csv(map_path); intents = json.loads(intent_path.read_text())
    state_index = np.asarray(model["axis"]["state_index"], int)
    state_names = np.array(STATES)[state_index - 1]
    native_mask = ~np.asarray(model["external"]["generator_mask"], bool)
    post = model["templates"][3]; postpolicy = model["loss_static"][3]
    busidx = {int(b): i for i, b in enumerate(post["bus"][:, 0])}
    generator_group = np.array([int(postpolicy["bus_group"][busidx[int(b)]]) for b in model["generator_bus_ids"]])
    busgroup140 = np.asarray(postpolicy["bus_group"][:140], int)
    source_native = np.zeros((8760, 11)); gross = source_native.copy()
    hq = np.zeros(8760); fixed_dc = np.zeros((8760, 6)); regional_target = np.zeros((8760, 3))
    for j, path in enumerate(profiles):
        a = loadmat(path, simplify_cells=True)["profiles"]; s = slice(j * 4380, (j + 1) * 4380)
        for zone in range(1, 12):
            source_native[s, zone - 1] = a["generator_PG_MW"][:, native_mask & (generator_group == zone)].sum(axis=1)
            gross[s, zone - 1] = a["bus_PD_MW"][:, busgroup140 == zone].sum(axis=1)
        hq[s] = a["generator_PG_MW"][:, int(postpolicy["HQ"]) - 1]
        fixed_dc[s] = a["fixed_transfer_PF_MW"]
        for region in range(12, 15):
            mask = np.asarray(postpolicy["external_gen_group"]) == region
            regional_target[s, region - 12] = a["generator_PG_MW"][:, mask].sum(axis=1) - a["bus_PD_MW"][:, busgroup140 == region].sum(axis=1)
    P = np.full((8760, 413), np.nan); T = P.copy()
    allocated = np.full((8760, 14), np.nan); served = np.full((8760, 11), np.nan)
    ext_ac = np.full((8760, 11, 3), np.nan); solved_native = np.full((8760, 11), np.nan)
    seen = np.zeros(8760, int); max_checks = {k: 0.0 for k in ["source_native_vs_solved", "source_gross_vs_saved", "fixed_DC", "regional_target", "allocated_loss_ownership", "NY_gross_equals_served_plus_loss"]}
    fields = ["hour_index", "timestamp_utc", "gamma", "PF", "PT", "branch_keys", "branch_present", "branch_active", "topology_state_index",
              "source_qualified", "PF_converged", "AC_equation_gate", "loss_allocation_gate", "reduction_and_equation_gate", "VQ_and_generator_assumption_gate",
              "actual_budget_MW", "NY_served_PD_MW", "NY_gross_target_MW", "regional_import_target_MW", "DC_PF", "DC_PT", "bus_id", "bus_PG", "external_gen_PG", "external_generator_rows_1based"]
    for path in monthly:
        d = loadmat(path, variable_names=fields, simplify_cells=True)
        ix = np.asarray(d["hour_index"], int) - 1; seen[ix] += 1
        assert np.array_equal(np.asarray(d["timestamp_utc"], str), times[ix]) and float(d["gamma"]) == gamma
        good = np.ones(len(ix), bool)
        for key in ["source_qualified", "PF_converged", "AC_equation_gate", "loss_allocation_gate", "reduction_and_equation_gate"]: good &= np.asarray(d[key], bool)
        assert np.array_equal(good, q[ix]) and not np.asarray(d["VQ_and_generator_assumption_gate"], bool)[good].any()
        assert np.array_equal(np.asarray(d["topology_state_index"], int), state_index[ix])
        ext_rows = np.asarray(d["external_generator_rows_1based"], int) - 1
        assert np.array_equal(ext_rows, np.flatnonzero(~native_mask))
        allocated[ix[good]] = d["actual_budget_MW"][good]; served[ix[good]] = d["NY_served_PD_MW"][good]
        keyrow = {str(k): i for i, k in enumerate(d["branch_keys"])}; busrow = {int(b): i for i, b in enumerate(d["bus_id"])}
        for sn, state in enumerate(STATES, 1):
            local = np.flatnonzero(good & (state_index[ix] == sn)); h = ix[local]
            if not len(h): continue
            p = model["loss_static"][sn - 1]; m = model["templates"][sn - 1]
            table = maps[maps.state.eq(state)].set_index("runtime_branch_row")
            first = [keyrow[str(table.loc[int(r), "branch_key"])] for r in p["from_runtime"]]
            last = [keyrow[str(table.loc[int(r), "branch_key"])] for r in p["to_runtime"]]
            npart = len(first); cols = np.arange(npart)
            assert d["branch_present"][np.ix_(local, first)].all() and d["branch_present"][np.ix_(local, last)].all()
            P[np.ix_(h, cols)] = d["PF"][np.ix_(local, first)]; T[np.ix_(h, cols)] = d["PT"][np.ix_(local, last)]
            losses = P[np.ix_(h, cols)] + T[np.ix_(h, cols)]
            owned = losses @ np.asarray(p["loss_ownership"]).T
            max_checks["allocated_loss_ownership"] = max(max_checks["allocated_loss_ownership"], float(np.max(abs(owned - allocated[h]))))
            ext_ac[h] = 0.0; pf = np.asarray(p["parent_from"], int); pt = np.asarray(p["parent_to"], int)
            on = m["branch"][np.asarray(p["from_runtime"], int) - 1, 10] > 0
            assert np.all(m["bus"][:, 4] == 0) and np.all(m["dcline"][:, 15:17] == 0)
            for k in np.flatnonzero(on & ((pf <= 11) != (pt <= 11))):
                if pf[k] <= 11: ext_ac[h, pf[k] - 1, pt[k] - 12] -= P[h, k]
                else: ext_ac[h, pt[k] - 1, pf[k] - 12] -= T[h, k]
            for zone in range(1, 12):
                ids = m["bus"][np.asarray(p["bus_group"]) == zone, 0].astype(int)
                allpg = d["bus_PG"][np.ix_(local, [busrow[b] for b in ids])].sum(axis=1)
                external = d["external_gen_PG"][np.ix_(local, np.flatnonzero(generator_group[ext_rows] == zone))].sum(axis=1)
                solved_native[h, zone - 1] = allpg - external
        for name, left, right in [
            ("source_native_vs_solved", source_native[ix[good]], solved_native[ix[good]]),
            ("source_gross_vs_saved", gross[ix[good]], d["NY_gross_target_MW"][good]),
            ("fixed_DC", fixed_dc[ix[good]], d["DC_PF"][good]),
            ("fixed_DC", fixed_dc[ix[good]], d["DC_PT"][good]),
            ("regional_target", regional_target[ix[good]], d["regional_import_target_MW"][good]),
            ("NY_gross_equals_served_plus_loss", gross[ix[good]], served[ix[good]] + allocated[ix[good], :11])]:
            max_checks[name] = max(max_checks[name], float(np.max(abs(left - right))))
    assert np.all(seen == 1) and max(max_checks.values()) < 1e-5, max_checks
    loss = P + T; DC = np.zeros((8760, 11))
    for j, row in enumerate(post["dcline"]):
        target_zone = int(postpolicy["bus_group"][busidx[int(row[1])]])
        assert 1 <= target_zone <= 11
        DC[:, target_zone - 1] += fixed_dc[:, j]
    scope_frames = []; definition_rows = []; summary_rows = []; preferred = {}
    for scope, j, letters in SCOPES:
        zone_ids = np.array([ord(z) - 64 for z in letters], int); z = zone_ids - 1
        result = {k: np.full(8760, np.nan) for k in ["primary", "member_midpoint", "complete_midpoint", "signed_half_loss", "member_loss", "omitted_midpoint", "internal_loss", "boundary_loss", "rhs", "closure", "served_closure", "ownership_closure"]}
        native = source_native[:, z].sum(axis=1); demand = gross[:, z].sum(axis=1)
        hq_inside = hq if 4 in zone_ids else np.zeros(8760)
        ac = ext_ac[:, z, :].sum(axis=(1, 2)); dc_in = DC[:, z].sum(axis=1)
        rhs = native + hq_inside + ac + dc_in - demand
        for sn, state in enumerate(STATES, 1):
            h = np.flatnonzero(q & (state_index == sn)); p = model["loss_static"][sn - 1]; m = model["templates"][sn - 1]
            f = np.asarray(p["parent_from"], int); t = np.asarray(p["parent_to"], int)
            fs = np.isin(f, zone_ids); ts = np.isin(t, zone_ids)
            on = m["branch"][np.asarray(p["from_runtime"], int) - 1, 10] > 0
            cross = np.flatnonzero(on & (f <= 11) & (t <= 11) & (fs != ts)); cross_sign = np.where(fs[cross], 1, -1)
            internal = np.flatnonzero(on & fs & ts)
            rows = terms[terms.state.eq(state) & terms.interface.eq(names[j])]
            members = rows.original_branch_row.to_numpy(int) - 1; signs = rows.coefficient.to_numpy(int)
            assert set(members) <= set(cross) and np.array_equal(signs, np.where(fs[members], 1, -1))
            missing = sorted(set(cross) - set(members)); npart = len(f)
            cp = P[np.ix_(h, cross)]; ct = T[np.ix_(h, cross)]
            mp = P[np.ix_(h, members)]; mt = T[np.ix_(h, members)]
            complete_mid = .5 * ((cp - ct) * cross_sign).sum(axis=1)
            member_mid = .5 * ((mp - mt) * signs).sum(axis=1)
            primary = (mp * signs).sum(axis=1); correction = .5 * ((mp + mt) * signs).sum(axis=1)
            internal_loss = loss[np.ix_(h, internal)].sum(axis=1); boundary_loss = (cp + ct).sum(axis=1)
            source_export = np.where(cross_sign > 0, cp, ct).sum(axis=1)
            reconstruction = rhs[h] - (complete_mid - member_mid) + correction
            values = {"primary": primary, "member_midpoint": member_mid, "complete_midpoint": complete_mid,
                "signed_half_loss": correction, "member_loss": (mp + mt).sum(axis=1), "omitted_midpoint": complete_mid - member_mid,
                "internal_loss": internal_loss, "boundary_loss": boundary_loss, "rhs": rhs[h], "closure": primary - reconstruction,
                "served_closure": source_export - (native[h] + hq_inside[h] + ac[h] + dc_in[h] - served[np.ix_(h, z)].sum(axis=1) - internal_loss),
                "ownership_closure": allocated[np.ix_(h, z)].sum(axis=1) - internal_loss - .5 * boundary_loss}
            for key, value in values.items(): result[key][h] = value
            definition_rows.append({"state": state, "scope": scope, "interface": names[j], "accounting_zone_set": "+".join(letters),
                "declared_source_zones": "+".join(intents[j]["source_zones"]), "member_count": len(members), "complete_NY_cut_count": len(cross),
                "is_complete_cut": len(missing) == 0, "omitted_parent_rows": ";".join(str(k + 1) for k in missing),
                "external_AC_parent_rows": ";".join(str(k + 1) for k in np.flatnonzero(on & ((fs & (t > 11)) | (ts & (f > 11))))),
                "signed_members": ";".join(str(int(c) * (int(k) + 1)) for k, c in zip(members, signs))})
        errs = {key: float(np.max(abs(result[key][q]))) for key in ["closure", "served_closure", "ownership_closure"]}
        midpoint_error = float(np.max(abs(result["complete_midpoint"][q] - rhs[q])))
        official_error = float(np.max(abs(result["primary"][q] / gamma - saved["revised_legacy_signed_literal_from"][q, j])))
        assert max(*errs.values(), midpoint_error, official_error) < 1e-5, (scope, errs, midpoint_error, official_error)
        frame = pd.DataFrame({"hour_index": np.flatnonzero(q) + 1, "timestamp_utc": times[q], "state": state_names[q],
            "scope": scope, "interface": names[j], "accounting_zone_set": "+".join(letters),
            "native_PG_model_MW": native[q], "HQ_PG_model_MW": hq_inside[q], "external_AC_import_model_MW": ac[q],
            "fixed_DC_import_model_MW": dc_in[q], "gross_P58_model_MW": demand[q],
            "served_PD_model_MW": served[q][:, z].sum(axis=1), "allocated_loss_model_MW": allocated[q][:, z].sum(axis=1),
            **{key + "_model_MW": value[q] for key, value in result.items()},
            "observed_public_numeric_MW": saved["observed"][q, j],
            "primary_public_MW": result["primary"][q] / gamma,
            "error_public_MW": result["primary"][q] / gamma - saved["observed"][q, j]})
        scope_frames.append(frame)
        summary_rows.append({"scope": scope, "interface": names[j], **stats(result["primary"][q] / gamma, saved["observed"][q, j]),
            "signed_half_loss_mean_public_MW": float(np.mean(result["signed_half_loss"][q]) / gamma),
            "signed_half_loss_mean_abs_public_MW": float(np.mean(abs(result["signed_half_loss"][q])) / gamma),
            "signed_half_loss_max_abs_public_MW": float(np.max(abs(result["signed_half_loss"][q])) / gamma),
            "omitted_midpoint_mean_public_MW": float(np.mean(result["omitted_midpoint"][q]) / gamma),
            "maximum_primary_identity_error_model_MW": errs["closure"], "maximum_complete_midpoint_error_model_MW": midpoint_error,
            "maximum_nodal_sum_error_model_MW": errs["served_closure"], "maximum_loss_ownership_error_model_MW": errs["ownership_closure"]})
        if j not in preferred: preferred[j] = result
    pd.concat(scope_frames, ignore_index=True).to_csv(OUT / "hourly_cut_drivers.csv", index=False)
    pd.DataFrame(definition_rows).to_csv(OUT / "cut_completeness_and_bypass.csv", index=False)
    pd.DataFrame(summary_rows).to_csv(OUT / "cut_identity_summary.csv", index=False)
    primary = np.column_stack([preferred[j]["primary"] for j in range(7)])
    midpoint = np.column_stack([preferred[j]["member_midpoint"] for j in range(7)])
    correction = np.column_stack([preferred[j]["signed_half_loss"] for j in range(7)])
    observed = saved["observed"]; error = primary / gamma - observed
    shared = error[:, 0]; incremental = (primary[:, 1] - primary[:, 0]) / gamma - (observed[:, 1] - observed[:, 0])
    dcm = dc["interface_pf"]; delta = primary - dcm
    dy_fixed = source_native[:, 0] - gross[:, 0] + regional_target[:, 1] - fixed_dc[:, 4:6].sum(axis=1)
    west_fixed = dy_fixed + source_native[:, 1] - gross[:, 1]
    ms_fixed = source_native[:, 3] + hq + fixed_dc[:, 4:6].sum(axis=1) - gross[:, 3]
    te_fixed = source_native[:, :5].sum(axis=1) - gross[:, :5].sum(axis=1) + hq + regional_target[:, 1]
    up_fixed = source_native[:, :7].sum(axis=1) - gross[:, :7].sum(axis=1) + hq + regional_target.sum(axis=1) - fixed_dc[:, :4].sum(axis=1)
    pjma = ext_ac[:, 0, 2]; pjmc = ext_ac[:, 2, 2]; pjmg = ext_ac[:, 6, 2]
    pjm_north = pjma + pjmc; eg_mid = .5 * (P[:, 223] - T[:, 223])
    identities = {
        "DY_midpoint_fixed_inputs_plus_passive_stub": midpoint[:, 0] - dy_fixed - pjma,
        "WC_midpoint_fixed_inputs_plus_passive_stub": midpoint[:, 1] - west_fixed - pjma,
        "MS_midpoint_fixed_inputs": midpoint[:, 3] - ms_fixed,
        "UPNY_midpoint_fixed_inputs": midpoint[:, 5] - up_fixed,
        "ZoneB_primary_difference": primary[:, 1] - primary[:, 0] - (source_native[:, 1] - gross[:, 1]) - (correction[:, 1] - correction[:, 0]),
        "TE_midpoint_fixed_inputs_plus_PJM_north": midpoint[:, 2] - te_fixed - pjm_north,
        "PJM_north_south_DC_target_closure": pjm_north + pjmg + fixed_dc[:, 1:4].sum(axis=1) - regional_target[:, 2],
        "CE_equals_TE_minus_parent224_PF": primary[:, 4] - primary[:, 2] + P[:, 223],
        "CE_midpoint_equals_TE_midpoint_minus_224_midpoint": midpoint[:, 4] - midpoint[:, 2] + eg_mid,
        "shared_plus_incremental_residual_equals_WC": error[:, 1] - shared - incremental,
    }
    identity_errors = {k: float(np.max(abs(v[q]))) for k, v in identities.items()}
    assert max(identity_errors.values()) < 1e-5, identity_errors
    modes = pd.DataFrame({"hour_index": np.flatnonzero(q)+1, "timestamp_utc": times[q], "state": state_names[q],
        "DY_error_public_MW": error[q, 0], "WC_error_public_MW": error[q, 1], "shared_A_residual_public_MW": shared[q],
        "incremental_B_residual_public_MW": incremental[q], "observed_WC_minus_DY_numeric_MW": (observed[q, 1]-observed[q, 0]),
        "model_B_native_minus_gross_public_MW": (source_native[q, 1]-gross[q, 1])/gamma,
        "WC_minus_DY_terminal_correction_public_MW": (correction[q, 1]-correction[q, 0])/gamma,
        "PJM_A_passive_stub_import_public_MW": pjma[q]/gamma, "PJM_C_import_public_MW": pjmc[q]/gamma,
        "PJM_G_import_public_MW": pjmg[q]/gamma, "PJM_north_import_public_MW": pjm_north[q]/gamma,
        "PJM_north_DC_gate_inferred_public_MW": (dcm[q, 2]-te_fixed[q])/gamma,
        "parent224_from_terminal_public_MW": P[q, 223]/gamma, "parent224_midpoint_public_MW": eg_mid[q]/gamma,
        "DC_TE_minus_CE_reference_public_MW": (dcm[q, 2]-dcm[q, 4])/gamma,
        "Moses_fixed_midpoint_public_MW": ms_fixed[q]/gamma,
        "Moses_observed_minus_passive_upper_bound_MW": observed[q, 3]-ms_fixed[q]/gamma,
        **{f"AC_minus_DC_{j+1}_public_MW": delta[q, j]/gamma for j in range(7)},
        **{f"signed_half_loss_{j+1}_public_MW": correction[q, j]/gamma for j in range(7)}})
    modes.to_csv(OUT / "hourly_residual_modes.csv", index=False)
    ac_dc = []
    for j, name in enumerate(names):
        ac_dc.append({"interface": name, **{"AC_"+k:v for k,v in stats(primary[q,j]/gamma, observed[q,j]).items()},
            **{"DC_"+k:v for k,v in stats(dcm[q,j]/gamma, observed[q,j]).items()},
            "AC_minus_DC_mean_public_MW": float(np.mean(delta[q,j])/gamma),
            "signed_half_loss_mean_public_MW": float(np.mean(correction[q,j])/gamma),
            "midpoint_minus_DC_mean_public_MW": float(np.mean(delta[q,j]-correction[q,j])/gamma),
            "midpoint_minus_DC_max_abs_public_MW": float(np.max(abs(delta[q,j]-correction[q,j]))/gamma)})
    pd.DataFrame(ac_dc).to_csv(OUT / "matched_AC_DC_terminal_decomposition.csv", index=False)
    np.savez_compressed(OUT / "accounting_arrays.npz", hour_index=np.arange(1,8761), timestamp_utc=times, qualified=q, gamma=gamma,
        interface_names=np.array(names), primary_model_MW=primary, midpoint_model_MW=midpoint, correction_model_MW=correction,
        source_native_model_MW=source_native, source_gross_model_MW=gross, HQ_model_MW=hq, fixed_DC_model_MW=fixed_dc,
        regional_target_model_MW=regional_target, external_AC_zone_region_model_MW=ext_ac, parent224_PF_model_MW=P[:,223],
        parent224_midpoint_model_MW=eg_mid, observed_public_MW=observed, DC_interface_model_MW=dcm)
    leaf_checks = []
    for i,state in enumerate(STATES):
        m=model["templates"][i]; p=model["loss_static"][i]; row=np.flatnonzero(m["bus"][:,0]==140)[0]
        incident=np.flatnonzero((m["branch"][:,0]==140)|(m["branch"][:,1]==140))
        active=incident[m["branch"][incident,10]>0]
        goodleaf=np.all(m["bus"][row,2:6]==0) and not np.any(m["gen"][:,0]==140) and not np.isin(140,m["dcline"][:,:2])
        goodleaf=bool(goodleaf and len(active)==1 and int(p["parent"][active[0]])==71)
        assert goodleaf
        leaf_checks.append({"state":state,"bus":140,"active_parent":71,"zero_PD_QD_GS_BS":True,"no_generator_or_DC_terminal":True})
    outputs=[OUT/name for name in ["hourly_cut_drivers.csv","cut_completeness_and_bypass.csv","cut_identity_summary.csv","hourly_residual_modes.csv","matched_AC_DC_terminal_decomposition.csv","accounting_arrays.npz"]]
    assert all(sha(p)==h for p,h in before.items()), "A frozen input changed during the read-only analysis"
    report={"passed":True,"created_utc":datetime.now(timezone.utc).isoformat(),"source_checkout_commit":"303b626bcab43215c839ad7e175e7274f25b4bdc",
        "scope":"Exact saved AC zonal-cut accounting and conditional residual modes on the current matched8170 cohort",
        "qualified_hours":8170,"gamma":gamma,"cohort_mask_sha256":hashlib.sha256(q.tobytes()).hexdigest(),
        "independent_source_and_loss_checks_max_model_MW":max_checks,"exact_identity_max_errors_model_MW":identity_errors,
        "scope_closure_summary":summary_rows,"PJM_bus140_passive_leaf_checks":leaf_checks,
        "western_residual_statistics":{"DY_WC_error_correlation":float(np.corrcoef(error[q,0],error[q,1])[0,1]),
            "incremental_B_MAE_public_MW":float(np.mean(abs(incremental[q]))),"incremental_B_bias_public_MW":float(np.mean(incremental[q])),
            "PJM_A_import_mean_public_MW":float(np.mean(pjma[q])/gamma),"PJM_A_import_range_public_MW":[float(np.min(pjma[q])/gamma),float(np.max(pjma[q])/gamma)]},
        "Moses_conditional_passivity_bound":{"description":"All three frozen member coefficients are negative; primary <= fixed complete-cut midpoint for nonnegative member losses",
            "observed_above_model_midpoint_hours":int(np.sum(observed[q,3]>ms_fixed[q]/gamma)),
            "mean_positive_observed_gap_above_midpoint_MW":float(np.mean(np.maximum(0,observed[q,3]-ms_fixed[q]/gamma)))},
        "measurement_scope":"Frozen modeled zone cuts; physical P32 meter correspondence and inherited numeric-as-MW interpretation are not certified. Residual differences are accounting identities, not causal diagnoses.",
        "source_input_vs_physical_gate_distinction":True,"new_PF_OPF_or_annual_run":False,"within_zone_or_impedance_scenario_executed":False,
        "old_inputs_and_artifacts_modified":False,"source_files_unchanged":True,
        "sources":[record(p) for p in inputs],"outputs":[record(p) for p in outputs],"analysis_script":record(Path(__file__))}
    (OUT/"accounting_identity_review.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"passed":True,"max_identity_error_model_MW":max(identity_errors.values()),"western":report["western_residual_statistics"],"Moses_bound":report["Moses_conditional_passivity_bound"]}))


if __name__=="__main__":main()
