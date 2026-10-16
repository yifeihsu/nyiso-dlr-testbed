"""Inspect evidence-bound P34 qualifications without rewriting frozen inputs.

This is a use gate, not a unit converter. Conditional DC use keeps the existing
posted-number convention. Stronger physical claims require evidence that is
currently absent. P53A schedules are a separate data product.
"""
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_p34_qualification'
CONTRACT = OUT / 'P34_qualification_contract.json'
PTIDS = {25118, 25119, 625149, 625150}
USES = ('conditional_dc', 'verified_native_MW', 'measured_physical_telemetry',
        'historically_verified_sign', 'physical_thermal_validation')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_contract(path=CONTRACT):
    contract = json.loads(Path(path).read_text(encoding='utf-8'))
    require(contract['schema_version'] == 1, 'Unsupported qualification schema')
    channels = contract['channels']
    require(len(channels) == 4 and {c['ptid'] for c in channels} == PTIDS,
            'P34 channel set changed or duplicated')
    source_key = 'output/nygrid_2025_p34_qualification/sources/primary_evidence_conclusion.json'
    required = {source_key,
                'output/nygrid_2025_par_controls/controls/input_receipt.json',
                'System Matpower Format/npcc_nygrid_2025_dover_dc.m',
                'output/nygrid_2025_dover_parameters/replay/operating_states.mat',
                'output/nygrid_2025_dover_parameters/replay/replay_receipt.json'}
    require(required <= set(contract['dependencies']), 'Missing required evidence dependencies')
    for rel, digest in contract['dependencies'].items():
        target = (ROOT / rel).resolve()
        require(target.is_relative_to(ROOT), 'Dependency escapes repository')
        require(target.is_file() and sha(target) == digest, 'Stale dependency: ' + rel)
    primary = json.loads((ROOT / source_key).read_text(encoding='utf-8'))
    require(primary['passed'] and primary['audit_complete'], 'Primary audit is incomplete')
    require(contract['native_numeric_MW_unit_verified'] == primary['physical_unit_confirmed'],
            'Unit qualification contradicts primary evidence')
    require(contract['actual_measurement_origin_verified']
            == primary['product_kind']['independent_metered_actual_confirmed'],
            'Measurement-origin qualification contradicts primary evidence')
    require(primary['native_timestamp_support_status']
            == 'unresolved_begin_end_instantaneous_or_average'
            and contract['native_timestamp_support_verified'] is False,
            'Timestamp qualification requires a new evidence review')
    require(contract['raw_numeric_policy']['interval_energy_multiplier'] == 1,
            'Unreviewed unit conversion')
    require(contract['raw_numeric_policy']['conversion_is_assumption'],
            'Conditional unit policy was promoted without new evidence')
    controls = json.loads((ROOT / 'output/nygrid_2025_par_controls/controls/input_receipt.json').read_text())
    require(contract['raw_numeric_policy']['gamma'] == controls['gamma']
            and contract['raw_numeric_policy']['gamma_applied_once'] is True,
            'Power-scale contract changed')
    require(controls['P34_time_policy']
            == 'Frozen forward-held means; complete3600seconds and source gap<=600seconds; no fill or clipping.'
            and contract['raw_numeric_policy']['time_aggregation']
            == 'forward_hold_max600s;complete3600s;retain_UTC_DST;no_missing_zero_fill'
            and contract['raw_numeric_policy']['literal_source_column'] == primary['raw_header'],
            'Native field or aggregation policy changed')
    for c in channels:
        require(c['raw_to_NY_import_multiplier'] == 1
                and c['raw_to_NY_export_multiplier'] == -1,
                'Unreviewed sign convention')
        ontario = c['ptid'] in (25118, 25119)
        evidence = primary['sign']['Ontario_StLawrence' if ontario else 'Dover']
        expected_historical = evidence['applies_to_2025'] if ontario else evidence['specific_2025_effective_date_confirmed']
        require(c['ptid'] in evidence['ptids']
                and c['historical_2025_sign_verified'] == expected_historical
                and c['documentary_direction_verified'] == evidence['documented_convention_confirmed']
                and c['explicit_effective_date'] == (evidence['explicit_convention_date'] if ontario else None),
                'Per-device historical sign contradicts primary evidence')
        require(c['family'] == ('Ontario' if ontario else 'Dover')
                and c['documented_positive_from'] == ('St Lawrence / IESO' if ontario else 'Long Mountain / ISONE')
                and c['documented_positive_to'] == ('Moses / NYISO' if ontario else 'Cricket Valley / NYISO'),
                'Per-device endpoint identity changed')
    return contract


def inspect_use(contract, use, ptids=None):
    require(use in USES, 'Unknown use')
    requested = PTIDS if ptids is None else set(ptids)
    require(bool(requested) and requested <= PTIDS, 'Unknown or empty P34 channel set')
    channels = [c for c in contract['channels'] if c['ptid'] in requested]
    reasons = []
    if use in ('verified_native_MW', 'measured_physical_telemetry', 'physical_thermal_validation'):
        if not contract['native_numeric_MW_unit_verified']:
            reasons.append('Native P34 numeric units/interval basis are not directly verified.')
    if use in ('measured_physical_telemetry', 'physical_thermal_validation'):
        if not contract['actual_measurement_origin_verified']:
            reasons.append('SCADA measurement versus dispatch-calculated publication origin is unverified.')
        if not contract['native_timestamp_support_verified']:
            reasons.append('Native timestamp support (begin/end/instantaneous/average) is unverified.')
    if use in ('historically_verified_sign', 'measured_physical_telemetry', 'physical_thermal_validation'):
        unresolved = [c['ptid'] for c in channels if not c['historical_2025_sign_verified']]
        if unresolved:
            reasons.append('2025 sign effective date is unverified for PTIDs ' + str(unresolved) + '.')
    if use == 'physical_thermal_validation':
        reasons.append('P34 active flow alone does not establish terminal current, Q, voltage, cooling or switching state.')
    return dict(use=use, ptids=sorted(requested), allowed=not reasons,
                status='conditional_research_use' if use == 'conditional_dc' else 'evidence_gate',
                reasons=reasons, numeric_data_changed=False,
                retained_policy=contract['raw_numeric_policy'], channels=channels)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--use', choices=USES, default='conditional_dc')
    parser.add_argument('--ptid', type=int, action='append')
    args = parser.parse_args()
    result = inspect_use(load_contract(), args.use, args.ptid)
    print(json.dumps(result, indent=2))
    return 0 if result['allowed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
