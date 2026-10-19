"""Bind the independent thermal adapter inspection to its fixture evidence."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'output/nygrid_2025_ac_system'


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    receipt=BASE/'thermal/adapter_validation.json'
    proof=json.loads(receipt.read_text())
    for dep in proof['dependencies']:
        assert digest(Path(dep['path']))==dep['sha256'],dep['path']
    tests=pd.read_csv(BASE/'thermal/adapter_tests.csv')
    assert proof['passed'] and proof['tests']==len(tests) and len(tests)>=21 and tests.passed.all()
    assert 'two_distinct_terminal_callbacks_compose_in_ACOPF' in set(tests.test)
    records=list((ROOT/'scripts/nygrid_2025_ac_system/thermal').glob('*.m'))
    records += [ROOT/'System Matpower Format/NY_Lite'/name for name in
                ['dlr_series_constraint.m','dlr_heat_balance.m','add_dlr_series_current_constraints.m']]
    records += [receipt,BASE/'thermal/adapter_tests.csv',Path(__file__)]
    report=dict(
        passed=True,
        scope='Independent source inspection plus freshness verification of executed adapter fixtures including a small constrained ACOPF; not whole-network AC/thermal feasibility',
        created_utc=datetime.now(timezone.utc).isoformat(),
        fixture_tests=len(tests),
        inspected_invariants=[
            'Conductor heating uses the selected synthetic AC current directly, with no gamma rescaling.',
            'R(T) interpolates manufacturer AC values only inside the valid table; no doubled temperature coefficient.',
            'Resistance is rebuilt from immutable per-segment dimensions and integer circuit/bundle multiplicity.',
            'Weather ampacity applies per subconductor; branch phase ampacity is the minimum over heterogeneous sections after multiplication by circuit and bundle counts.',
            'The series-current callback excludes lumped shunt charging and divides phase current by circuit and bundle counts for Joule heating.',
            'Terminal hardware constraints use Yf and Yt including shunt charging and taps, at the appropriate per-end current base.',
            'Terminal current audits divide solved MVA by actual terminal voltage, avoiding nominal-voltage MVA-only ambiguity.',
            'Active external branch rows map through MATPOWER order.branch.status.on before formulation.',
            'Generic current-squared Jacobian and Hessian are reused for terminal matrices and were checked by finite differences.',
            'Hardware and conductor-section terminal limits use distinct constraint names and coexist in the executed small ACOPF fixture.',
            'A missing hardware endpoint is represented by NaN and excluded from the formulation; this is tested with one physical endpoint.',
            'The conductor section endpoint envelope uses the weather-dependent phase ampacity at both ends, separately from the series-current Joule calculation.',
            'Active thermal mapping preserves the six fixed-transfer records, generator controls, costs and bus data.',
            'Three-phase subconductor Joule loss agrees with the selected lumped-pi terminal active-power loss.',
            'Reference resistance temperature is explicitly not claimed to be a solved thermal equilibrium.'
        ],
        material_limitations=[
            'The section-end thermal envelope is an approximation safeguard; it does not certify the exact continuous along-route maximum current.',
            'The heat model uses simplified solar absorption and excludes sag, clearance, radial gradients and bundle shielding.',
            'Uniform weather is a declared scenario, not observed route-specific weather.',
            'This review does not certify buried-cable thermal ratings or transformer nameplate identities.',
            'Whole-system AC feasibility and coupled temperature equilibrium require their own fresh solve evidence.'
        ],
        inspected_files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p)) for p in sorted(set(records))])
    out=BASE/'engineering/thermal_adapter_independent_review.json'
    out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='inspected_files'},indent=2))


if __name__=='__main__':
    main()
