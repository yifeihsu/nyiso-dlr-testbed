"""Seal metadata-only interface operators and validate their structural axes."""
from pathlib import Path
import csv
import hashlib
import json
from datetime import datetime, timezone
import numpy as np
from scipy.io import savemat
from interface_operator import ROOT, STATES, CONVENTIONS, source_case, interface_definitions, build_runtime_operator, apply_interface_flows


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = ROOT / "output/nygrid_2025_acpf_profile_audit/alignment"
    out.mkdir(parents=True, exist_ok=True)
    definitions = interface_definitions(); rows = []; checks = []; mat = {}
    source_paths = [ROOT / "output/nygrid_2025_downstate/replay/interface_definitions.json",
                    ROOT / "output/nygrid_2025_downstate/replay/interface_membership.csv",
                    ROOT / "output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat",
                    ROOT / "output/nygrid_2025_dover_parameters/network/x_nominal.mat"]
    with source_paths[1].open(newline="") as f:
        membership = list(csv.DictReader(f))
    for state in STATES:
        definitions = interface_definitions(state)
        full, zones, keys, source = source_case(state)
        zone_by_bus = {int(b): str(z) for b, z in zip(full["bus"][:, 0], zones)}
        coeff = np.zeros((len(definitions), len(full["branch"])))
        for j, d in enumerate(definitions):
            for signed in d["signed_parent_branch_rows"]:
                coeff[j, abs(signed) - 1] = np.sign(signed)
            # Independent zone crossing, restricted to active AC branches.
            independent = np.zeros(len(full["branch"]))
            for k, b in enumerate(full["branch"]):
                zf, zt = zone_by_bus[int(b[0])], zone_by_bus[int(b[1])]
                if b[10] and zf in d["source_zones"] and zt in d["target_zones"]: independent[k] = 1
                if b[10] and zt in d["source_zones"] and zf in d["target_zones"]: independent[k] = -1
            assert np.array_equal(coeff[j], independent), (state, d["interface"], "zone crossing mismatch")
            stored = full["if"]["map"]
            signed = stored[stored[:, 0] == d["inherited_interface_id"], 1].astype(int)
            assert sorted(signed.tolist()) == sorted(d["signed_parent_branch_rows"]), (state, "if.map mismatch")
            if state != "post_dover":
                historical = [r for r in membership if r["variant"] == "upgrades_dated" and r["state"] == f"refined_2025_{state}_case" and r["interface"] == d["interface"]]
                assert sorted(int(r["branch_row"]) * int(float(r["coefficient"])) for r in historical) == sorted(signed.tolist()), (state, "expanded membership CSV mismatch")
        if state == "post_dover":
            assert np.array_equal(coeff, source["recovery"]["full_interface_branch_matrix"])
        path = ROOT / f"output/nygrid_2025_ac_system/branches/{state}_branch_map.csv"
        source_paths.append(path)
        with path.open(newline="") as f: mapping = list(csv.DictReader(f))
        branch = np.zeros((len(mapping), 13)); parents = []
        for k, row in enumerate(mapping):
            assert int(row["runtime_branch_row"]) == k + 1
            branch[k, :2] = [int(row["from_bus"]), int(row["to_bus"])]
            branch[k, 10] = row["active"].lower() == "true"
            parents.append(int(row["original_branch_row"]))
        op = build_runtime_operator(branch, parents, state)
        for term in op["terms"]:
            first = mapping[term["first_runtime_branch_row"] - 1]
            last = mapping[term["last_runtime_branch_row"] - 1]
            assert first["physical_terminal_from"].lower() == "true"
            assert last["physical_terminal_to"].lower() == "true"
            term["first_runtime_branch_key"] = first["runtime_branch_key"]
            term["last_runtime_branch_key"] = last["runtime_branch_key"]
        # Synthetic terminal powers with strictly positive per-section loss.
        # This validates negative orientation and split-terminal selection.
        pf = np.arange(len(branch), dtype=float) + 2000
        pt = -pf + 0.1
        for parent in set(parents):
            candidates = [k for k, p in enumerate(parents) if p == parent]
            ordered = sorted(candidates, key=lambda k: int(mapping[k]["section_index"]))
            for previous, current in zip(ordered, ordered[1:]): pf[current] = -pt[previous]; pt[current] = -pf[current] + 0.1
        result = apply_interface_flows(pf, pt, op)
        expected_loss = np.array([sum(t["section_count"] * 0.1 for t in op["terms"] if t["interface"] == d["interface"]) for d in definitions])
        assert np.max(np.abs(result["oriented_source_minus_target_loss"] - expected_loss)) < 1e-9
        assert np.all(result[CONVENTIONS[0]] >= result[CONVENTIONS[2]] - 1e-8)
        assert np.all(result[CONVENTIONS[0]] <= result[CONVENTIONS[1]] + 1e-8)
        permutation = np.arange(len(branch))[::-1]
        permuted = build_runtime_operator(branch[permutation], np.asarray(parents)[permutation], state)
        perm_result = apply_interface_flows(pf[permutation], pt[permutation], permuted)
        assert all(np.allclose(result[k], perm_result[k]) for k in result)
        rows.extend(op["terms"])
        for convention, w in op["weights"].items():
            mat[f"{state}_{convention}_PF"] = w["PF"]
            mat[f"{state}_{convention}_PT"] = w["PT"]
        mat[f"{state}_branch_keys"] = np.asarray([r["runtime_branch_key"] for r in mapping], dtype=object)
        checks.append(dict(state=state, branch_count=len(branch), membership_terms=len(op["terms"]),
                           current_if_map_and_active_zone_crossing_match=True,
                           full_recovery_matrix_match=True if state == "post_dover" else None,
                           original_physical_terminals_verified=True, row_permutation_test_pass=True,
                           positive_loss_orientation_test_pass=True,
                           retired_211_coefficient=float(np.abs(coeff[:, 210]).max()),
                           dover_old_394_coefficient=float(np.abs(coeff[:, 393]).max()),
                           dover_new_413_coefficient=float(np.abs(coeff[:, 412]).max()) if len(keys) >= 413 else None))
    with (out / "interface_operator_terms.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    mat["interface_names"] = np.asarray([d["interface"] for d in definitions], dtype=object)
    savemat(out / "interface_operator_weights.mat", mat, do_compression=True)
    contract = dict(created_utc=datetime.now(timezone.utc).isoformat(),
        status="sealed_metadata_only_before_inspection_of_new_ACPF_interface_values",
        interpretation="legacy active NY-zone crossing diagnostics; exact physical P-32 correspondence unestablished",
        primary_convention=CONVENTIONS[0], alternative_conventions=list(CONVENTIONS[1:]),
        formulas={CONVENTIONS[0]: "sum(sign * PF_at_original_corridor_from_terminal)",
                  CONVENTIONS[1]: "sum(PF_first if sign>0 else PT_last)",
                  CONVENTIONS[2]: "sum(-PT_last if sign>0 else -PF_first)"},
        alternative_interpretation="diagnostic meter-convention sensitivity, not a confidence interval or a bound on true P-32 flow",
        conservation="oriented_source_side - oriented_target_side equals sum of included corridor active losses when internal section buses have no active injection or shunt conductance",
        public_unit_normalization="divide aggregate model MW by gamma; no gamma scaling of solved current or impedances",
        membership_basis="inherited seven zone cuts; independently checked against all four current full-case if.map and active zone crossings",
        forbidden_shortcuts=["no reduced DC H-theta coefficients", "no historical-parent positional padding", "no membership or orientation fitting to P-32 values"],
        p32_physical_flowgate_binding="unestablished", checks=checks,
        source_receipts=[dict(path=str(p.relative_to(ROOT)).replace('\\','/'), sha256=sha(p)) for p in source_paths])
    (out / "interface_operator_contract.json").write_text(json.dumps(contract, indent=2) + "\n")
    print(json.dumps(dict(output=str(out), state_checks=checks), indent=2))


if __name__ == "__main__": main()
