"""Read back one finished month before annual scoring; never claim full-year completion."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

import score_revised_profiles as scorer


def main(path):
    contract_path = scorer.BASE / "comparison_contract.json"
    contract = json.loads(contract_path.read_text())
    scorer.enforce_receipts(contract["source_receipts"])
    cohort = pd.read_csv(scorer.BASE / "frozen_comparison_cohort.csv")
    m = loadmat(path, simplify_cells=True, variable_names=scorer.READ_FIELDS)
    assert set(scorer.READ_FIELDS) <= set(m)
    h = scorer.vector(m, "hour_index", int); ix = h - 1
    assert np.array_equal(scorer.vector(m, "timestamp_utc", str), cohort.timestamp_utc.to_numpy(str)[ix])
    assert np.array_equal(scorer.vector(m, "source_qualified", bool), cohort.frozen_source_qualified.to_numpy(bool)[ix])
    assert (str(m["impedance_mode"]), str(m["loss_mode"])) == scorer.VARIANT_OPTIONS["combined"]
    month = pd.to_datetime(cohort.timestamp_utc.iloc[ix], utc=True).dt.tz_convert("America/New_York").dt.month.unique()
    assert len(month) == 1
    old_path = scorer.FROZEN / f"acpf/monthly/profile_PF_2025_{month[0]:02d}.mat"
    old = loadmat(old_path, simplify_cells=True)
    good = np.logical_and.reduce([scorer.vector(m, f, bool) for f in ["source_qualified", "PF_converged", "AC_equation_gate", "loss_allocation_gate", "reduction_and_equation_gate"]])
    assert good.any()
    for f in ["branch_present", "branch_active", "bus_present"]:
        assert np.array_equal(np.asarray(m[f], bool)[good], np.asarray(old[f], bool)[good])
    for f in scorer.AXES + ["DC_from_bus", "DC_to_bus"]:
        assert np.array_equal(np.asarray(m[f]), np.asarray(old[f]))
    landing_path = scorer.ROOT / "output/nygrid_2025_western_audit/replay/dated_combined.mat"
    landing = loadmat(landing_path, simplify_cells=True, variable_names=["corrected_generator_buses"])["corrected_generator_buses"]
    assert np.array_equal(scorer.vector(m, "generator_bus_id", int), landing)
    values, budget, imports = scorer.reconstruct(m, cohort.dated_state.to_numpy(str)[ix], good, contract["gamma"], contract["interface_names"])
    for c in scorer.CONVENTIONS: assert np.isfinite(values[c][good]).all()
    operating = loadmat(scorer.ROOT / "output/nygrid_2025_inputs/model/operating_inputs.mat", simplify_cells=True, variable_names=["zonal_load_model_mw", "base_case"])
    baseline = loadmat(scorer.ROOT / "output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat", simplify_cells=True, variable_names=["actual_regional_import_public_mw", "gen_pg"])
    shares = pd.read_csv(scorer.ROOT / "output/nygrid_2025_western_audit/dispatch/all_boundary_external_generator_shares.csv").sort_values("model_gen_row_1based")
    cap = operating["base_case"]["gen"][shares.parent_gen_row.to_numpy(int) - 1]
    ext_pg = np.asarray(m["external_gen_PG"])[good]
    checks = {
        "independent_loss_budget_error_model_MW": scorer.maxabs(budget[good] - np.asarray(m["actual_budget_MW"])[good]),
        "NY_gross_target_vs_source_error_model_MW": scorer.maxabs(np.asarray(m["NY_gross_target_MW"])[good] - operating["zonal_load_model_mw"][ix[good]]),
        "NY_gross_served_plus_loss_closure_model_MW": scorer.maxabs(np.asarray(m["NY_served_PD_MW"])[good] + budget[good, :11] - operating["zonal_load_model_mw"][ix[good]]),
        "regional_NY_terminal_import_vs_source_error_model_MW": scorer.maxabs(imports[good] - baseline["actual_regional_import_public_mw"][ix[good], :3] * contract["gamma"]),
        "native_per_unit_PG_delta_audit_model_MW": scorer.maxabs(scorer.vector(m, "native_PG_change_from_original_MW")[good]),
        "external_original_P_bound_violation_model_MW": float(np.maximum(0, np.maximum(cap[:, 9] - ext_pg, ext_pg - cap[:, 8])).max()),
        "HQ_PG_delta_audit_model_MW": scorer.maxabs(scorer.vector(m, "HQ_PG_change_from_original_MW")[good]),
        "six_controlled_transfer_P_delta_model_MW": max(scorer.maxabs(np.asarray(m[f])[good] - np.asarray(old[f])[good]) for f in ["DC_PF", "DC_PT"]),
    }
    assert max(checks.values()) < contract["comparison_tolerance_model_MW"], checks
    scorer.enforce_receipts(contract["source_receipts"])
    report = dict(passed=True, created_utc=datetime.now(timezone.utc).isoformat(), scope="One finished monthly export readback, not completed annual scoring",
                  annual_comparison_complete=False, month=int(month[0]), hour_positions=len(h), source_qualified_hours=int(scorer.vector(m, "source_qualified", bool).sum()),
                  revised_comparison_qualified_hours=int(good.sum()), checks=checks,
                  matched_frozen_dated_axes_and_topology=True, corrected_generator_landing_axis_verified=True,
                  source_receipts=[scorer.record(p) for p in [Path(__file__), Path(scorer.__file__), contract_path, path, old_path, landing_path]])
    out = scorer.BASE / f"month_{month[0]:02d}_export_readback.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("monthly_file", type=Path)
    args = parser.parse_args(); main(args.monthly_file.resolve())
