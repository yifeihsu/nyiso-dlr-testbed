"""Freeze source-only two-factor intervention definitions before any ablation scoring."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_postrepair_diagnosis/ablations'
BASE = ROOT / 'output/nygrid_2025_moses_repair/annual'


def record(path):
    with path.open('rb') as f: digest = hashlib.file_digest(f, 'sha256').hexdigest()
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest, 'bytes': path.stat().st_size}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    old = loadmat(BASE / 'baseline_bundle/model/latest_model.mat', simplify_cells=True)['model']
    new = loadmat(BASE / 'candidate_bundle/model/latest_model.mat', simplify_cells=True)['model']
    assert len(old['generator_bus_ids']) == 1464 and len(new['generator_bus_ids']) == 1466
    for key in ['hour_index', 'state_index', 'source_qualified', 'reference_bus']:
        assert np.array_equal(old['axis'][key], new['axis'][key])
    assert old['scale_factor_gamma'] == new['scale_factor_gamma']
    for a, b in zip(old['templates'], new['templates']):
        assert np.array_equal(a['branch'], b['branch'])
        assert np.array_equal(a['bus'], b['bus'])
    gen = loadmat(ROOT / 'output/nygrid_2025_moses_repair/generation/generation_candidate.mat',
                  simplify_cells=True, variable_names=['stlawrence_rows_1based', 'hydro_rows_1based'])
    stl = np.asarray(gen['stlawrence_rows_1based'], int).reshape(-1) - 1
    pg = np.concatenate([loadmat(BASE / 'candidate_bundle/model' / name, simplify_cells=True)['profiles']['generator_PG_MW']
                         for name in ['profiles_h0001_4380.mat', 'profiles_h4381_8760.mat']])
    q = np.asarray(new['axis']['source_qualified'], bool)
    frozen_axes = loadmat(BASE / 'frozen_baseline_axes.mat', simplify_cells=True)
    times = np.asarray(frozen_axes['timestamp_utc'], str).reshape(-1)
    assert np.array_equal(frozen_axes['hour_index'], new['axis']['hour_index'])
    assert np.array_equal(frozen_axes['source_qualified'], q)
    months = pd.DatetimeIndex(pd.to_datetime(times, utc=True)).tz_convert('America/New_York').month.to_numpy()
    hours = [int((ix := np.flatnonzero(q & (months == m)))[np.argmax(pg[ix][:, stl].sum(axis=1))] + 1) for m in range(1, 13)]
    sources = []
    for bundle in ['baseline_bundle', 'candidate_bundle']:
        for name in ['latest_model.mat', 'profiles_h0001_4380.mat', 'profiles_h4381_8760.mat', 'model_receipt.json']:
            sources.append(BASE / bundle / 'model' / name)
    sources += list((BASE / 'candidate_bundle/runtime').rglob('*.m'))
    sources += [BASE / 'frozen_baseline_axes.mat', ROOT / 'output/nygrid_2025_moses_repair/generation/generation_policy.json',
                ROOT / 'output/nygrid_2025_moses_repair/generation/generation_candidate.mat',
                ROOT / 'output/nygrid_2025_moses_repair/boundary/PV20_source_receipt.json',
                ROOT / 'output/nygrid_2025_moses_repair/boundary/boundary_verification_receipt.json']
    recipe = {'schema_version': 1, 'source_HEAD': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        'created_utc': datetime.now(timezone.utc).isoformat(), 'predeclared_before_ablation_solves_and_metrics': True,
        'P32_observations_read_to_construct_interventions': False, 'source_qualified_hours': int(q.sum()),
        'clock_rows': 8760, 'gamma': float(new['scale_factor_gamma']), 'baseline_generator_rows': 1464,
        'common_generator_rows': 1466, 'unit21_row': 1465, 'PV20_boundary_row': 1466,
        'source_selected_bridge_hours': hours, 'bridge_selection': 'One maximum source-input StLawrence PG hour per local calendar month, using current compiled PG and frozen source mask only.',
        'scenarios': {
            'B': {'G': False, 'P': False, 'recipe': 'Baseline native PG and original native Pmin/Pmax; unit21 PG and bounds zero; original ISONE PG; PV20 PG and bounds zero.'},
            'G': {'G': True, 'P': False, 'recipe': 'Corrected hydro PG/monthly unit availability/native bounds; original ISONE PG; PV20 PG and bounds zero.'},
            'P': {'G': False, 'P': True, 'recipe': 'Baseline native PG/original native bounds; unit21 PG and bounds zero; current PV20 PG and compensated ISONE PG.'},
            'GP': {'G': True, 'P': True, 'recipe': 'Current compiled Moses repair exactly: corrected hydro/native bounds plus PV20 and compensated ISONE PG.'}},
        'common_case_reconstruction': 'After PG/Pmin/Pmax choice, rebuild status, bus PV/ref types, Qmin/Qmax, generator MBASE/VG, active/reactive gencost, generator p/capability/q/S references and objective weights using frozen current loader algebra. Fixed boundary never regulates voltage or shares losses. All inactive extra rows remain explicit zero rows.',
        'preserved': ['all existing AC/DC parameters and topology states', 'full-axis fixed shunts', 'all load profiles', 'other native fuel input', 'HQ', 'existing six DC inputs', 'regional net-import targets', 'source mask', 'gamma', 'all seven interface operators'],
        'bridge_contract': 'B on common 1466-row axis reproduces saved physical baseline; GP reproduces saved Moses candidate on each of 12 source-selected hours. Complex voltage and branch P/Q compare at 1e-8 pu / 1e-5 MVA.',
        'annual': 'Fresh G and P solves only after bridge pass; all 8651 source-qualified hours attempted; all8760 slots retained; no failure or source exclusion is promoted.',
        'validation': 'Independent all-hour direct branch laws, nodal KCL, generator PG preservation, fixed boundary P/Q, six DC inputs, loss ownership and regional accounting from compact saved arrays; metadata reconstructed independently on detailed sample cases.',
        'attribution': 'For each frozen metric f: G_shapley=0.5*((fG-fB)+(fGP-fP)); P_shapley=0.5*((fP-fB)+(fGP-fG)); interaction=fGP-fG-fP+fB. Negative MAE effects improve error. Within-model controlled-input causality only; no claim about real-system causality or physical meter certification.',
        'inputs': [record(p) for p in sorted(set(sources))], 'producer': record(Path(__file__))}
    target = OUT / 'scenario_recipe.json'
    if target.exists():
        prior = json.loads(target.read_text()); recipe['created_utc'] = prior['created_utc']; recipe['source_HEAD'] = prior['source_HEAD']
        assert recipe == prior, 'Preserve the frozen recipe; use a new diagnostic version for changed interventions.'
    else: target.write_text(json.dumps(recipe, indent=2)+'\n', encoding='utf-8')
    axes = OUT / 'source_axes.mat'
    values = {'hour_index':np.arange(1,8761), 'timestamp_utc':times, 'source_qualified':q,
              'topology_state_index':new['axis']['state_index'], 'model_month':months, 'bridge_hours':np.array(hours),
              'hydro_rows_1based':gen['hydro_rows_1based'], 'stlawrence_rows_1based':stl+1, 'gamma':float(new['scale_factor_gamma'])}
    if not axes.exists(): savemat(axes, values, do_compression=True)
    print(json.dumps({'frozen':True,'source_qualified_hours':int(q.sum()),'bridge_hours':hours,'recipe':record(target)}))


if __name__ == '__main__': main()
