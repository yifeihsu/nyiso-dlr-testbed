"""Copy immutable DC comparator arrays to a MATLAB-readable experiment input.

No observed interface series is read. The selected worst-case hour IDs are
post-hoc diagnostic selections supplied by the independent measurement audit.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
from scipy.io import savemat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_centraleast_diagnosis/experiments'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'output/nygrid_2025_dover_parameters/replay/bounded_x_nominal.npz'
    score = ROOT / 'output/nygrid_2025_dover_parameters/comparison/scoring_receipt.json'
    proof = json.loads(score.read_text())
    assert proof['passed']
    for r in proof['dependencies'] + proof['outputs']:
        assert sha(ROOT / r['path']) == r['sha256'], r['path']
    with np.load(source, allow_pickle=False) as d:
        arrays = {name: d[name] for name in ['hour_index', 'timestamp_utc', 'qualified', 'network_state_ids', 'gamma', 'bus_va', 'interface_pf', 'bank_shift_model_deg', 'post_full_service']}
    assert np.array_equal(arrays['hour_index'], np.arange(1, 8761)) and arrays['qualified'].sum() == 8651
    arrays['primary_hours'] = np.array([2630, 4194, 523, 4000, 8508, 8471, 8472, 3360])
    arrays['additional_diagnostic_extremes'] = np.array([4746, 4213, 4740])
    dest = OUT / 'archived_DC_reference.mat'
    savemat(dest, arrays, do_compression=True)
    receipt = dict(passed=True, observations_read=False, primary_hours=arrays['primary_hours'].tolist(),
        diagnostic_extreme_hours=arrays['additional_diagnostic_extremes'].tolist(),
        source=dict(path=source.relative_to(ROOT).as_posix(), sha256=sha(source)),
        output=dict(path=dest.relative_to(ROOT).as_posix(), sha256=sha(dest)),
        source_scoring_receipt=dict(path=score.relative_to(ROOT).as_posix(), sha256=sha(score)),
        gamma=float(arrays['gamma']), qualified_hours=8651)
    (OUT / 'archived_DC_reference_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
