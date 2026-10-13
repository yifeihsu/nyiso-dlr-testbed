"""Freeze source/cohort intent before reading any compact-AC solve results.

This only reads the existing audited profiles, public observations and legacy
terminal definitions. It never changes or solves either electrical model.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import subprocess
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_compact_ac/alignment'
BASELINE_HEAD = '3d2d3104879815180b82804861788dd132aed729'
AUDIT = ROOT / 'output/nygrid_2025_acpf_profile_audit'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def record(path):
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path), bytes=path.stat().st_size)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sealed_path = AUDIT / 'DELIVERY_MANIFEST.json'
    committed = subprocess.check_output(['git', 'show', BASELINE_HEAD + ':output/nygrid_2025_acpf_profile_audit/DELIVERY_MANIFEST.json'], cwd=ROOT)
    assert sealed_path.read_bytes() == committed, 'Prior detailed audit manifest differs from frozen commit'
    sealed = json.loads(committed)
    for relative, expected in sealed['files'].items():
        p = ROOT / relative
        assert p.stat().st_size == expected['bytes'] and sha(p) == expected['sha256'], f'Prior audit changed: {relative}'
    source_cohort_path = AUDIT / 'alignment/source_comparison_cohort.csv'
    prior_comparison_path = AUDIT / 'comparison/comparison_arrays.npz'
    source_cohort = pd.read_csv(source_cohort_path)
    with np.load(prior_comparison_path, allow_pickle=False) as d:
        hours, times, gamma = d['hour_index'], d['timestamp_utc'].astype(str), float(d['gamma'])
        detailed_good = d['ACPF_comparison_cohort'].astype(bool)
        source_good = d['source_qualified'].astype(bool)
        names = d['interface_names'].astype(str).tolist()
        detailed_operating_good = d['VQ_and_generator_assumption_gate'].astype(bool)
        observed = d['observed']
    assert np.array_equal(hours, np.arange(1, 8761))
    assert np.array_equal(source_cohort.hour_index, hours)
    assert np.array_equal(source_cohort.timestamp_utc, times)
    assert np.array_equal(source_cohort.final_common_replay_source_qualified.astype(bool), source_good)
    assert np.array_equal(source_cohort.final_source_and_P32_comparison_cohort.astype(bool), source_good)
    assert source_good.sum() == 8651 and detailed_good.sum() == 8494 and detailed_operating_good.sum() == 0
    assert np.all(~detailed_good | source_good) and np.isfinite(observed[source_good]).all()
    cohort = source_cohort[['hour_index','timestamp_utc','local_timestamp','time_zone','utc_offset_minutes','dst_fold','dated_state']].copy()
    cohort['frozen_source_qualified'] = source_good
    cohort['frozen_detailed_equation_and_profile_qualified'] = detailed_good
    cohort['frozen_detailed_VQ_generator_qualified'] = detailed_operating_good
    cohort['all_seven_public_P32_qualified'] = source_cohort.all_seven_P32_qualified
    cohort.to_csv(OUT / 'frozen_comparison_cohort.csv', index=False, lineterminator='\n')
    files = [Path(__file__), OUT / 'frozen_comparison_cohort.csv', sealed_path, source_cohort_path, prior_comparison_path,
             AUDIT / 'alignment/profile_alignment_summary.json', AUDIT / 'alignment/interface_operator_contract.json',
             AUDIT / 'alignment/interface_operator_terms.csv', AUDIT / 'alignment/load_source_semantics.json',
             ROOT / 'scripts/nygrid_2025_acpf_profile_audit/alignment/interface_operator.py',
             ROOT / 'output/nygrid_2025_dover_parameters/replay/bounded_x_nominal.npz',
             ROOT / 'output/nygrid_2025_inputs/load_source/interface_wide.csv',
             ROOT / 'output/nygrid_2025_inputs/load_source/interface_quality_wide.csv',
             ROOT / 'output/nygrid_2025_inputs/load_source/load_wide.csv',
             ROOT / 'output/nygrid_2025_inputs/model/operating_inputs.mat',
             ROOT / 'output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat']
    # The reusable mapper reads current full-parent case files. Bind those
    # numerical membership sources too, not only the mapper/contract text.
    prior_operator = json.loads((AUDIT / 'alignment/interface_operator_contract.json').read_text())
    for entry in prior_operator['source_receipts']:
        path = ROOT / entry['path']
        assert sha(path) == entry['sha256'], f'Frozen interface membership source changed: {entry["path"]}'
        files.append(path)
    files = list(dict.fromkeys(files))
    contract = dict(created_utc=datetime.now(timezone.utc).isoformat(),
        status='source_and_comparison_contract_sealed_before_compact_result_inspection', baseline_HEAD=BASELINE_HEAD,
        previous_detailed_audit_files_verified_unchanged=len(sealed['files']),
        model_or_profile_changes_performed_by_alignment=False, PF_or_OPF_executed_by_alignment=False,
        source_qualified_hours=int(source_good.sum()), retained_hour_positions=8760,
        frozen_detailed_equation_and_profile_qualified_hours=int(detailed_good.sum()),
        frozen_detailed_VQ_generator_qualified_hours=int(detailed_operating_good.sum()),
        source_qualified_and_numerical_convergence_are_separate=True,
        baseline_detailed_monthly_directory='output/nygrid_2025_acpf_profile_audit/acpf/monthly',
        public_observation_path='output/nygrid_2025_inputs/load_source/interface_wide.csv',
        public_quality_path='output/nygrid_2025_inputs/load_source/interface_quality_wide.csv',
        interface_names=names, gamma=gamma,
        primary_terminal_convention='legacy_signed_literal_from',
        alternative_terminal_conventions=['oriented_source_side','oriented_target_side'],
        inherited_operator_path='scripts/nygrid_2025_acpf_profile_audit/alignment/interface_operator.py',
        physical_P32_meter_membership_or_units_certified=False,
        public_load_meaning='NYISO measured grid load; not gross end-use demand before BTM solar and demand response',
        exact_zone_load_agreement_is_construction_identity=True,
        within_zone_bus_distribution_is_observed_2025=False,
        numerical_comparison_scope='Compare compact recovered original bus voltages and full branch terminal powers/currents to the detailed case on identical source hours and declared initializations.',
        primary_public_comparison_cohort='Intersection of frozen source eligibility, detailed equation/profile qualification and compact equation/profile qualification; report coverage losses and gains separately.',
        additional_compact_success_policy='Report separately if compact converges on previously failed detailed hours; do not silently mix those hours into the paired detailed public-error comparison.',
        paired_reference_policy='A new direct detailed solve, if supplied, is labelled separately from the frozen default annual reference; never replace a failed historical solve without a provenance label.',
        power_comparison_scale='Aggregate model MW divided by gamma for public comparison only; paired compact/detailed numerical equality uses model MW.',
        current_comparison_scale='Recovered physical branch terminal and series currents in amperes; never divide current by gamma.',
        flow_membership_policy='Use original full-parent corridor identities and original from/to physical terminal powers, following section chains and current dated active masks; no reduced-network edge sums.',
        fitting_policy='No internal-interface observations are used to fit profiles, retained-node choices, model parameters, signs, times, scaling or operator membership.',
        operating_gate_policy='Inherited V/Q/generator assumptions and violations remain explicit; algebraic reduction or numerical agreement does not certify a feasible or observed NYISO operating state.',
        expected_compact_export_fields=['hour_index','timestamp_utc','gamma','source_qualified',
            'AC_equation_gate','P_profile_preservation_gate','VQ_and_generator_assumption_gate',
            'full_branch_keys','full_branch_parent_row','full_branch_from_bus','full_branch_to_bus',
            'full_branch_present','full_branch_active','recovered_PF','recovered_PT','recovered_QF','recovered_QT',
            'recovered_Iseries','recovered_Ifrom','recovered_Ito','full_bus_id','recovered_VM','recovered_VA'],
        export_API_status='Proposed consumption contract; solver owner will confirm exact field names before numerical scoring.',
        source_receipts=[record(p) for p in files])
    (OUT / 'comparison_contract.json').write_text(json.dumps(contract, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, contract=str(OUT / 'comparison_contract.json'),
                         prior_audit_files_unchanged=len(sealed['files']), source_hours=int(source_good.sum()),
                         frozen_detailed_qualified_hours=int(detailed_good.sum()))))


if __name__ == '__main__': main()
