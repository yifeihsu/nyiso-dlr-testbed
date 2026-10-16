"""Bind the final report review to corrected, preserved source evidence.

This checks the report and previously independently verified evidence. It does
not run a new power flow or promote a model/operator/source correction.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_postrepair_diagnosis'
REPORT = ROOT / 'NYGRID_2025_POSTREPAIR_DIAGNOSIS.md'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8'))


def file_record(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)}


def verify_refs(rows):
    for row in rows:
        assert sha(ROOT / row['path']) == row['sha256'], row['path']
    return len(rows)


text = REPORT.read_text(encoding='utf-8')
local_links = [x for x in re.findall(r'\]\(([^)]+)\)', text)
               if not x.startswith(('https://', 'http://', '#'))]
assert all((ROOT / x).is_file() for x in local_links)
guard = load('output/nygrid_2025_postrepair_diagnosis/source_guard.json')
guard_count = verify_refs(guard['files'])
gen = load('output/nygrid_2025_postrepair_diagnosis/generation/generation_source_review.json')
gen_refs = verify_refs(gen['receipt_files'])
assert gen['passed'] and len(gen['data_catalog']) == 11
assert not gen['universal_absence_claimed']
assert 'not annual-total monthly imputation' in gen['source_supported_remaining_driver']['AM_monthly_caveat']
assert gen['source_supported_remaining_driver']['actual_negative_auxiliary_power_bound_established'] is False
wind = load('output/nygrid_2025_postrepair_diagnosis/boundary/independent_wind_review.json')
residual = load('output/nygrid_2025_postrepair_diagnosis/boundary/independent_residual_review.json')
assert wind['passed'] and residual['passed']
own_refs = verify_refs(wind['inputs']) + verify_refs(residual['inputs'])
assert abs(wind['qualified_energy_minus_reported_annual_MWh'] - 237723.2505819518) < 1e-7
assert residual['months_incompatible_at_each_tested_cap'] == 12

# The prediction-interaction distribution supports the report's distinction
# between MAE nonlinearity and the much smaller electrical interaction.
data = np.load(OUT / 'ablations/factorial_arrays.npz', allow_pickle=False)
q = data['common_qualified'].astype(bool)
assert q.sum() == 8651
j = data['interface_names'].tolist().index('MOSES SOUTH')
interaction = (data['GP_legacy_signed_literal_from']
               - data['G_legacy_signed_literal_from']
               - data['P_legacy_signed_literal_from']
               + data['B_legacy_signed_literal_from'])[q, j]
assert np.max(np.abs(interaction)) < 1.02
assert abs(interaction.mean() - 0.1979170947623852) < 1e-8

required_report_qualifications = {
    'controlled_effects_within_current_model': 'controlled effects in this model',
    'PV20_operator_reported_proxy': 'same reported PV20 proxy',
    'native_P34_units_not_resolved': 'native `Flow(MWH)` header',
    'complete_interface_not_certified': 'Neither mixed-scope comparison nor one added term can certify',
    'wind_bound_conditional': 'conditional on those nonnegative bounds',
    'negative_EIA_net_generation': 'EIA permits negative net generation',
    'AM_distinct_from_A': 'AM must not be conflated with the annual-only A category',
    'flat_control_includes_other_HY': 'including other HY redistribution',
    'flat_control_not_annual_AC': 'not a new annual AC validation',
    'StLawrence_oracle_not_dispatch': 'oracle is never used as a source or dispatch target',
    '912_not_certified_capability': 'not certified capability',
    'one_feeder_not_error_bound': 'not a complete hourly tap-load or meter-error bound',
    '2026_goldbook_retrieval_limit': 'No claim that the 2026 book is absent',
    'no_model_promotion': 'No model, current map or handoff update is promoted',
}
assert all(phrase in text for phrase in required_report_qualifications.values())

inputs = [
    OUT / 'source_guard.json', OUT / 'independent_summary_review.json',
    OUT / 'ablations/factorial_arrays.npz', OUT / 'ablations/factorial_metrics.csv',
    OUT / 'ablations/factorial_attribution.csv', OUT / 'ablations/factorial_scoring_receipt.json',
    OUT / 'boundary/boundary_readout_receipt.json', OUT / 'boundary/source_semantics_review.json',
    OUT / 'boundary/independent_residual_review.json', OUT / 'boundary/independent_wind_review.json',
    OUT / 'generation/generation_source_review.json', OUT / 'generation/D_wind_source_energy_review.json',
    OUT / 'generation/D_wind_monthly_totals.csv', OUT / 'generation/D_wind_annual_EIA_comparison.csv',
    OUT / 'controlled_effects.png', OUT / 'figure_receipt.json',
]
receipt = {
    'passed': True,
    'reviewed_utc': datetime.now(timezone.utc).isoformat(),
    'report': file_record(REPORT),
    'scope': 'Final narrative, source semantics, conditional inference, cohort, evidence links and figure review; no model or physical-meter promotion.',
    'all_local_report_links_exist': True,
    'local_links_checked': len(local_links),
    'immutable_source_and_current_delivery_hashes_checked': guard_count,
    'final_generation_receipt_hashes_checked': gen_refs,
    'prior_independent_residual_and_wind_input_hashes_checked': own_refs,
    'qualified_hours': int(q.sum()),
    'report_qualifications_reviewed': list(required_report_qualifications),
    'Moses_prediction_interaction_public_MW': {
        'mean': float(interaction.mean()),
        'mean_absolute': float(np.mean(np.abs(interaction))),
        'p95_absolute': float(np.percentile(np.abs(interaction), 95)),
        'maximum_absolute': float(np.max(np.abs(interaction))),
        'interpretation': 'Large MAE interaction is supported as mainly offsetting signed effects and absolute-error nonlinearity, not hidden large opposing hourly prediction interactions.',
    },
    'resolved_review_findings': [
        'Annual wind table now recomputes interval distances and Boolean flags from annual totals.',
        'AM monthly values reported annually are distinguished from annual-only A monthly estimates.',
        'Wind lower bound is explicitly conditional on nonnegative excluded net generation; no auxiliary-power bound is invented.',
        'PV20 is described as operator-reported under adopted MW/forward-hold semantics, with native support unresolved.',
        'StLawrence-only necessary condition and frozen-terminal shape sensitivity retain all assumptions.',
    ],
    'controlled_effects_figure_visual_review': {
        'passed': True,
        'method': 'Reviewer visually inspected the rendered PNG; both B/G/P/GP rows, numeric labels, cohort and model-only qualification were legible and consistent with the report.',
        'sha256': sha(OUT / 'controlled_effects.png'),
    },
    'unresolved_actionable_report_findings': [],
    'remaining_scientific_limitations_are_disclosed': True,
    'new_AC_power_flows': 0,
    'model_map_handoff_pointer_changed_by_review': False,
    'inputs': [file_record(p) for p in inputs],
    'script_sha256': sha(Path(__file__)),
}
(OUT / 'boundary/independent_report_review.json').write_text(
    json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: receipt[k] for k in ('passed', 'report', 'local_links_checked',
                 'immutable_source_and_current_delivery_hashes_checked',
                 'final_generation_receipt_hashes_checked')}))
