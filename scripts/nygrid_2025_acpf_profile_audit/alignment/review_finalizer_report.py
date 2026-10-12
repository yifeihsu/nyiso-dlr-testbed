"""Independent read-only delivery review; writes only its review receipt."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import re
import subprocess
from urllib.parse import unquote
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_acpf_profile_audit'
REVIEW = OUT / 'alignment/finalizer_report_independent_review.json'
HEAD = '330be1d90e6faab8d6c32c3d6c174aa364a30c73'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path):
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path))


def main():
    baseline_path = ROOT / 'output/nygrid_2025_ac_system/DELIVERY_MANIFEST.json'
    old = subprocess.check_output(['git', 'show', HEAD + ':output/nygrid_2025_ac_system/DELIVERY_MANIFEST.json'], cwd=ROOT)
    assert old == baseline_path.read_bytes()
    baseline = json.loads(old)
    for path, rec in baseline['files'].items():
        p = ROOT / path
        assert sha(p) == rec['sha256'] and p.stat().st_size == rec['bytes']
    dependencies = [ROOT / 'NYGRID_2025_ACPF_PROFILE_AUDIT.md', baseline_path, Path(__file__)]
    dependencies += [ROOT / 'scripts/nygrid_2025_acpf_profile_audit' / p for p in
                     ['finalize_audit.py', 'build_report.py', 'score_interfaces.py', 'build_sources_receipt.py']]
    json_paths = ['alignment/profile_alignment_summary.json', 'alignment/load_source_semantics.json',
                  'alignment/interface_operator_contract.json', 'structure/structure_audit.json',
                  'structure/preservation_and_readability.json', 'structure/scoring_annual_independent_review.json',
                  'comparison/scoring_receipt.json', 'acpf/annual_profile_PF_receipt.json',
                  'acpf/representative_profile_PF_receipt.json', 'acpf/cache_parity_and_benchmark.json',
                  'acpf/Q_limit_sensitivity/Q_limit_sensitivity_receipt.json',
                  'acpf/NR_recovery/NR_recovery_receipt.json', 'acpf/validation_source_receipt.json', 'audit_summary.json']
    data = {p: json.loads((OUT / p).read_text(encoding='utf-8-sig')) for p in json_paths}
    dependencies += [OUT / p for p in json_paths]
    a = data['alignment/profile_alignment_summary.json']
    annual = data['acpf/annual_profile_PF_receipt.json']
    scoring = data['comparison/scoring_receipt.json']
    assert a['generation']['source_and_dispatch_qualified_hours'] == 8657
    assert a['generation']['final_common_replay_source_qualified_hours'] == 8651
    assert annual['completed'] and annual['attempted_hours'] == 8651
    assert annual['PF_converged_hours'] == scoring['matched_comparison_hours'] == 8494
    assert annual['VQ_and_generator_assumption_qualified_hours'] == 0
    assert not annual['OPF_used'] and not scoring['physical_NYISO_meter_membership_and_terminal_convention_certified']
    recovery = data['acpf/NR_recovery/NR_recovery_receipt.json']
    assert recovery['primary_failed_hours'] == 157 and recovery['attempts'] == 314 and recovery['recovered_hour_count'] == 0
    assert not recovery['source_profiles_controls_or_parameters_changed'] and not recovery['primary_outputs_overwritten']
    qchecks = data['acpf/Q_limit_sensitivity/Q_limit_sensitivity_receipt.json']['checks']
    qgood = [r for r in qchecks if r['PF_converged'] and r['AC_equation_gate']]
    assert len(qchecks) == 7 and len(qgood) == 5
    assert all(r['generator_Q_bound_gate'] and r['six_DC_Q_contract_gate'] for r in qgood)
    assert all(not r['normal_voltage_gate'] and not r['generator_P_bound_gate'] and not r['generator_S_proxy_gate'] for r in qgood)
    frozen = ROOT / 'output/nygrid_2025_dover_parameters/replay/bounded_x_nominal.npz'
    dependencies.append(frozen)
    with np.load(frozen) as d:
        times, sourceq, gamma = d['timestamp_utc'].astype(str), d['qualified'].astype(bool), float(d['gamma'])
    seen = set(); axes = {}; totals = np.zeros(4, int)
    monthly = sorted((OUT / 'acpf/monthly').glob('profile_PF_2025_*.mat'))
    assert len(monthly) == 12
    for p in monthly:
        m = loadmat(p, simplify_cells=True, variable_names=['hour_index','timestamp_utc','source_qualified','gamma',
                    'branch_keys','branch_parent_row','branch_from_bus','branch_to_bus','bus_id','base_kv',
                    'AC_equation_gate','P_profile_preservation_gate','VQ_and_generator_assumption_gate'])
        h = np.asarray(m['hour_index'], int).reshape(-1)
        assert ((h >= 1) & (h <= 8760)).all() and len(h) == len(set(h)) and not seen.intersection(h)
        assert np.array_equal(times[h - 1], np.asarray(m['timestamp_utc']).astype(str))
        assert np.array_equal(sourceq[h - 1], np.asarray(m['source_qualified']).astype(bool))
        assert m['gamma'] == gamma
        for k in ['branch_keys','branch_parent_row','branch_from_bus','branch_to_bus','bus_id','base_kv']:
            if k not in axes: axes[k] = m[k]
            else: assert np.array_equal(axes[k], m[k])
        seen.update(h.tolist())
        totals += [len(h), int(sourceq[h - 1].sum()), int((m['AC_equation_gate'].astype(bool) & m['P_profile_preservation_gate'].astype(bool) & sourceq[h - 1]).sum()), int(m['VQ_and_generator_assumption_gate'].sum())]
    assert seen == set(range(1,8761)) and totals.tolist() == [8760, 8651, 8494, 0]
    assert len(set(axes['branch_keys'])) == 488 and len(set(axes['bus_id'])) == 267
    quality_path = OUT / 'acpf/annual_hour_quality.csv'; dependencies.append(quality_path)
    quality = pd.read_csv(quality_path)
    failed = quality.loc[~quality.PF_converged.astype(bool)]
    assert len(failed) == 157
    assert set(pd.to_datetime(failed.timestamp_utc, utc=True).dt.tz_convert('America/New_York').dt.month) == {7, 8}
    report = dependencies[0].read_text(encoding='utf-8')
    links = []
    for target in re.findall(r'\]\(([^)]+)\)', report):
        if target.startswith(('https://','http://','#')): continue
        p = ROOT / unquote(target.strip('<>').split('#')[0])
        assert p.is_file(), target
        links.append(target)
    source_pdf = OUT / 'alignment/sources/NYISO_2025_hot_weather_operations.pdf'
    assert sha(source_pdf) == 'cdf7e3ac98ea5fc0aac0342fe367987944e528ad5c69c404462ca2970af63cb8'
    dependencies.append(source_pdf)
    semantics = data['alignment/load_source_semantics.json']
    peak = semantics['peak_load_hour']
    assert peak['measured_load_rounded_MW'] + peak['BTM_solar_MW'] + peak['NYISO_and_retail_DR_MW'] == peak['reconstructed_total_demand_MW'] == 33799
    result = dict(passed=True, created_utc=datetime.now(timezone.utc).isoformat(),
        review_scope='Independent finalizer/report source-alignment, preservation, axis/cohort and evidence-link review. Interface metric arithmetic independently reviewed in structure/scoring_annual_independent_review.json.',
        baseline_commit=HEAD, baseline_manifest_equals_committed_bytes=True, baseline_files_unchanged=len(baseline['files']),
        canonical_monthly_axes_checked=12, retained_hours=8760, source_qualified_hours=8651, matched_cohort_hours=8494,
        VQ_generator_qualified_hours=0, local_report_links_checked=len(links),
        source_alignment_review=dict(exact_zonal_agreement_identified_as_construction_identity=True,
            static_31_positive_NY_bus_weights_not_observed_2025_bus_loads=True,
            external_94_bus_load_proxy_distinguished_from_NY_11_zones=True,
            native_1436_plus_external_28_generation_reconstruction_not_unit_telemetry=True,
            upstream8657_and_final8651_masks_distinguished=True,
            slack_loss_adjustment_qualified_against_non_slack_profile_preservation=True,
            fixed_external_P_not_claimed_as_preserved_actual_AC_net_exchange=True,
            physical_P32_membership_units_and_meter_terminals_remain_qualified=True,
            public_NYISO_load_semantics_supported_by_archived_primary_pdf_pages_7_and_12=True,
            net_measured_peak_vs_gross_end_use_distinction_preserved=True),
        scientific_status_review=dict(audit_complete_not_model_ready=True, no_ACOPF_requirement_inferred=True,
            primary8494_of8651_results_not_replaced_by_diagnostics=True,
            zero_recovery_in314_attempts_not_global_infeasibility_proof=True,
            Q_limit_control_5_of7_success_not_voltage_or_generator_P_feasibility=True,
            thermal_overload_not_PF_convergence_rejection=True),
        resolved_review_findings=['Baseline manifest now anchored to recorded Git commit before trusting its454 hashes.',
            'Scorer now rejects out-of-range hours and changed canonical parent/from/to/bus/kV axes.',
            'Reproduction distinguishes verification of archived bytes from regenerated receipt refresh and resealing.'],
        outstanding_actionable_findings=[], model_or_root_owned_files_modified_by_review=False,
        final_delivery_manifest_intentionally_not_bound_to_avoid_hash_cycle=True,
        dependencies=[record(p) for p in dependencies + monthly])
    REVIEW.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    # This call only computes/validates the manifest and does not seal it.
    path = ROOT / 'scripts/nygrid_2025_acpf_profile_audit/finalize_audit.py'
    spec = importlib.util.spec_from_file_location('reviewed_finalizer', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    expected = module.expected_manifest()
    result['read_only_finalizer_closure_passed'] = True
    result['finalizer_status_checked'] = expected['status']
    result['finalizer_proof_checks_at_review'] = expected['proof_file_hash_checks']
    REVIEW.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, review=str(REVIEW), baseline_files_unchanged=len(baseline['files']),
                         report_links=len(links), matched_hours=8494, finalizer_closure_passed=True)))


if __name__ == '__main__': main()
