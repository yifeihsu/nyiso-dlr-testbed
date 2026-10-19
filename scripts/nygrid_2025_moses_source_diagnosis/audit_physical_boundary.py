"""Recheck the model cut and documentary physical-meter boundary independently."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_moses_source_diagnosis/physical_boundary'
BASE = ROOT / 'output/nygrid_2025_flowgate_definitions'


def receipt(path):
    return {'path': path.relative_to(ROOT).as_posix(),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    defs_path = BASE / 'definitions/all_seasonal_members.csv'
    candidates_path = BASE / 'local_model/candidates/physical_term_model_identifiability.csv'
    defs = pd.read_csv(defs_path)
    defs = defs.loc[defs.gate_id.eq('moses_south')].copy()
    candidates = pd.read_csv(candidates_path)
    candidates = candidates.loc[candidates.interface.str.upper().eq('MOSES SOUTH')].copy()
    assert len(defs) == 21 and not candidates.physical_2025_crosswalk_verified.any()
    defs.to_csv(OUT / 'seasonal_physical_Moses_members.csv', index=False)
    candidates.to_csv(OUT / 'physical_model_identifiability.csv', index=False)
    sources = [defs_path, candidates_path]
    for path, sha in defs[['source_pdf', 'source_pdf_sha256']].drop_duplicates().itertuples(index=False, name=None):
        p = ROOT / path
        assert receipt(p)['sha256'] == sha
        sources.append(p)
    model_path = ROOT / 'output/nygrid_2025_physical_repair/model/latest_model.mat'
    model = loadmat(model_path, simplify_cells=True)['model']
    sources.append(model_path)
    checks = []
    for state, (template, static) in enumerate(zip(model['templates'], model['loss_static']), 1):
        parent = np.asarray(static['parent'], int)
        frm, to = np.asarray(static['parent_from']), np.asarray(static['parent_to'])
        crossing = np.flatnonzero((frm == 4) ^ (to == 4)) + 1
        active = sorted(map(int, set(parent[template['branch'][:, 10] > 0]) & set(crossing)))
        inactive = sorted(map(int, set(crossing) - set(active)))
        assert active == [46, 51, 52] and inactive == [211]
        dcb = template['dcline']
        bg = dict(zip(template['bus'][:, 0].astype(int), np.asarray(static['bus_group'], int)))
        dc_crossing = [i + 1 for i, row in enumerate(dcb)
                       if row[2] > 0 and ((bg[int(row[0])] == 4) ^ (bg[int(row[1])] == 4))]
        assert dc_crossing == [5, 6]
        assert np.array_equal(dcb[4:6, :2], [[100, 48], [100, 48]])
        assert int(static['HQ']) == 1464 and template['gen'][1463, 0] == 48
        checks.append({'state_index': state, 'active_AC_crossing_parents': active,
                       'inactive_original_crossing_parent': inactive,
                       'prescribed_transfer_crossing_rows': dc_crossing,
                       'PAR_from_bus': 100, 'PAR_to_bus': 48,
                       'HQ_proxy_generator_row': 1464, 'HQ_proxy_bus': 48})
    result = {
        'status': 'passed_model_cut_and_source_definition_recheck',
        'state_checks': checks,
        'physical_definition_entries': len(defs),
        'entries_per_edition': defs.groupby('edition').size().to_dict(),
        'verified_2025_circuit_to_current_model_crosswalks': 0,
        'complete_model_AC_cut': True,
        'complete_AC_plus_prescribed_transfer_cut': False,
        'physical_P32_equivalence_proved': False,
        'summer_page_37_visual_inspection': 'All seven names, circuits, voltages and metered-end asterisks agree with the cached PDF page.',
        'summer_members': ['MSU1 765 kV', 'MA1 230 kV', 'MA2 230 kV', '4 115 kV', '5 115 kV', '13 115 kV', '3 115 kV'],
        'winter_2025_26_document_change': 'MA1/MA2 at Moses 230 kV become HA1/HA2 at Haverstock 345 kV; operational cutover hour is not supplied by study posting dates.',
        'boundary_assumptions': [
            'The reduced D-area accounting cut is assumed comparable to the public Moses South meter aggregate.',
            'The entire NYIS-HQT net interchange is assigned to one injection at bus48, while the physical corridor includes separately named Chateauguay/Massena and Cedars/Dennison paths.',
            'The two Ontario PAR observations are prescribed transfers to bus48; they are not AC cut members.',
            'A source-backed whole-cut equivalence could establish an aggregate model without seven explicit branches, but neither physical mapping nor that equivalence is presently certified.'
        ],
        'causal_MW_attributed_to_boundary_mismatch': None,
        'reason_attribution_unavailable': 'No circuit-resolved hourly telemetry or verified P32 expression/operational intervals are available in the audited sources.',
        'unknown_physical_terms_assumed_zero': False,
        'new_AC_runs': 0,
        'default_model_changed': False,
        'sources': [receipt(p) for p in sources]
    }
    (OUT / 'physical_boundary_review.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['status', 'physical_definition_entries', 'complete_model_AC_cut', 'physical_P32_equivalence_proved']}))


if __name__ == '__main__':
    main()
