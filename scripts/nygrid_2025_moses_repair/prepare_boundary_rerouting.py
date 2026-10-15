"""Reroute an observed northern component without changing regional net input."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_moses_repair/boundary'
BASE = ROOT / 'output/nygrid_2025_physical_repair/model'


def record(path):
    with path.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=digest)


def redistribute(old, lo, hi, weight, target):
    """Unique bounded weighted least-change projection, without flow targets."""
    assert lo.sum() - 1e-7 <= target <= hi.sum() + 1e-7
    assert np.all(weight > 0)
    left = float(np.min((lo-old)/weight)) - 1
    right = float(np.max((hi-old)/weight)) + 1
    for _ in range(90):
        mid = (left+right)/2
        if np.clip(old+mid*weight, lo, hi).sum() < target:
            left = mid
        else:
            right = mid
    return np.clip(old+(left+right)/2*weight, lo, hi)


def main():
    model = loadmat(BASE / 'latest_model.mat', simplify_cells=True)['model']
    gamma = float(model['scale_factor_gamma'])
    q = np.asarray(model['axis']['source_qualified'], bool)
    pvfile = OUT / 'PV20_hourly_source.csv'
    pv = pd.read_csv(pvfile)
    assert len(pv) == 8760
    flow = pv['PV20_SandBar_import_to_NY_proxy_MW'].to_numpy(float)
    assert np.isfinite(flow[q]).all()
    profiles = [loadmat(BASE / f'profiles_h{a:04d}_{b}.mat', simplify_cells=True)['profiles']
                for a, b in [(1, 4380), (4381, 8760)]]
    pg = np.concatenate([p['generator_PG_MW'] for p in profiles]) / gamma
    s0 = model['loss_static'][0]
    groups = np.asarray(s0['external_gen_group'])
    rows = np.flatnonzero((groups == 12) & (np.asarray(s0['generator_share']) > 0))
    new = pg[:, rows].copy()
    for i in np.flatnonzero(q):
        p = model['loss_static'][int(model['axis']['state_index'][i])-1]
        er = np.asarray(p['finite_external_generator_rows'], int)-1
        lower = dict(zip(er, np.asarray(p['finite_external_Pmin_MW'], float)/gamma))
        upper = dict(zip(er, np.asarray(p['finite_external_Pmax_MW'], float)/gamma))
        lo = np.array([lower[r] for r in rows]); hi = np.array([upper[r] for r in rows])
        weights = np.asarray(p['generator_share'], float)[rows]
        new[i] = redistribute(pg[i, rows], lo, hi, weights, pg[i, rows].sum()-flow[i])
    error = new[q].sum(axis=1) + flow[q] - pg[q][:, rows].sum(axis=1)
    assert np.max(abs(error)) < 1e-7
    path = OUT / 'boundary_rerouting.mat'
    savemat(path, dict(ISONE_pool_rows_1based=rows+1, ISONE_pool_PG_public_MW=new,
                      PV20_boundary_PG_public_MW=flow, source_qualified=q,
                      original_ISONE_pool_PG_public_MW=pg[:, rows]), do_compression=True)
    summary = pd.DataFrame(dict(hour_index=np.arange(1, 8761), qualified=q,
                                PV20_import_public_MW=flow,
                                old_pool_public_MW=pg[:, rows].sum(axis=1),
                                rerouted_pool_public_MW=new.sum(axis=1)))
    summary.to_csv(OUT / 'regional_rerouting_hourly.csv', index=False)
    proof = dict(passed=True, hours=8760, qualified_hours=int(q.sum()),
                 external_region='ISONE', original_ISONE_generator_rows_1based=(rows+1).tolist(),
                 boundary_generator_row_1based=1466, boundary_NY_bus_id=49,
                 boundary_positive_direction='import into New York', fixed_Q_MVAr=0,
                 maximum_regional_total_preservation_error_public_MW=float(np.max(abs(error))),
                 baseline_global_P_balance_preserved=True,
                 preserved_other_fuels=True, preserved_native_generation=True,
                 per_hour_source_values_fitted_to_internal_interfaces=False,
                 physical_PV20_meter_equivalence_certified=False,
                 meter_proxy_assumption='Sand Bar PAR reading used at the Plattsburgh aggregate port; South Hero net load, intervening losses and bypass differences remain unresolved.',
                 redistribution='Bounded weighted least-squares change in the existing ISONE pool, using its unchanged loss-allocation shares as positive weights.',
                 excluded_hours_modified_in_existing_pool=False,
                 sources=[record(pvfile), record(BASE/'latest_model.mat'), *[record(BASE/f'profiles_h{a:04d}_{b}.mat') for a,b in [(1,4380),(4381,8760)]]],
                 output=record(path))
    (OUT / 'boundary_rerouting_receipt.json').write_text(json.dumps(proof, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: proof[k] for k in ['passed', 'qualified_hours', 'maximum_regional_total_preservation_error_public_MW']}))


if __name__ == '__main__':
    main()
