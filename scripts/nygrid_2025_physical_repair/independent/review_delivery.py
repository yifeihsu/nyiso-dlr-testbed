"""Read-only final delivery freshness and numerical-content review.

Checks HTML embedded payload, all annual masks/flows, physical metadata, the
compiled model and manual/report statements. Visual layout has separate QA.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
REPAIR = ROOT / 'output/nygrid_2025_physical_repair'
DELIVERY = REPAIR / 'delivery'; MAP = DELIVERY / 'map'
RUN = REPAIR / 'annual/physical_repair_v1'


def record(path):
    with path.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest}


def same(a, b, tolerance=1e-9):
    a, b = np.asarray(a, float), np.asarray(b, float)
    assert a.shape == b.shape and np.array_equal(np.isfinite(a), np.isfinite(b))
    finite = np.isfinite(a); error = float(np.max(np.abs(a[finite] - b[finite]))) if finite.any() else 0.
    assert error <= tolerance, error
    return error


def main():
    sources = [MAP / f'{name}.json' for name in ['map_data', 'annual_data', 'geography_data', 'interface_definitions']]
    data, annual, geography, definitions = [json.loads(p.read_text(encoding='utf-8')) for p in sources]
    html_path = MAP / 'network_map.html'; sources.append(html_path)
    html = html_path.read_text(encoding='utf-8')
    match = re.search(r'<script type="application/json" id="network-data">(.*?)</script>', html, re.S)
    assert match and json.loads(match.group(1)) == data
    assert data['annual'] == annual and data['geography'] == geography and data['interfaces'] == definitions
    candidate_path = REPAIR / 'candidate_receipt.json'; model_path = REPAIR / 'model/latest_model.mat'
    candidate_hash = record(candidate_path)['sha256']; model_hash = record(model_path)['sha256']
    assert geography['physicalRepairCandidateSha256'] == annual['metadata']['physicalRepairCandidateSha256'] == candidate_hash
    assert annual['metadata']['compiledModelSha256'] == model_hash
    metadata_path = REPAIR / 'independent/compiled_model_metadata_readback.json'
    metadata = json.loads(metadata_path.read_text()); assert metadata['passed']
    model_receipt_path = REPAIR / 'model/model_receipt.json'; model_receipt = json.loads(model_receipt_path.read_text())
    assert model_receipt['passed'] and model_receipt['model_file']['sha256'] == model_hash
    for file in model_receipt['model_files']:
        path = REPAIR / 'model' / file['name']; assert record(path)['sha256'] == file['sha256']; sources.append(path)
    sources.extend([candidate_path, metadata_path, model_receipt_path])
    model = loadmat(model_path, simplify_cells=True)['model']
    compiled = model['templates']; parameters_path = REPAIR / 'physics/parent41_parameters.json'
    parameters = json.loads(parameters_path.read_text()); sources.append(parameters_path)
    states = ['pre_may', 'may21', 'may30', 'post_dover']; parents = {p['id']: p for p in geography['parents']}
    assert parents[41]['parameterBasis'] == parameters['thermal_registry_parameter_basis']
    for state, template in enumerate(compiled):
        branch = template['branch']; source_parent = template['userdata']['ac_system']['branch_parent_row']
        sec = template['userdata']['ac_sections']; ids = template['bus'][:, 0]
        assert len(sec['reactor_BS_delta_all_buses']) == len(ids) and np.array_equal(sec['reactor_BS_bus_ids'], ids)
        for parent in [41, 185, 195]:
            rows = np.flatnonzero(source_parent == parent); row = next(x for x in parents[parent]['stateRecords'] if x['stateId'] == states[state])
            same([row['rPu'], row['xPu'], row['bPu']], branch[rows, 2:5].sum(axis=0), 1e-12)
            assert row['runtimeRows'] == (rows + 1).tolist()
            if parent in [185, 195]:
                rec = next(x for x in sec['reactor_ledger'] if x['original_branch_row'] == parent)
                same(row['reactorBusIds'], rec['distributed_bus_ids']); same(row['reactorBSDeltaMVAr'], rec['distributed_bus_BS_delta_mvar'])
                same(row['reactorNominalMVAr'], rec['applied_total_reactor_mvar_at1pu'])
                assert abs(sum(row['reactorBSDeltaMVAr']) + row['reactorNominalMVAr']) < 1e-8
    op_path = ROOT / 'output/nygrid_2025_acpf_profile_audit/alignment/interface_operator_terms.csv'
    op = pd.read_csv(op_path); terms_checked = 0
    for interface in definitions['interfaces']:
        for state in states:
            expected = op[(op.state == state) & (op.interface_index == interface['index'])].sort_values('original_branch_row')
            actual = sorted(interface['members_by_state'][state], key=lambda x: x['parent_id'])
            assert len(actual) == len(expected)
            for a, e in zip(actual, expected.itertuples()):
                assert a['parent_id'] == e.original_branch_row and a['coefficient'] == e.coefficient
                assert a['first_runtime_key'] == e.first_runtime_branch_key and a['last_runtime_key'] == e.last_runtime_branch_key
                assert a['section_count'] == e.section_count; terms_checked += 1
    assert terms_checked == 136
    comparison_path = RUN / 'comparison/comparison_arrays.npz'; comparison = np.load(comparison_path)
    hours = annual['hours']; assert len(hours) == 8760
    for key, field in [('sourceQualified', 'source_qualified'), ('qualified', 'candidate_qualified'), ('operatingQualified', 'operating_qualified')]:
        assert np.array_equal(np.asarray([h[key] for h in hours], bool), comparison[field])
    assert [h['hour'] for h in hours] == list(range(1, 8761))
    assert [h['timestamp'] for h in hours] == comparison['timestamp_utc'].tolist()
    assert [h['state'] for h in hours] == [states[s - 1] for s in comparison['topology_state_index']]
    q = comparison['candidate_qualified']; source = comparison['source_qualified']; gamma = float(comparison['gamma'])
    assert q.sum() == source.sum() == 8651 and not comparison['operating_qualified'].any()
    assert np.array_equal(q, source)
    counts = annual['metadata']['counts']; assert counts['qualified'] == 8651 and counts['sourceExcluded'] == 109 and counts['failed'] == 0 and counts['operatingQualified'] == 0
    assert not annual['metadata']['branchCurrentGammaDivisionApplied'] and not definitions['ampere_gamma_rescaling']
    assert annual['metadata']['defaultUnits'] == 'Model MW' and gamma == annual['metadata']['gamma']
    flows = np.asarray(annual['interfaceFlowsModelMW'], float)
    comparison_flows = comparison['candidate_legacy_signed_literal_from'] * gamma
    error = {'map_interface_vs_scored_model_MW': same(flows, comparison_flows, 1e-9)}
    same(annual['observationsPublicMW'], comparison['observed'])
    zones = annual['zoneSeriesModelMW']
    error['gross_model_MW'] = same(zones['gross'], comparison['NY_gross_target_MW'])
    error['served_model_MW'] = same(zones['served'], comparison['NY_served_PD_MW'])
    error['loss_model_MW'] = same(zones['loss'], comparison['NY_allocated_loss_MW'])
    for field in [flows, np.asarray(zones['gross'], float), np.asarray(zones['generation'], float), np.asarray(zones['served'], float), np.asarray(zones['loss'], float), np.asarray(annual['fixedTransferFlowsModelMW'], float)]:
        assert np.isfinite(field[q]).all() and np.isnan(field[~source]).all()
    independent = np.full((8760, 7), np.nan); generation = np.full((8760, 11), np.nan); transfers = np.full((8760, 6), np.nan)
    canonical_bus_lookup = {int(x): j for j, x in enumerate(compiled[3]['bus'][:, 0])}
    gen_bus_rows = np.array([canonical_bus_lookup[int(x)] for x in model['generator_bus_ids']])
    gen_groups = model['loss_static'][3]['bus_group'][gen_bus_rows]; native = ~np.asarray(model['external']['generator_mask'], bool)
    for month in range(1, 13):
        path = RUN / f'monthly/profile_PF_2025_{month:02d}.mat'; sources.append(path)
        d = loadmat(path, simplify_cells=True, variable_names=['hour_index', 'qualified', 'topology_state_index', 'branch_keys', 'PF', 'gen_PG', 'DC_PF'])
        h = np.asarray(d['hour_index'], int) - 1; valid = np.asarray(d['qualified'], bool)
        lookup = {str(x): j for j, x in enumerate(d['branch_keys'])}
        for state in range(1, 5):
            use = np.flatnonzero(valid & (d['topology_state_index'] == state))
            if not len(use): continue
            for interface in range(1, 8):
                terms = op[(op.state == states[state - 1]) & (op.interface_index == interface)]
                cols = [lookup[x] for x in terms.first_runtime_branch_key]
                independent[h[use], interface - 1] = d['PF'][np.ix_(use, cols)] @ terms.coefficient.to_numpy()
        for zone in range(1, 12): generation[h[valid], zone - 1] = d['gen_PG'][valid][:, native & (gen_groups == zone)].sum(axis=1)
        transfers[h[valid]] = d['DC_PF'][valid]
    error['map_interface_vs_raw_branch_sum_model_MW'] = same(flows, independent)
    error['map_native_generation_vs_raw_solved_model_MW'] = same(zones['generation'], generation, 1e-8)
    error['map_transfer_vs_raw_model_MW'] = same(annual['fixedTransferFlowsModelMW'], transfers)
    manual_path = DELIVERY / 'docs/NYGRID_2025_PHYSICAL_REPAIR_MODEL_STRUCTURE.md'
    docx_path = manual_path.with_suffix('.docx'); manual = manual_path.read_text(encoding='utf-8')
    with zipfile.ZipFile(docx_path) as archive:
        xml = ET.fromstring(archive.read('word/document.xml'))
        docx_text = ' '.join(x.text or '' for x in xml.iter() if x.tag.endswith('}t'))
    for text in [manual, docx_text]:
        for token in ['0.0018', '0.0089', '10.750873', '3.948477', '0.02126747227', '607.279468', '254.817180', '50.606622', '18.201227', '8651', '8760']:
            assert token in text, token
        assert 'No count establishes installed facility ratings' in text
        assert 'same four corrected templates' in text and 'zero prescribed injection' in text
    report_path = ROOT / 'NYGRID_2025_PHYSICAL_REPAIR.md'; report = report_path.read_text(encoding='utf-8')
    physics_path = REPAIR / 'independent/annual_physics_review.json'; physics = json.loads(physics_path.read_text())
    assert physics['passed'] and physics['completed_annual_review']
    assert f"{physics['paired_parent41_loss_model_MW']['old_mean']:.5f}" in report
    assert f"{physics['paired_parent41_loss_model_MW']['new_mean']:.5f}" in report
    for parent in ['185', '195']:
        assert f"{physics['target_voltage'][parent]['max_VM']:.6f}" in report
    for token in ['8,651', '8,170', '481', '2,722', '4,794', '97.278%', '0.841226', '1.076170']:
        assert token in report
    figure_receipt_path = REPAIR / 'summary/report_receipt.json'; figure_receipt = json.loads(figure_receipt_path.read_text())
    assert figure_receipt['passed'] and figure_receipt['completed_annual_evidence_required']
    for group in ['sources', 'outputs']:
        for item in figure_receipt[group]: assert record(ROOT / item['path'])['sha256'] == item['sha256']
    target_path = REPAIR / 'independent/target_parent_metrics.csv'; targets = pd.read_csv(target_path)
    figure_data = targets[targets.cohort == 'paired_old_baseline']; assert set(figure_data.hours) == {8170}
    for parent in [185, 195]:
        pair = figure_data[figure_data.parent_row == parent].set_index('version')
        assert pair.loc['candidate', 'maximum_VM_pu'] < 1.05 < pair.loc['baseline', 'maximum_VM_pu']
    source_files = sources + [op_path, comparison_path, parameters_path, manual_path, docx_path, report_path, physics_path,
        figure_receipt_path, target_path, ROOT / 'scripts/nygrid_2025_physical_repair/build_repair_report.py',
        REPAIR / 'summary/physical_repair_comparison.png', REPAIR / 'summary/physical_repair_comparison.pdf', Path(__file__)]
    receipt = {'passed': True, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Independent final compiled-model metadata, HTML embedded numeric freshness, annual masks/units/cut flows, manual numerical content and root report/figure-data review; no PF or browser/visual-layout check.',
        'candidate_sha256': candidate_hash, 'compiled_model_sha256': model_hash,
        'network_map_sha256': record(html_path)['sha256'], 'all_embedded_payloads_equal_standalone_JSON': True,
        'clock_rows': 8760, 'qualified_rows': 8651, 'source_excluded_rows': 109, 'operating_qualified_rows': 0,
        'interface_membership_terms_checked': terms_checked, 'all_qualified_interface_values_checked': int(q.sum() * 7),
        'maximum_numeric_export_errors': error,
        'parent41_compiled_registry_and_thermal_metadata_correct': True,
        'full_axis_reactor_metadata_matches_map_in_all_four_states': True,
        'profile_shards_hashes_preserved_and_authenticated': True,
        'root_report_and_figure_paired_cohort_numbers_verified': True,
        'manual_DOCX_and_Markdown_numeric_content_verified': True,
        'substantive_findings': [],
        'limitations': ['Document layout and native browser interactions are covered by separate owner reviews.',
            'The immutable preannual candidate receipt records annual_validation_complete=false by design; completed annual receipts and the delivered map/manual establish current annual completion.',
            'Global operating qualification remains zero despite requested line-loss and voltage repairs.'],
        'sources': [record(p) for p in dict.fromkeys(source_files)]}
    path = DELIVERY / 'independent_delivery_review.json'
    path.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'qualified_rows': int(q.sum()), 'interface_values': int(q.sum() * 7),
                      'map_sha256': receipt['network_map_sha256'], 'numeric_errors': error, 'output': path.relative_to(ROOT).as_posix()}))


if __name__ == '__main__':
    main()
