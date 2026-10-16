"""Audit source semantics and write the declared AC loss-accounting contract.

This does not change operating inputs, generation profiles, or model parameters.
Run from any directory with Python, scipy, numpy, and pandas installed.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output/nygrid_2025_ac_loss_revision/policy_evidence"
SOURCE = OUT / "sources"


def receipt(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def json_write(name: str, value: dict) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    definitions = [
        ("NYISO_Market_Participants_User_Guide", "NYISO", "18.0", "2026-09-18",
         "Actual loads are\ncalculated as generation plus net interchange for each zone"),
        ("NYISO_Transmission_and_Dispatch_Operations_Manual", "NYISO", "11.0", "2026-07-31",
         "The load forecast does not include an estimate of zonal transmission losses."),
        ("EIA930_current_instructions", "EIA", "OMB expiration 2029-07-31", None,
         "the sum of demand and net metered tie line flow is expected to equal net generation"),
    ]
    archived_sources = []
    for stem, publisher, version, effective, signature in definitions:
        pdf, txt = SOURCE / (stem + ".pdf"), SOURCE / (stem + ".txt")
        r = json.loads((SOURCE / (stem + ".receipt.json")).read_text())
        assert receipt(pdf)["sha256"] == r["sha256"]
        assert pdf.stat().st_size == r["bytes"] and pdf.read_bytes().startswith(b"%PDF")
        normalized = " ".join(txt.read_text(encoding="utf-8").split())
        assert " ".join(signature.split()) in normalized
        archived_sources.append({**receipt(pdf), "publisher": publisher, "version": version,
            "effective_date": effective, "source_url": r["source_url"],
            "retrieved_utc": r["retrieved_utc"], "definition_signature_checked": True,
            "historical_2025_manual_vintage_verified": False,
            "extracted_text": receipt(txt)})

    facts = [
        {"fact_id": "NYISO_ACTUAL_DEFINITION", "evidence_type": "primary_definition",
         "source_document": definitions[0][0], "printed_pages": "59", "PDF_pages_1based": "94",
         "section": "5.6.2 Actual Load", "source_url": archived_sources[0]["source_url"],
         "finding": "Real-time actual zonal load is calculated from generation and net interchange using telemetry; its integrated series is a time-weighted hourly value.",
         "model_implication": "Treat the P58 balance quantity as gross boundary demand before separating modeled internal losses from delivered bus load.",
         "qualification": "The definition supports this balance interpretation but does not supply 2025 zonal loss values or certify the model's exact physical meter locations."},
        {"fact_id": "NYISO_FORECAST_DISTINCTION", "evidence_type": "primary_definition",
         "source_document": definitions[1][0], "printed_pages": "124-125", "PDF_pages_1based": "143-144",
         "section": "7.3.4 Transmission loss treatment", "source_url": archived_sources[1]["source_url"],
         "finding": "The short-term real-time demand forecast excludes transmission losses; scheduling adds zonal losses calculated by RTC/RTD power flow.",
         "model_implication": "Do not transfer this forecast convention to the separately defined public actual-load balance series.",
         "qualification": "A forecast rule alone cannot establish that P58 actual load is delivered bus PD."},
        {"fact_id": "EIA930_BALANCE_AND_SIGN", "evidence_type": "primary_definition",
         "source_document": definitions[2][0], "printed_pages": "5,9", "PDF_pages_1based": "5,9",
         "section": "Data Type FLOW; General Instructions / Energy balance", "source_url": archived_sources[2]["source_url"],
         "finding": "Demand plus net exported tie flow balances net generation. Positive reported FLOW means export from the reporting balancing authority.",
         "model_implication": "Negate NYIS-reported FLOW to obtain positive NY import targets and use a consistent reporting perspective.",
         "qualification": "Generation and interchange must use compatible reporting boundaries."},
        {"fact_id": "EIA930_PHYSICAL_SCOPE", "evidence_type": "primary_definition",
         "source_document": definitions[2][0], "printed_pages": "9-10", "PDF_pages_1based": "9-10",
         "section": "Physical vs. commercial operations", "source_url": archived_sources[2]["source_url"],
         "finding": "Reporting generally follows physical tie boundaries rather than ownership or dispatch. Dynamic-transfer exceptions require consistent agreements among affected balancing authorities communicated to EIA.",
         "model_implication": "Preserve the existing boundary-scope qualification, including NYISO-market resources physically outside NY and unresolved counterpart differences.",
         "qualification": "Market admission does not by itself prove EIA physical-balancing-area inclusion."},
        {"fact_id": "EIA930_STORAGE", "evidence_type": "primary_definition",
         "source_document": definitions[2][0], "printed_pages": "5-6", "PDF_pages_1based": "5-6",
         "section": "D and NG; pumped storage and batteries", "source_url": archived_sources[2]["source_url"],
         "finding": "Known grid energy used for storage is normally excluded from demand and included as negative net generation; a separate reporting fallback is defined.",
         "model_implication": "Do not treat storage or pumped hydro as unconstrained loss-balancing resources without energy and availability evidence.",
         "qualification": "No storage energy constraint has been reconstructed in this experiment."},
    ]
    pd.DataFrame(facts).to_csv(OUT / "primary_source_fact_ledger.csv", index=False)

    operating_path = ROOT / "output/nygrid_2025_inputs/model/operating_inputs.mat"
    dispatch_path = ROOT / "output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat"
    axes_path = ROOT / "output/nygrid_2025_acpf_profile_audit/acpf/annual_axes.mat"
    shares_path = ROOT / "output/nygrid_2025_western_audit/dispatch/all_boundary_external_generator_shares.csv"
    pal_receipts_path = ROOT / "output/nygrid_2025_inputs/load_source/source_receipts.csv"
    scaling_path = ROOT / "output/nygrid_2025_inputs/model/scaling_manifest.json"
    headroom_path = ROOT / "output/nygrid_2025_ac_loss_revision/validation/headroom/headroom_audit.json"
    graph_path = ROOT / "output/nygrid_2025_ac_loss_revision/validation/regional_budget_review/regional_budget_reference_review.json"
    operating = loadmat(operating_path, simplify_cells=True)
    dispatch = loadmat(dispatch_path, simplify_cells=True)
    axes = loadmat(axes_path, simplify_cells=True)
    shares = pd.read_csv(shares_path)
    headroom = json.loads(headroom_path.read_text())
    graph = json.loads(graph_path.read_text())
    scaling = json.loads(scaling_path.read_text())
    pal_receipts = pd.read_csv(pal_receipts_path).query("family == 'palIntegrated'")
    assert len(pal_receipts) == 12 and pal_receipts.month.nunique() == 12
    pal_archive_checks = []
    for item in pal_receipts.itertuples():
        archived = ROOT / item.archive
        assert receipt(archived)["sha256"] == item.sha256
        pal_archive_checks.append({"month": item.month, "source_url": item.source_url,
                                   "acquisition": item.acquisition, **receipt(archived)})
    valid = axes["source_qualified"].astype(bool)
    assert valid.sum() == 8651 and np.all(dispatch["qualified"][valid])
    assert np.array_equal(axes["hour_index"], dispatch["hour_index"])
    assert np.array_equal(axes["timestamp_utc"], dispatch["timestamp_utc"])
    assert headroom["passed"] and graph["passed"]
    original_gen = operating["base_case"]["gen"]
    crosscheck = []
    for region, group in shares.groupby("region", sort=False):
        old = group.parent_gen_row.to_numpy(dtype=int) - 1
        new = group.model_gen_row_1based.to_numpy(dtype=int) - 1
        assert np.array_equal(original_gen[old, 0], group.bus_id.to_numpy())
        assert abs(group.frozen_generation_share.sum() - 1) < 1e-12
        pg = dispatch["gen_pg"][valid][:, new]
        pmin, pmax = original_gen[old, 9], original_gen[old, 8]
        assert np.all(pg >= pmin - 1e-8) and np.all(pg <= pmax + 1e-8)
        row = {"region": region, "generator_count": len(group), "hours": int(valid.sum()),
               "loss_balancing_participant": region != "HQ",
               "original_Pmin_total_model_MW": float(pmin.sum()),
               "original_Pmax_total_model_MW": float(pmax.sum()),
               "minimum_upward_headroom_model_MW": float((pmax - pg).sum(axis=1).min()),
               "minimum_downward_headroom_model_MW": float((pg - pmin).sum(axis=1).min()),
               "frozen_generation_shares_sum": float(group.frozen_generation_share.sum()),
               "capability_status": "finite historical synthetic aggregate proxy; not observed 2025 unit reserve"}
        reference = next(x for x in headroom["external_original_capability_by_region"] if x["region"] == region)
        assert abs(row["minimum_upward_headroom_model_MW"] - reference["original_Pbox_upward_headroom_model_MW"]["min"]) < 1e-7
        crosscheck.append(row)
    pd.DataFrame(crosscheck).to_csv(OUT / "external_original_capability_crosscheck.csv", index=False)

    contract = {
        "policy_id": "NY_boundary_load_partition_and_external_area_loss_balance_at_NY_terminals",
        "status": "source-informed declared accounting policy; not observed 2025 dispatch or loss reconstruction",
        "source_vintage": "Primary NYISO manuals retrieved in 2026; their 2025 historical editions were not independently verified.",
        "actual_load_input_lineage": {
            "NYISO_family": "palIntegrated",
            "all_12_2025_archive_SHA256_checks_passed": True,
            "data_source_receipt": receipt(pal_receipts_path),
            "scaling_manifest_receipt": receipt(scaling_path),
            "annual_gamma": scaling["gamma"],
            "time_label_assumption_retained": scaling["load_interval_assumption"],
            "archived_source_receipts": pal_archive_checks,
        },
        "direct_source_facts": facts,
        "interpretation": {
            "NY_P58": "gross boundary demand: generation plus net import contains demand and losses inside the chosen meter boundary",
            "P58_partition": "gamma * P58(zone,hour) = delivered_PD(zone,hour) + allocated_modeled_NY_internal_real_loss(zone,hour)",
            "external_PD": "frozen delivered-demand proxy; no observed external 2025 regional load is claimed",
            "native_PG": "the existing 1436-row profile remains fixed, including the native reference generator",
            "HQ": "the bus48 equivalent remains the fixed signed source-target injection and is excluded from loss balancing",
        },
        "loss_ownership": {
            "same_NY_zone_corridor": "all real loss belongs to that zone",
            "different_NY_zones_corridor": "half belongs to each original physical terminal zone",
            "external_internal_corridor": "all real loss belongs to its external region",
            "cross_border_corridor": "all real loss belongs to the external area under the NY-terminal receipt convention, including reverse-flow hours",
            "numeric_section_nodes": "sum losses over the original parent corridor; never determine ownership from numerical interior-node tags",
            "zero_injection_nodes": "preserve zero active/reactive demand at added station and numerical section buses",
            "GS_and_DC_losses": "currently required to be exactly zero; a nonzero value requires an explicit ownership extension",
            "status": "declared model accounting; not certified NYISO zonal meter allocation",
        },
        "allocation": {
            "NY_delivered_PD": "subtract the assigned zonal loss by scaling the existing nonnegative zonal bus-load shares",
            "NY_QD": "scale by the same factor, preserving the existing assumed power factor; QD is not observed telemetry",
            "external_PG": "baseline_PG plus regional assigned loss allocated by frozen within-region generation shares, with bounded redistribution on saturation",
            "external_limits": "restore original finite Pmin/Pmax; retain fixed apparent-power capability proxy and recompute Q circle allowance at revised PG",
            "infeasibility": "reject exhausted external headroom or nonpositive zonal delivered demand; do not enlarge limits or clip unaccounted loss",
            "reference": "a numerical angle reference may absorb temporary iteration residuals; final native-reference PG must return to its input within tolerance",
        },
        "boundary_contract": {
            "regional_net": "preserve actual NYIS-reported EIA930 net-import targets at NY physical corridor terminals",
            "controlled_transfers": "preserve all six signed DC/PAR targets exactly; the AC/DC split retains its original source qualification",
            "algebra": "external_PG - external_delivered_PD - external_internal_loss - cross_border_loss = net_import_at_NY_terminals",
            "graph_prerequisite": "each external region connects to NY and has no active ties to another external region",
            "internal_interfaces": "the seven P32 internal interface series are comparison-only and never fitted by this policy",
        },
        "qualification_gates": [
            "AC equations and loss fixed point converge on every reported qualified hour",
            "all native PG and HQ injection retain their source-profile values within reported numerical tolerance",
            "all three modeled regional NY-terminal imports and all six controlled transfers match their targets",
            "the loss ledger counts each active parent-corridor loss exactly once and global power balance closes",
            "all NY delivered loads remain nonnegative and loss fractions are published by zone",
            "external PG stays within finite original P bounds and fixed S capability is not enlarged",
            "report Q capability, voltage, thermal limits, and reactive-control caveats separately from active-balance correctness",
            "compact-model terminal reconstructions retain the original physical-terminal measurements and injections",
        ],
        "limited_sensitivity_contract": [
            "Alternative allocation of cross-NY-zone corridor loss may be evaluated as explicitly declared accounting sensitivity.",
            "Treating external frozen PD as gross demand rather than delivered-demand proxy is a different boundary interpretation, not the default.",
            "Native fossil participation requires explicit delivered-P58 reinterpretation and synchronized/availability/AGC qualifications; finite box headroom alone is not evidence of real flexibility.",
            "Do not count the same NY losses in both a P58 delivered-load reduction and an added native generation requirement.",
        ],
        "material_limitations": [
            "The source definition justifies a boundary-balance interpretation but does not validate modeled loss magnitude or exact meter locations.",
            "The historical AC screen shows large synthetic zone-F losses; evaluate revised loss fractions before claiming physical realism.",
            "Frozen model fleet status, positive modeled generation, and original external capability are proxies, not observed commitment or reserves.",
            "Native NYISO-market inclusion and EIA physical-BA reporting may have unresolved scope differences.",
            "The synthetic external grid and engineering impedance/reactive assumptions remain model limitations.",
        ],
        "independent_input_crosscheck": crosscheck,
        "prerequisite_review_receipts": [receipt(headroom_path), receipt(graph_path)],
    }
    json_write("loss_accounting_policy_contract.json", contract)
    summary = {
        "passed": True, "created_utc": datetime.now(timezone.utc).isoformat(),
        "checkout_branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "checkout_HEAD": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "primary_source_files_verified": archived_sources,
        "source_qualified_hours": int(valid.sum()),
        "external_finite_capability_independent_crosscheck_passed": True,
        "source_definition_vs_model_inference_explicit": True,
        "new_PF_run_or_operating_profile_mutation": False,
        "revised_model_feasibility_established_by_this_audit": False,
        "all_12_2025_palIntegrated_source_archive_SHA256_checks_passed": True,
        "sources": [receipt(x) for x in [operating_path, dispatch_path, axes_path, shares_path, pal_receipts_path, scaling_path, headroom_path, graph_path]],
        "source_code": receipt(Path(__file__)),
        "outputs": [receipt(OUT / x) for x in ["primary_source_fact_ledger.csv", "external_original_capability_crosscheck.csv", "loss_accounting_policy_contract.json"]],
    }
    json_write("policy_evidence_audit.json", summary)
    print(json.dumps({"passed": True, "source_qualified_hours": int(valid.sum()),
                     "primary_sources": len(archived_sources), "output": str(OUT)}))


if __name__ == "__main__":
    main()
