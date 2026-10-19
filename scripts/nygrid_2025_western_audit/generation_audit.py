"""Source-only Niagara generation and landing audit; no dispatch/model edits.

Reproduces the frozen hydro projection, separates monthly net/gross/pumping
quantities, compares targeted early/final EIA923 records, and emits a reviewed
coarse Lewiston landing proposal. Internal interface observations are not read.
"""
from __future__ import annotations

import calendar
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import openpyxl
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_western_audit/generation"
GEN = ROOT / "output/nygrid_2025_inputs/generation_source"
DISPATCH = ROOT / "output/nygrid_2025_dispatch/dispatch"
FLEET = ROOT / "output/nygrid_2025_moses_audit/corrected/fleet/fleet_register.csv"
REGISTER = ROOT / "output/nygrid_2025_moses_audit/corrected/model_generator_register.csv"
PRIOR = ROOT / "output/nygrid_2025_dispatch/priors/dispatch_priors.npz"
EARLY = ROOT / "tmp/nonfossil_sources/eia923_2025/EIA923_Schedules_2_3_4_5_M_12_2025_Early_Release_30JUN2026.xlsx"
FINAL = OUT / "sources/EIA923_Schedules_2_3_4_5_M_12_2025_Final.xlsx"
GOLD = ROOT / "output/nygrid_2025_dispatch/fleet/source_scope/2025_Gold_Book.pdf"
GOLD_TEXT = ROOT / "output/nygrid_2025_moses_audit/generation/goldbook2025_layout.txt"
PARENT = ROOT / "output/nygrid_2025_dispatch/fleet/source_parent"
PHYSICAL = OUT / "sources/NYISO_Niagara_Model_20180724.pdf"
TARGETS = [2691, 2692, 2693]
SHEETS = ["Page 1 Generation and Fuel Data", "Page 1 Energy Storage"]


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def save_json(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def workbook_rows(path, include_state=False):
    """Header-based extraction; early release adds a leading warning column."""
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows, state = [], []
    for sheet in SHEETS:
        head = None
        for line, values in enumerate(workbook[sheet].iter_rows(values_only=True), 1):
            normalized = [" ".join(str(x).split()) if x is not None else "" for x in values]
            if "Plant Id" in normalized:
                head = normalized
                continue
            if head is None:
                continue
            row = dict(zip(head, values))
            pid = row.get("Plant Id")
            target = pid in TARGETS
            selected = include_state and row.get("Plant State") == "NY" and row.get("Reported Fuel Type Code") == "WAT"
            if not (target or selected):
                continue
            for month in range(1, 13):
                suffix = calendar.month_name[month]
                record = dict(workbook=path.name, sheet=sheet, excel_row=line, plant_id=int(pid),
                    plant_name=row["Plant Name"], operator=row["Operator Name"],
                    balancing_authority=row["Balancing Authority Code"], prime_mover=row["Reported Prime Mover"],
                    respondent_frequency=row["Respondent Frequency"], month=month,
                    net_generation_mwh=float(row["Netgen " + suffix]),
                    gross_generation_mwh=float(row["Grossgen " + suffix]) if sheet.endswith("Storage") else np.nan,
                    pumping_energy_mwh=float(row["Quantity " + suffix]) if sheet.endswith("Storage") else np.nan)
                if target:
                    rows.append(record)
                if selected:
                    state.append(record)
    workbook.close()
    return pd.DataFrame(rows), pd.DataFrame(state)


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    dependencies = [FLEET, REGISTER, PRIOR, DISPATCH / "dispatch.mat", DISPATCH / "dispatch_bounds.mat",
        GEN / "eia923_monthly_hydro_2025.csv", GEN / "eia860_nonfossil_inventory_2025.csv",
        GEN / "hydro_monthly_plant_allocation_register.csv", GEN / "statewide_fuelmix_hourly.csv",
        ROOT / "output/nygrid_2025_dispatch/priors/nonfossil_to_fleet_allocation.csv",
        EARLY, FINAL, GOLD, GOLD_TEXT, PHYSICAL,
        PARENT / "npcc.csv", PARENT / "nygrid_full_updateOpCond.m",
        ROOT / "scripts/nygrid_2025_inputs/generation_priors.py",
        ROOT / "build_compact_nonfossil_generation_inputs.py",
        ROOT / "scripts/nygrid_2025_dispatch/build_fleet.py",
        ROOT / "scripts/nygrid_2025_dispatch/build_dispatch_priors.py", Path(__file__)]
    dependencies += sorted(GEN.glob("hydro_plant_priors_*.npz"))
    initial = {p: sha(p) for p in dependencies}
    require(sha(FINAL) == "95684212d89ac688a355a5c8b51935111247e6f60716eba250464b28d14cfd2c", "Final source workbook changed")
    require(sha(PHYSICAL) == "7ace05f9231540b218add162fbe70398b649bd4089fc350f062d81e067178396", "Niagara physical-group source changed")
    early, _ = workbook_rows(EARLY)
    final, state = workbook_rows(FINAL, include_state=True)
    early.to_csv(OUT / "target_EIA923_early_monthly.csv", index=False)
    final.to_csv(OUT / "target_EIA923_final_monthly.csv", index=False)
    state.to_csv(OUT / "final_EIA923_NY_hydro_scope.csv", index=False)
    keys = ["sheet", "plant_id", "month"]
    require(not early.duplicated(keys).any() and not final.duplicated(keys).any(), "Duplicated target monthly source rows")
    joined = early.merge(final, on=keys, suffixes=("_early", "_final"), validate="one_to_one")
    changes = []
    for row in joined.itertuples():
        for field in ["net_generation_mwh", "gross_generation_mwh", "pumping_energy_mwh"]:
            a, b = getattr(row, field + "_early"), getattr(row, field + "_final")
            if np.isnan(a) and np.isnan(b):
                continue
            changes.append(dict(sheet=row.sheet, plant_id=row.plant_id, month=row.month, quantity=field,
                early_value_mwh=a, final_value_mwh=b, difference_mwh=b - a,
                early_excel_row=row.excel_row_early, final_excel_row=row.excel_row_final))
    change = pd.DataFrame(changes)
    change.to_csv(OUT / "EIA923_target_vintage_comparison.csv", index=False)
    require(np.max(abs(change.difference_mwh)) == 0, "Target vintage values changed; further review required")
    storage = final[final.sheet.eq(SHEETS[1])]
    require(np.max(abs(storage.gross_generation_mwh - storage.pumping_energy_mwh - storage.net_generation_mwh)) == 0,
            "Gross-pumping-net source identity fails")
    storage.to_csv(OUT / "pumped_storage_gross_pumping_net_monthly.csv", index=False)

    fleet = pd.read_csv(FLEET, dtype={"eia_generator_id": str}, keep_default_na=False)
    register = pd.read_csv(REGISTER, dtype={"eia_generator_id": str}, keep_default_na=False)
    register["plant_id"] = pd.to_numeric(register.plant_id, errors="coerce")
    require(fleet.device_key.is_unique and not fleet.duplicated(["plant_id", "eia_generator_id"]).any(), "Fleet duplicate")
    require(register.device_key.is_unique and register.gen_row.tolist() == list(range(1, len(register) + 1)), "Model identity duplicate")
    prior = np.load(PRIOR, allow_pickle=False)
    require(np.array_equal(prior["fleet_id"], fleet.fleet_id), "Prior fleet axis differs")
    d = loadmat(DISPATCH / "dispatch.mat", simplify_cells=True, variable_names=["dispatch_qualified", "gen_pg", "gamma", "timestamp_utc"])
    q = np.asarray(d["dispatch_qualified"], bool)
    gamma = float(d["gamma"])
    time = pd.DatetimeIndex(pd.to_datetime(np.asarray(d["timestamp_utc"]).astype(str), utc=True)).tz_convert("America/New_York")
    source = pd.read_csv(GEN / "eia923_monthly_hydro_2025.csv")
    require(not source.duplicated(["plant_id", "prime_mover", "month"]).any(), "Hydro source plant/prime-mover/month duplicate")
    monthly = pd.read_csv(GEN / "hydro_monthly_plant_allocation_register.csv")
    require(not monthly.duplicated(["month", "plant_id", "prime_mover"]).any(), "Hydro register duplicated")
    p63 = pd.read_csv(GEN / "statewide_fuelmix_hourly.csv")
    p63 = p63[p63.fuel_category.eq("Hydro")].sort_values("hour_index").reset_index(drop=True)
    require(np.array_equal(p63.hour_index, np.arange(1, 8761)), "Hydro source hour axis differs")
    parent = pd.read_csv(PARENT / "npcc.csv")
    plants, plant_hour = [], {}
    for pid in TARGETS + [2568, 2623]:
        fi = np.flatnonzero(fleet.plant_id.eq(pid)); gi = np.flatnonzero(register.plant_id.eq(pid))
        require(len(gi) == {2691: 4, 2692: 11, 2693: 13, 2568: 3, 2623: 2}[pid], "Target admitted model unit count differs")
        p = prior["prior_actual_mw"][:, fi].sum(axis=1)
        pg = d["gen_pg"][:, gi].sum(axis=1) / gamma
        plant_hour[pid] = (p, pg)
        rows = fleet.iloc[fi]
        plants.append(dict(plant_id=pid, plant_name=str(rows.plant_name.iloc[0]), inventory_units=len(fi), admitted_units=len(gi),
            source_statuses="|".join(sorted(set(rows.source_status))), prior_mean_on_dispatch_hours_mw=float(p[q].mean()),
            dispatch_mean_on_dispatch_hours_mw=float(pg[q].mean()), dispatch_min_mw=float(pg[q].min()), dispatch_max_mw=float(pg[q].max()),
            bounded_adjustment_mean_mw=float((pg[q] - p[q]).mean()), qualified_energy_mwh=float(pg[q].sum()),
            qualified_hours=int(q.sum()), all_year_energy_complete=False,
            inventory_summer_mw=float(rows.summer_capacity_mw.sum()), inventory_winter_mw=float(rows.winter_capacity_mw.sum()),
            admitted_summer_mw=float(rows[rows.fleet_id.isin(register.fleet_id)].summer_capacity_mw.sum()),
            frozen_buses="|".join(str(int(v)) for v in sorted(set(rows.bus_id))),
            frozen_bus_names="|".join(sorted(set(rows.parent_bus_name))), zone="|".join(sorted(set(rows.zone)))))
    pd.DataFrame(plants).to_csv(OUT / "plant_summary.csv", index=False)
    unit_columns = ["fleet_id", "device_key", "plant_id", "plant_name", "eia_generator_id", "prime_mover", "source_status",
        "zone", "bus_id", "parent_bus_name", "mapping_method", "nameplate_capacity_mw", "summer_capacity_mw", "winter_capacity_mw",
        "dispatch_eligible_default", "pumped_hydro_prior_eligible", "legacy_source_gen_rows", "source_excel_row", "source_sha256"]
    fleet[fleet.plant_id.isin(TARGETS)][unit_columns].to_csv(OUT / "Niagara_and_Gilboa_unit_inventory.csv", index=False)
    hydro_checks, reconciliation, plant_month = [], [], []
    for month in range(1, 13):
        reg = monthly[monthly.month.eq(month)].sort_values("column_index")
        saved = np.load(GEN / f"hydro_plant_priors_{month:02d}.npz")
        ix = saved["hour_index"].astype(int) - 1
        require(np.array_equal(ix, np.flatnonzero(time.month == month)), "Hydro month physical-hour membership differs")
        require(np.array_equal(reg.column_index, np.arange(len(reg))), "Hydro column identities differ")
        values = saved["prior_actual_mw"]
        total = p63.generation_mw.to_numpy(float)[ix]
        good = np.isfinite(values).all(axis=1)
        require(np.array_equal(good, p63.coverage_qualified.to_numpy(bool)[ix]), "P63 hydro mask differs")
        cap = reg.capability_mw.to_numpy(float); base = np.minimum(reg.baseline_mw, cap).to_numpy(float)
        below = total <= base.sum()
        low = total[:, None] / base.sum() * base
        high = base + ((total - base.sum()) / (cap.sum() - base.sum()))[:, None] * (cap - base)
        calculated = np.where(below[:, None], low, high)
        err = float(np.max(abs(calculated[good] - values[good])))
        require(err < 1e-8, "Declared bounded hydro projection does not reproduce saved values")
        require(np.max(abs(values[good].sum(axis=1) - total[good])) < 1e-7, "Hydro P63 conservation failed")
        unit_error = 0.
        for pid in TARGETS:
            col = np.flatnonzero(reg.plant_id.eq(pid)); require(len(col) == 1, "Target plant column missing/duplicate")
            fi = np.flatnonzero(fleet.plant_id.eq(pid))
            unit_error = max(unit_error, float(np.max(abs(prior["prior_actual_mw"][np.ix_(ix[good], fi)].sum(axis=1) - values[good, col[0]]))))
            require(unit_error < 1e-8, "Plant-to-unit prior duplicated or lost generation")
        rm = int(np.flatnonzero(reg.plant_id.eq(2693))[0])
        down = np.where(below, base[rm] * (total / base.sum() - 1), 0.)
        up = np.where(~below, (total - base.sum()) / (cap.sum() - base.sum()) * (cap[rm] - base[rm]), 0.)
        require(np.max(abs(base[rm] + down[good] + up[good] - values[good, rm])) < 1e-8, "Niagara projection decomposition failed")
        physical_hours = len(ix); nominal_hours = 24 * calendar.monthrange(2025, month)[1]
        hys = state[state.month.eq(month) & state.sheet.eq(SHEETS[0]) & state.prime_mover.eq("HY")]
        pss = state[state.month.eq(month) & state.sheet.eq(SHEETS[1])]
        reconciliation.append(dict(month=month, physical_month_hours=physical_hours, EIA_mean_denominator_hours=nominal_hours,
            P63_qualified_hours=int(good.sum()), P63_hydro_mean_mw=float(total[good].mean()),
            frozen_selected_HY_baseline_sum_mw=float(reg.baseline_mw.sum()), frozen_clipped_baseline_sum_mw=float(base.sum()),
            baseline_sum_is_official_state_total=False,
            final_EIA_NY_HY_net_mean_mw=float(hys.net_generation_mwh.sum() / nominal_hours),
            final_EIA_NYIS_HY_net_mean_mw=float(hys.loc[hys.balancing_authority.eq("NYIS"), "net_generation_mwh"].sum() / nominal_hours),
            final_EIA_PS_gross_mean_mw=float(pss.gross_generation_mwh.sum() / nominal_hours),
            final_EIA_PS_pumping_mean_mw=float(pss.pumping_energy_mwh.sum() / nominal_hours),
            final_EIA_PS_net_mean_mw=float(pss.net_generation_mwh.sum() / nominal_hours),
            allocated_PS_positive_mean_mw=float(values[good][:, reg.prime_mover.eq("PS")].sum(axis=1).mean()),
            below_baseline_fraction=float(below[good].mean()),
            Robert_Moses_baseline_mw=float(base[rm]), Robert_Moses_prior_P63_hour_mean_mw=float(values[good, rm].mean()),
            Robert_Moses_below_baseline_mean_contribution_mw=float(down[good].mean()),
            Robert_Moses_above_baseline_mean_contribution_mw=float(up[good].mean()),
            P63_net_or_positive_pumping_basis_independently_verified=False))
        hydro_checks.append(dict(month=month, compared_plant_hours=int(good.sum() * len(reg)),
            projection_max_error_mw=err, plant_to_unit_conservation_max_error_mw=unit_error))
        for pid in TARGETS:
            mask = q & (time.month == month); p, pg = plant_hour[pid]
            eia = source[source.plant_id.eq(pid) & source.month.eq(month)]
            require(len(eia) == 1, "Source plant/month identity missing")
            plant_month.append(dict(plant_id=pid, month=month, qualified_hours=int(mask.sum()), physical_month_hours=physical_hours,
                EIA_month_net_generation_mwh=float(eia.net_generation_mwh.iloc[0]),
                EIA_calendar_mean_net_mw=float(eia.monthly_mean_net_mw.iloc[0]),
                prior_qualified_mean_mw=float(p[mask].mean()), dispatch_qualified_mean_mw=float(pg[mask].mean()),
                prior_qualified_energy_mwh=float(p[mask].sum()), dispatch_qualified_energy_mwh=float(pg[mask].sum()),
                monthly_energy_constraint_enforced=False, EIA_net_and_positive_PS_dispatch_are_same_quantity=pid != 2692 and pid != 2691))
    pd.DataFrame(hydro_checks).to_csv(OUT / "projection_reproduction_checks.csv", index=False)
    pd.DataFrame(reconciliation).to_csv(OUT / "monthly_P63_EIA_projection_reconciliation.csv", index=False)
    pd.DataFrame(plant_month).to_csv(OUT / "Niagara_Gilboa_monthly_prior_dispatch.csv", index=False)
    np.savez_compressed(OUT / "target_plant_hourly_audit.npz", timestamp_utc=np.asarray(d["timestamp_utc"]).astype(str),
        dispatch_qualified=q, plant_ids=np.array(TARGETS), prior_public_mw=np.column_stack([plant_hour[p][0] for p in TARGETS]),
        dispatch_public_mw=np.column_stack([plant_hour[p][1] for p in TARGETS]))

    # Source-backed project/voltage correction, with explicit coarse destination.
    bus55 = parent[parent.idx.eq(55)].iloc[0]
    require(bus55["name"] == "NIAGARA E" and bus55.Vn == 230 and bus55.zone == "A", "Canonical Niagara aggregate anchor changed")
    legacy_text = (PARENT / "nygrid_full_updateOpCond.m").read_text()
    require("Bus 55: zone A, Niagara" in legacy_text, "Legacy anchor not explicitly Niagara")
    lewiston = fleet[fleet.plant_id.eq(2692)]
    require(len(lewiston) == 12 and lewiston.bus_id.eq(57).all() and lewiston.zone.eq("A").all(), "Lewiston repair scope changed")
    candidate = []
    for row in lewiston.itertuples():
        candidate.append(dict(fleet_id=row.fleet_id, device_key=row.device_key, plant_id=2692,
            eia_generator_id=row.eia_generator_id, source_status=row.source_status,
            old_zone="A", new_zone="A", old_bus_id=57, new_bus_id=55,
            old_bus_name="HUNTLEY", old_bus_kv=115, new_bus_name="NIAGARA E", new_bus_kv=230,
            new_mapping_method="NYISO_Niagara230_group_to_declared_existing_Niagara_project_bus55_proxy",
            new_bus_landing_proxy=1, physical_terminal_ID_claim=False,
            correction_basis="NYISO2018p3_Lewiston_at_Niagara230;GoldBook2025p86_same_project_PTID23760;legacy_builder_explicit_Niagara_bus55",
            per_unit_PG_capacity_status_admission_and_priors_must_remain_unchanged=True,
            within_zone_A_cut_interface_flow_change_at_fixed_injections=0))
    pd.DataFrame(candidate).to_csv(OUT / "Lewiston_candidate_landing_correction.csv", index=False)
    gold_pages = GOLD_TEXT.read_text(encoding="utf-8").split("\f")
    lines = []
    for page_no, page in enumerate(gold_pages, 1):
        for line in page.splitlines():
            if any(name in line for name in ["Lewiston PS (Fleet)", "Moses Niagara (Fleet)", "Glenwood 1", "Glenwood 2", "Glenwood 3", "Waterport 1", "Waterport 2"]):
                lines.append(dict(pdf_page=page_no, source_text=line.strip(), energy_column_year=2024, capability_column_year=2025))
    pd.DataFrame(lines).to_csv(OUT / "GoldBook_station_evidence.csv", index=False)
    save_json("source_interpretation.json", dict(
        primary_Niagara_groups_source="https://www.nyiso.com/documents/20142/2181113/Enhancements%20to%20the%20Niagara%20Model%20vJuly24_2018vFINAL.pdf/9340e3b7-26a6-813a-0998-e1252622d1d1",
        primary_Niagara_groups_pdf_page=3, visually_verified_pages=["Niagara_Model_page3", "GoldBook2025_page86"],
        physical_groups=[dict(bus="Niagara230", main_units=6, Lewiston_units=12), dict(bus="Niagara115East", main_units=4), dict(bus="Niagara115West", main_units=3)],
        physical_group_unit_ID_crosswalk_and_hourly_dispatch_available=False,
        presentation_historical_capacity_numbers_not_used_as_2025_limits=True,
        PERFORM_limitation="Historical case assigns all RobertMoses units to a345kV deadend and Lewiston to115kV; it does not resolve the officially described physical groups.",
        GoldBook_energy_values_are_2024_not_2025=True,
        Lewiston_mapping_rule="Move EIA2692 inventory from Huntley115 proxy57 to existing explicit Niagara230 project proxy55; retain all quantities. No exact physical terminal claim.",
        within_A_relocation_changes_internal_loading_but_not_A_boundary_net_flow_at_fixed_other_injections=True,
        monthly_generation_recommendation="Preserve frozen declared hydro projection; no confirmed numerical or unit-duplication defect found. No monthly-energy hard constraint or gross-PS substitution promoted.",
        EIA923_final_verified_release="2026-09-14", EIA923_final_catalog="https://www.eia.gov/electricity/data/eia923/",
        EIA923_final_download_receipt="sources/f923_2025_final.receipt.json",
        monthly_scope_warning="P63 hourly Hydro net-versus-positive-storage and load pumping boundary have not been independently reconciled. Source gross, net and pumping are distinct quantities.",
        contract_shares="No customer entitlement multiplier is applied. EIA records identify NYPA and NYIS for both plants. Commercial sales allocation does not establish physical unit dispatch.",
        public_hourly_search=dict(plant_electrical_dispatch_located=False,
            searched_primary_domains=["nypa.gov", "ijc.org", "eia.gov", "nyiso.com"],
            NIAGARA_project_source="https://www.nypa.gov/power/generation/niagara-power-project",
            storage_operation_source="https://www.nypa.gov/news/press-releases/2018/20181101-lewiston",
            hydrology_scope="Public water-level/diversion information and historical reports do not identify2025 hourly electrical output, pumping, unit availability or physical three-bus dispatch; no conversion to MW performed.",
            no_claim_that_unlocated_data_do_not_exist=True)))
    unchanged = all(sha(p) == initial[p] for p in dependencies)
    require(unchanged, "Frozen dependency changed during generation audit")
    pd.DataFrame([dict(path=p.relative_to(ROOT).as_posix(), sha256=initial[p]) for p in dependencies]).to_csv(OUT / "source_manifest.csv", index=False)
    result = dict(passed=True, completed_utc=datetime.now(timezone.utc).isoformat(),
        head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        dispatch_qualified_hours=int(q.sum()), EIA_target_early_final_quantity_comparisons=len(change),
        EIA_target_early_final_differences=int(np.count_nonzero(change.difference_mwh)),
        projection_max_error_mw=max(r["projection_max_error_mw"] for r in hydro_checks),
        plant_to_unit_conservation_max_error_mw=max(r["plant_to_unit_conservation_max_error_mw"] for r in hydro_checks),
        duplicate_fleet_units=0, duplicate_plant_prime_mover_month_rows=0,
        Niagara_plants=[r for r in plants if r["plant_id"] in [2692, 2693]],
        confirmed_Lewiston_project_voltage_mismatch=True, proposed_destination_is_declared_coarse_proxy=True,
        Lewiston_inventory_rows=12, Lewiston_active_model_rows=11,
        confirmed_dispatch_quantity_fix=False, monthly_energy_change_promoted=False,
        old_outputs_or_builders_modified=False, all_frozen_hashes_unchanged=unchanged,
        internal_interface_observations_read=False, annual_power_flow_run=False)
    save_json("generation_audit.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
