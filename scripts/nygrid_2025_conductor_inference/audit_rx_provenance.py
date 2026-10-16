"""Independently validate current section R/X and distinguish prior redesigns."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_conductor_inference"
STATES = ["pre_may", "may21", "may30", "post_dover"]
ABS_TOL, REL_TOL = 1e-10, 1e-8


def rec(path):
    with path.open("rb") as f: digest = hashlib.file_digest(f, "sha256").hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=digest)


def matches(a, b):
    return bool(abs(a-b) <= max(ABS_TOL, REL_TOL*abs(b)))


def forward(row, cat, base):
    nb, nc = int(row.bundle_count), int(row.circuits)
    assert nb == row.bundle_count and nc == row.circuits and nb > 0 and nc > 0
    ts, rs = [25., 75.], [cat.r_ac25_ohm_per_m, cat.r_ac75_ohm_per_m]
    if np.isfinite(cat.r_ac200_ohm_per_m):
        ts.append(200.); rs.append(cat.r_ac200_ohm_per_m)
    assert ts[0] <= row.reference_temperature_c <= ts[-1]
    resistance = np.interp(row.reference_temperature_c, ts, rs)
    def radius(single):
        if nb == 1: return single
        vertices = row.bundle_spacing_m/(2*np.sin(np.pi/nb))*np.exp(2j*np.pi*np.arange(nb)/nb)
        distances = np.abs(vertices[:, None]-vertices[None, :]); np.fill_diagonal(distances, single)
        return np.exp(np.log(distances).mean())
    gmr, capradius = radius(cat.gmr_m), radius(cat.diameter_m/2)
    assert row.gmd_m > max(gmr, capradius) and row.segment_length_m > 0
    zbase, omega = row.base_kv**2/base, 2*np.pi*60
    return np.array([resistance*row.segment_length_m/(nc*nb*zbase),
        omega*2e-7*np.log(row.gmd_m/gmr)*row.segment_length_m/(nc*zbase),
        nc*omega*2*np.pi*8.8541878128e-12*row.segment_length_m*zbase/np.log(row.gmd_m/capradius)])


def main():
    assignments_path = ROOT / "output/nygrid_2025_ac_system/branches/branch_assignments.csv"
    catalog_path = ROOT / "output/nygrid_2025_ac_system/engineering/thermal_conductors.csv"
    conflict_path = ROOT / "output/nygrid_2025_acpf_profile_audit/structure/overhead_cable_classification_conflicts.csv"
    reg = pd.read_csv(assignments_path, keep_default_na=False).set_index("branch_row")
    cat = pd.read_csv(catalog_path).set_index("catalog_id")
    conflicts = pd.read_csv(conflict_path).set_index("branch_row")
    redesigned = set(reg.index[reg.parameter_basis == "synthetic_positive_R_X_B_redesign_from_nominal_geometry_and_X_implied_length"])
    assert len(redesigned) == 58 and 224 in redesigned
    sources = [assignments_path, catalog_path, conflict_path, Path(__file__),
               ROOT / "scripts/nygrid_2025_conductor_inference/export_rx_provenance_inputs.m",
               OUT / "provenance_inputs/export_receipt.json"]
    all_parents, all_branches, all_segments, state_summary = [], [], [], []
    maxerr = np.zeros(3)
    for state in STATES:
        source = OUT / f"provenance_inputs/{state}.mat"; sources.append(source)
        d = loadmat(source, simplify_cells=True)
        assert d["snapshot_metadata"]["operating_case_not_solved"]
        branch, bus, parent = d["branch"], d["bus"], d["branch_parent_row"].astype(int)
        original = d["original_parent_branch"]
        segments = pd.DataFrame(d["thermal_segments"])
        legacy = pd.DataFrame(d["legacy_eligibility"]).set_index("original_parent_row")
        lookup = {int(b): k for k, b in enumerate(bus[:, 0])}
        predicted = np.array([forward(s, cat.loc[s.catalog_id], d["baseMVA"]) for s in segments.itertuples()])
        for j, field in enumerate(["forward_R_pu", "forward_X_pu", "forward_B_pu"]): segments[field] = predicted[:, j]
        grouped = segments.groupby("branch_row")[["forward_R_pu", "forward_X_pu", "forward_B_pu"]].sum()
        p_rows = []
        for p in range(1, len(original)+1):
            selected = np.flatnonzero(parent == p); sg = segments[segments.original_branch_row == p]
            r = reg.loc[p]; target = branch[selected, 2:5].sum(axis=0); imported = original[p-1, 2:5]
            active = bool((branch[selected, 10] > 0).all())
            samekv = all(bus[lookup[int(branch[k, 0])], 9] == bus[lookup[int(branch[k, 1])], 9] for k in selected)
            ordinary = samekv and np.isin(branch[selected, 8], [0, 1]).all() and (branch[selected, 9] == 0).all()
            supplied = len(sg) > 0 and set(selected+1) == set(sg.branch_row)
            errors = np.full(3, np.nan); match_rx = False; match_b = False
            if supplied:
                f = grouped.loc[selected+1].to_numpy(); e = np.abs(f-branch[selected, 2:5]); errors = e.max(axis=0)
                maxerr = np.maximum(maxerr, errors)
                match_rx = all(matches(f[j, k], branch[ix, k+2]) for j, ix in enumerate(selected) for k in [0, 1])
                match_b = all(matches(f[j, 2], branch[ix, 4]) for j, ix in enumerate(selected))
                for j, ix in enumerate(selected):
                    all_branches.append(dict(dated_state=state, original_parent_row=p, branch_row=int(ix+1),
                        branch_key=str(d["branch_keys"][ix]), target_R_pu=branch[ix, 2], target_X_pu=branch[ix, 3],
                        target_B_pu=branch[ix, 4], forward_R_pu=f[j, 0], forward_X_pu=f[j, 1], forward_B_pu=f[j, 2],
                        R_absolute_error_pu=e[j, 0], X_absolute_error_pu=e[j, 1], B_absolute_error_pu=e[j, 2],
                        runtime_segment_count=int((sg.branch_row == ix+1).sum()), R_X_forward_match=match_rx))
            imported_preserved = matches(target[0], imported[0]) and matches(target[1], imported[1])
            basis = "source_design" if r.classification == "design_based_overhead" else ("prior_engineering_redesigned_RX" if p in redesigned and p != 224 else "imported_model_RX")
            if p == 224: basis = "released_equivalent_RX_without_current_thermal_record"
            oh = r.classification in ["synthetic_overhead_corridor", "design_based_overhead"]
            conflict = p in conflicts.index
            eligible = bool(active and ordinary and oh and supplied and match_rx and not conflict)
            old = bool(legacy.loc[p, "research_screen_eligible"])
            reason = str(legacy.loc[p, "reason"])
            row = dict(dated_state=state, original_parent_row=p, branch_key=r.branch_key,
                classification=r.classification, source_role=r.source_role, prior_parameter_basis=r.parameter_basis,
                target_basis=basis, active=active, same_voltage_and_ordinary_tap=bool(ordinary),
                current_thermal_segment_count=len(sg), current_thermal_runtime_branch_count=sg.branch_row.nunique(),
                imported_R_pu=imported[0], imported_X_pu=imported[1], imported_B_pu=imported[2],
                current_parent_R_pu=target[0], current_parent_X_pu=target[1], current_parent_B_pu=target[2],
                imported_R_X_preserved=imported_preserved, prior_explicit_R_X_redesign=p in redesigned,
                maximum_R_forward_error_pu=errors[0], maximum_X_forward_error_pu=errors[1], maximum_B_forward_error_pu=errors[2],
                current_R_X_forward_match=match_rx, current_geometric_B_forward_match=match_b,
                positive_imported_B=bool(imported[2] > 0), imported_B_preserved=matches(target[2], imported[2]),
                current_B_to_positive_imported_B_ratio=float(target[2]/imported[2]) if imported[2] > 0 else np.nan,
                known_cable_corridor_evidence_conflict=conflict,
                cable_conflict_finding=conflicts.loc[p, "finding"] if conflict else "",
                cable_conflict_source_ids=conflicts.loc[p, "source_ids"] if conflict else "",
                cable_conflict_source_locator=conflicts.loc[p, "source_locator"] if conflict else "",
                synthetic_existing_model_RX_eligible=eligible, handoff_v1_eligible=old, handoff_v1_reason=reason,
                previously_excluded_only_by_source_role=eligible and not old and reason == "no_specific_historical_circuit_or_documented_line_design_provenance",
                installed_identity_required_for_synthetic_eligibility=False, geographic_chord_required=False,
                installed_asset_DLR_qualified=False)
            p_rows.append(row)
        parents = pd.DataFrame(p_rows).set_index("original_parent_row", drop=False)
        for j, s in segments.iterrows():
            p = int(s.original_branch_row); metadata = parents.loc[p]
            for field in ["target_basis", "source_role", "imported_R_X_preserved", "prior_explicit_R_X_redesign", "synthetic_existing_model_RX_eligible", "known_cable_corridor_evidence_conflict"]:
                segments.loc[j, field] = metadata[field]
            segments.loc[j, "dated_state"] = state
            segments.loc[j, "realization_id"] = f"{state}:parent{p}:runtime{int(s.branch_row)}:{s.segment_id}"
        segments.to_csv(OUT / f"runtime_segment_provenance_{state}.csv", index=False)
        all_segments.append(segments); all_parents.extend(p_rows)
        active_oh = parents[parents.current_thermal_segment_count > 0]
        accepted = parents[parents.synthetic_existing_model_RX_eligible]
        state_summary.append(dict(dated_state=state, current_OH_parents=len(active_oh),
            current_OH_runtime_branches=int(segments.branch_row.nunique()), current_OH_segments=len(segments),
            independently_RX_matched_parents=int(active_oh.current_R_X_forward_match.sum()),
            synthetic_eligible_parents=len(accepted), prior_handoff_eligible_parents=int(parents.handoff_v1_eligible.sum()),
            new_admissions_only_from_removing_source_role_gate=int(parents.previously_excluded_only_by_source_role.sum()),
            eligible_imported_RX_preserved=int(accepted.imported_R_X_preserved.sum()),
            eligible_prior_engineered_RX=int((~accepted.imported_R_X_preserved).sum())))
    parent_table = pd.DataFrame(all_parents)
    current_oh = parent_table[parent_table.current_thermal_segment_count > 0]
    all_rx_matched = bool(current_oh.current_R_X_forward_match.all())
    all_geometric_b_matched = bool(current_oh.current_geometric_B_forward_match.all())
    assert len(current_oh) > 0 and all_rx_matched, "Current runtime R/X reconstruction failed"
    assert all_geometric_b_matched, "Current runtime geometric B reconstruction failed"
    parent_table.to_csv(OUT / "all_parent_parameter_provenance.csv", index=False)
    pd.DataFrame(all_branches).to_csv(OUT / "runtime_branch_RXB_forward_validation.csv", index=False)
    pd.DataFrame(state_summary).to_csv(OUT / "provenance_coverage_by_state.csv", index=False)
    parent_table[parent_table.original_parent_row.isin([224,300,309,310,386])].to_csv(OUT / "special_parent_provenance.csv", index=False)
    coverage = parent_table[parent_table.current_thermal_segment_count > 0].groupby(["dated_state", "classification", "source_role", "target_basis"]).agg(
        parents=("original_parent_row", "size"), RX_matched=("current_R_X_forward_match", "sum"), eligible=("synthetic_existing_model_RX_eligible", "sum"),
        imported_RX_preserved=("imported_R_X_preserved", "sum"), positive_imported_B=("positive_imported_B", "sum"), imported_B_preserved=("imported_B_preserved", "sum")).reset_index()
    coverage.to_csv(OUT / "provenance_coverage_by_class.csv", index=False)
    inverse_path = OUT / "inverse_target_summary.csv"; inverse = pd.read_csv(inverse_path)
    imported = inverse[inverse.target_basis == "imported_RX"]
    restorations = imported[(imported.original_parent_row.isin(redesigned)) & (imported.candidate_count > 0)]
    assert len(imported) == 186 and (imported.candidate_count > 0).sum() == 141 and len(restorations) == 13
    restorations.to_csv(OUT / "prior_redesign_imported_RX_restoration_candidates.csv", index=False)
    sources += [inverse_path, OUT / "inverse_search_receipt.json"]
    outputs = [OUT / n for n in ["all_parent_parameter_provenance.csv", "runtime_branch_RXB_forward_validation.csv", "provenance_coverage_by_state.csv", "special_parent_provenance.csv", "provenance_coverage_by_class.csv", "prior_redesign_imported_RX_restoration_candidates.csv"]]
    outputs += [OUT / f"runtime_segment_provenance_{state}.csv" for state in STATES]
    summary = dict(passed=all_rx_matched and all_geometric_b_matched, created_utc=datetime.now(timezone.utc).isoformat(), baseline_commit="51e424a139e0d0ec42fcbbb35749deaf119cffc2",
        scope="Independent current runtime R/X/B arithmetic and imported-versus-engineered parameter provenance; no annual replay or prior modification",
        PF_or_OPF_run=False, states=state_summary,
        maximum_runtime_R_X_B_errors_pu=dict(zip(["R", "X", "B"], maxerr.tolist())),
        all_current_runtime_RX_checks_pass=all_rx_matched,
        all_current_runtime_geometric_B_checks_pass=all_geometric_b_matched,
        tolerance=dict(absolute_pu=ABS_TOL, relative=REL_TOL),
        prior_OH_parent_classifications=186, prior_exact_RX_inverse_parents=125, prior_source_design_parents=3, prior_explicit_RX_redesign_parents=58,
        latest_removed_redesign_parent224=True, source_identity_and_geographic_chord_not_eligibility_requirements=True,
        B_consistency_is_separate_from_RX_acceptance=True, positive_B_not_asserted_to_be_verified_pure_line_charging=True,
        original_imported_RX_search_feasible_parents=141, restoration_candidate_parents=restorations.original_parent_row.astype(int).tolist(),
        root_search_scope="No geographic chord requirement; inherited 250/500/700/1000 km voltage-class caps, 14 catalog conductors, fixed reference temperature, integer circuits 1..4",
        three220kV_extended_length_only_parents=[152,163,164],
        inferred_candidates_applied_to_frozen_models=False, installed_asset_identity_or_operating_feasibility_claimed=False,
        important_distinction="Current engineered R/X can match a conductor exactly even where 58 prior overhead rows changed imported R/X. A current fit is not proof of imported parameter preservation.",
        sources=[rec(p) for p in sources], outputs=[rec(p) for p in outputs])
    (OUT / "provenance_and_runtime_RXB_review.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"passed":True,"states":state_summary,"max_errors":summary["maximum_runtime_R_X_B_errors_pu"]}))


if __name__ == "__main__": main()
