"""Summarize qualified controlled experiments and bind source/evidence hashes.

Reads no NYISO observed interface values. Failed R0 iterates are retained in
raw evidence and excluded from the validity-filtered reporting table.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_centraleast_diagnosis/experiments'
TARGET = OUT / 'experiment_source_receipt.json'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def record(path):
    p = Path(path)
    return dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p), bytes=p.stat().st_size)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    bridge = read(OUT / 'representative_bridge/bridge_receipt.json')
    xonly = read(OUT / 'X_only_ablations/X_only_receipt.json')
    reps = read(OUT / 'loss_and_parent_diagnostics/diagnostic_receipt.json')
    annual = read(OUT / 'annual_DC_bridge/annual_DC_bridge_receipt.json')
    loss_report = read(OUT / 'annual_loss_loaded_DCF/annual_loss_loaded_receipt.json')
    assert bridge['passed'] and len(bridge['hours']) == 11
    assert xonly['completed'] and xonly['all_DCPF_audits_passed'] and xonly['attempts'] == 33
    assert reps['completed'] and reps['loss_loaded_DCF_qualified'] == reps['parent_AC_qualified'] == 11
    assert annual['passed'] and annual['solves'] == 33976
    assert loss_report['passed'] and loss_report['solves'] == 25482
    d = loadmat(OUT / 'annual_DC_bridge/annual_DC_bridge_arrays.mat', simplify_cells=True)
    l = loadmat(OUT / 'annual_loss_loaded_DCF/annual_loss_loaded_arrays.mat', simplify_cells=True)
    cohort = d['cohort'].astype(bool)
    assert int(cohort.sum()) == 8494 and np.array_equal(cohort, l['cohort'].astype(bool))
    for key in ['hour_index', 'timestamp_utc', 'gamma', 'source_qualified', 'state_index', 'bus_id']:
        assert np.array_equal(d[key], l[key]), key
    assert d['audit_passed'][cohort].all() and l['audit_passed'][cohort].all()
    assert np.array_equal(d['interface_model_MW'][:, :, 0], l['baseline_detailed_DCF_interface_model_MW'], equal_nan=True)
    gamma = float(d['gamma'])
    dc = d['archived_DC_interface_model_MW'][:, 4] / gamma
    modern_dc = d['interface_model_MW'][:, 4, 0] / gamma
    ac = l['baseline_AC_interface_model_MW'][:, 4] / gamma
    loss = l['interface_model_MW'][:, 4, :] / gamma
    construction = modern_dc - dc
    supply = loss - modern_dc[:, None]
    remaining = ac[:, None] - loss
    assert np.max(abs(construction[cohort, None] + supply[cohort] + remaining[cohort] - (ac[cohort] - dc[cohort])[:, None])) < 1e-8
    assert np.max(abs(d['interface_model_MW'][cohort, :, 3] - d['archived_DC_interface_model_MW'][cohort])) < 1e-7
    assert np.max(abs(l['slack_increment_MW'][cohort] - l['baseline_AC_loss_MW'][cohort, None])) < 1e-6
    assert np.max(abs(l['max_non_slack_PG_change_MW'][cohort])) == 0
    # Cross-check the baseline AC series against the already sealed comparison.
    comparison_path = ROOT / 'output/nygrid_2025_compact_ac/alignment/comparison_arrays.npz'
    with np.load(comparison_path, allow_pickle=False) as comparison:
        expected_ac = comparison['compact_legacy_signed_literal_from']
        assert np.array_equal(cohort, comparison['paired_qualified'].astype(bool))
        assert expected_ac.shape == (8760, 7)
        baseline_comparison_error = float(np.max(abs(l['baseline_AC_interface_model_MW'][cohort] / gamma - expected_ac[cohort])))
    assert baseline_comparison_error < 1e-5
    hourly = pd.DataFrame(dict(hour_index=d['hour_index'][cohort].astype(int), timestamp_utc=d['timestamp_utc'][cohort],
        archived_DC_public_MW=dc[cohort], detailed_network_DCF_public_MW=modern_dc[cohort], baseline_ACPF_public_MW=ac[cohort],
        restore224X_DCF_public_MW=d['interface_model_MW'][cohort, 4, 1] / gamma,
        restore41X_DCF_public_MW=d['interface_model_MW'][cohort, 4, 2] / gamma,
        restore_all33X_DCF_public_MW=d['interface_model_MW'][cohort, 4, 3] / gamma,
        construction_delta_public_MW=construction[cohort],
        half_loss_DCF_public_MW=loss[cohort, 0], all_from_loss_DCF_public_MW=loss[cohort, 1], all_to_loss_DCF_public_MW=loss[cohort, 2],
        half_loss_allocation_delta_public_MW=supply[cohort, 0], remaining_after_half_loss_public_MW=remaining[cohort, 0],
        baseline_AC_real_losses_model_MW=l['baseline_AC_loss_MW'][cohort],
        half_loss_DCF_slack_increment_model_MW=l['slack_increment_MW'][cohort, 0]))
    hourly.to_csv(OUT / 'annual_CE_controlled_bridge.csv', index=False, lineterminator='\n')
    filtered = pd.read_csv(OUT / 'loss_and_parent_diagnostics/diagnostic_checks.csv')
    bad = ~filtered.R0_AC_equation_profile_qualified.astype(bool)
    for col in ['R0_CE_public_MW', 'R0_CE_delta_from_baseline_AC_public_MW', 'R0_AC_losses_model_MW', 'R0_min_VM', 'R0_max_VM']:
        filtered.loc[bad, col] = np.nan
    filtered.to_csv(OUT / 'representative_validity_filtered.csv', index=False, lineterminator='\n')
    mean_total = float(np.mean(ac[cohort] - dc[cohort])); mean_construction = float(np.mean(construction[cohort]))
    row224_effect = float(np.mean((d['interface_model_MW'][cohort, 4, 0] - d['interface_model_MW'][cohort, 4, 1]) / gamma))
    summary = dict(completed=True, qualified_fixed_annual_hours=8494,
        original_eight_representatives=bridge['primary_hours'], additional_posthoc_extremes=bridge['additional_diagnostic_extremes'],
        mean_AC_minus_archived_DC_CE_public_MW=mean_total,
        mean_same_network_construction_delta_public_MW=mean_construction,
        mean_loss_allocation_delta_public_MW=float(supply[cohort, 0].mean()),
        mean_remaining_after_half_loss_public_MW=float(remaining[cohort, 0].mean()),
        half_loss_remaining_mean_absolute_public_MW=float(abs(remaining[cohort, 0]).mean()),
        half_loss_remaining_maximum_absolute_public_MW=float(abs(remaining[cohort, 0]).max()),
        mean_row224_X_restoration_effect_on_DCF_public_MW=row224_effect,
        row224_share_of_mean_construction_difference=row224_effect / mean_construction,
        allocation_convention_sensitivity=[dict(allocation=label, mean_loss_contribution_public_MW=float(supply[cohort, k].mean()),
            mean_remaining_public_MW=float(remaining[cohort, k].mean())) for k, label in enumerate(l['labels'])],
        baseline_AC_vs_frozen_compact_interface_maximum_public_MW=baseline_comparison_error,
        R0_qualified_hours=filtered.loc[~bad, 'hour_index'].astype(int).tolist(), R0_failed_hours=filtered.loc[bad, 'hour_index'].astype(int).tolist(),
        coherent_old_parent_AC_qualified_hours=11, original_DC_vs_fresh_full_parent_parity_model_MW=max(r['archived_vs_full_parent_DC_interface_max_MW'] for r in bridge['checks']),
        all33_X_restored_DCF_vs_archived_all_seven_interfaces_maximum_model_MW=float(np.max(abs(d['interface_model_MW'][cohort, :, 3] - d['archived_DC_interface_model_MW'][cohort]))),
        findings_are_controlled_model_diagnostics_not_physical_validation=True,
        X_only_AC_interventions_create_hybrid_R_X_ratios_and_are_not_repair_candidates=True,
        half_loss_allocation_is_nonunique_not_unique_causal_attribution=True,
        from_to_allocation_sensitivity_is_not_confidence_interval=True,
        no_fit_to_NYISO_observations_performed=True, production_models_profiles_and_existing_outputs_unchanged=True)
    (OUT / 'experiment_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    logs = OUT / 'logs'; logs.mkdir(exist_ok=True)
    for path in sorted((ROOT / 'tmp').glob('centraleast_*.log')):
        shutil.copyfile(path, logs / path.name)
    # Bind the established compact/full AC baseline and check every sealed byte.
    baseline_seal_path = ROOT / 'output/nygrid_2025_compact_ac/validation/source_receipt.json'
    seal = read(baseline_seal_path)
    protected = sum([seal.get(key, []) for key in ['source_data', 'source_code', 'evidence', 'independent_reviews']], [])
    for r in protected:
        assert sha(ROOT / r['path']) == r['sha256'], f"Prior sealed data changed: {r['path']}"
    sources = {ROOT / r['path'] for r in seal['source_data']}
    sources.update([baseline_seal_path, comparison_path,
        ROOT / 'output/nygrid_2025_dover_parameters/replay/bounded_x_nominal.npz',
        ROOT / 'output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat',
        ROOT / 'output/nygrid_2025_dover_parameters/network/x_nominal.mat',
        ROOT / 'output/nygrid_2025_downstate/replay/interface_definitions.json',
        ROOT / 'output/nygrid_2025_centraleast_diagnosis/model_delta/x_changed_corridors.csv'])
    sources.update((ROOT / 'output/nygrid_2025_acpf_profile_audit/acpf/monthly').glob('profile_PF_2025_*.mat'))
    code = sorted(p for p in (ROOT / 'scripts/nygrid_2025_centraleast_diagnosis/experiments').iterdir() if p.suffix in {'.m', '.py'})
    evidence = sorted(p for p in OUT.rglob('*') if p.is_file() and p != TARGET and p.suffix in {'.m', '.mat', '.csv', '.json', '.log'})
    receipt = dict(passed=True, created_utc=datetime.now(timezone.utc).isoformat(), prior_sealed_records_unchanged=len(protected),
        initial_failed_multinterface_mapping_trial_preserved=True, initial_mapping_defect_corrected_before_any_ablation=True,
        primary_bridge_passed=True, annual_DCPF_bridge_passed=True, annual_loss_loaded_DCPF_passed=True,
        failed_R0_iterates_retained_but_excluded_from_reporting_table=True,
        all_models_are_diagnostics_not_promoted_repairs=True, no_production_input_or_result_modified=True,
        OPF_or_parameter_fitting_used=False, observed_interface_values_used_as_solver_inputs=False,
        independent_postexperiment_reviews_excluded_to_avoid_hash_cycles=True,
        source_data=[record(p) for p in sorted(sources)], source_code=[record(p) for p in code], evidence=[record(p) for p in evidence])
    TARGET.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(passed=True, summary=summary, receipt_sha256=sha(TARGET))))


if __name__ == '__main__':
    main()
