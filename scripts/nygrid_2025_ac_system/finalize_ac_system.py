"""Seal a partially qualified synthetic AC system without promoting failed runs.

Verification checks evidence, coverage, current bytes and preserved prior cases.
It does not rerun power flow, select another operating cohort, or relax limits.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_ac_system'
SCRIPTS = ROOT / 'scripts/nygrid_2025_ac_system'
REPORT = ROOT / 'NYGRID_2025_AC_SYSTEM.md'
CONTRACT = OUT / 'AC_SYSTEM_CONTRACT.json'
MANIFEST = OUT / 'DELIVERY_MANIFEST.json'
PUBLIC = [ROOT / 'System Matpower Format' / n for n in
          ('npcc_nygrid_2025_ac.m', 'run_nygrid_2025_ac_dlr.m')]
REQUIRED = [
    'branches/branch_engineering_receipt.json', 'branches/branch_unit_validation.json',
    'branches/sectioned_design_receipt.json', 'branches/sectioned_matlab_runtime_validation.json',
    'engineering/engineering_defaults_validation.json', 'engineering/cable_candidates_receipt.json',
    'engineering/voltage_changing_classification_review.json',
    'engineering/composite_revision_independent_review.json',
    'engineering/sectioned_design_independent_review.json',
    'engineering/thermal_adapter_independent_review.json', 'engineering/report_review.json',
    'thermal/adapter_validation.json', 'thermal/public_api_smoke.json',
    'ac_validation/generator_capability_policy.json']


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def resolve(path, directory):
    p = Path(path)
    if p.is_absolute():
        if p.is_file():
            return p
        marker = '/WECC and NPCC Systems/'
        normalized = str(p).replace('\\', '/')
        require(marker in normalized, 'Unavailable external proof path: ' + str(p))
        return ROOT / normalized.split(marker, 1)[1]
    return ROOT / p if (ROOT / p).is_file() else directory / p


def verify_hashes(value, directory):
    if isinstance(value, list):
        return sum(verify_hashes(v, directory) for v in value)
    if not isinstance(value, dict):
        return 0
    checks = 0
    if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
        p = resolve(value['path'], directory)
        require(p.is_file() and sha(p) == value['sha256'], 'Stale proof: ' + str(p))
        checks += 1
    for key, child in value.items():
        if key in ('dependencies', 'outputs', 'files', 'reviewed_hashes') and isinstance(child, dict):
            for path, digest in child.items():
                if isinstance(digest, str) and re.fullmatch('[a-f0-9]{64}', digest):
                    p = resolve(path, directory)
                    require(p.is_file() and sha(p) == digest, 'Stale mapped proof: ' + str(p))
                    checks += 1
        checks += verify_hashes(child, directory)
    return checks


def package_files():
    return sorted([REPORT, *PUBLIC] + [p for base in (SCRIPTS, OUT) for p in base.rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc' and p != MANIFEST])


def main(verify=False):
    checks = 0
    for rel in REQUIRED:
        p = OUT / rel; proof = read(p)
        require(proof.get('passed') is True, 'Unpassed required construction/review proof: ' + rel)
        checks += verify_hashes(proof, p.parent)
    sealpath = OUT / 'ac_validation/validation_source_receipt.json'
    seal = read(sealpath)
    require(seal['integrity_audit_passed'] and not seal['all_hours_or_all_tested_snapshots_feasible']
            and not seal['global_infeasibility_proved_for_failed_hours'], 'Operating-evidence scope changed')
    require(seal['electrical_attempts'] == 7 and seal['thermal_attempts'] == 8
            and seal['thermal_qualified_points'] == 4 and seal['thermal_failed_points_retained'] == 4,
            'Operating cohort or qualification counts changed')
    checks += verify_hashes(seal, sealpath.parent)
    electrical = read(OUT / 'ac_validation/electrical_final/electrical_validation.json')
    require(electrical['complete'] and not electrical['passed']
            and not electrical['all_8760_hours_or_all_qualified_hours_AC_feasible_claimed'],
            'Do not promote a partly successful electrical cohort')
    qualified = sorted(c['hour_index'] for c in electrical['checks'] if c['passed'] and c['ACPF_replay_passed'])
    failed = sorted(c['hour_index'] for c in electrical['checks'] if not c['passed'])
    require(qualified == [2630, 8471, 8472, 8508] and failed == [523, 4000, 4194],
            'Declared selected-hour qualification changed')
    thermal = read(OUT / 'thermal/whole_system_validation.json')
    require(thermal['completed'] and thermal['snapshots'] == 8
            and not thermal['all_snapshot_constraints_passed']
            and not thermal['historical_annual_AC_DLR_replay_completed'], 'Thermal scope changed')
    flags = ['solver_success', 'electrical_pass', 'thermal_pass', 'terminal_current_pass', 'section_end_thermal_pass']
    successes = [c for c in thermal['results'] if all(c[k] for k in flags)]
    require(len(successes) == 4 and sorted({c['hour'] for c in successes}) == [2630, 8508],
            'Do not drop unsuccessful weather scenarios or promote failed states')
    independent_path = OUT / 'ac_validation/independent_thermal_snapshots/independent_thermal_snapshot_validation.json'
    independent = read(independent_path)
    require(independent['independent_audit_complete'] and independent['root_classification_confirmed']
            and independent['all_eight_inputs_preserved'] and independent['snapshot_attempts'] == 8
            and independent['qualified_constrained_operating_points'] == 4
            and independent['failed_OPF_trials_not_promoted'] == 4
            and independent['all_four_successful_points_ACPF_replay_passed']
            and not independent['conductor_temperature_equilibrium_validated'], 'Independent operating audit incomplete')
    checks += verify_hashes(independent, independent_path.parent)
    require(read(OUT / 'thermal/adapter_validation.json')['tests'] == 21
            and read(OUT / 'branches/branch_unit_validation.json')['tests_run'] == 11, 'Component test coverage changed')
    api = read(OUT / 'thermal/public_api_smoke.json')
    require(api['public_default_API_executed'] and api['hour_index'] == 8508
            and api['buses'] == 267 and api['OH_branches'] == 258 and api['OH_segments'] == 259,
            'Documented default entrypoint is not qualified')
    branch = read(OUT / 'branches/branch_engineering_receipt.json')
    require(branch['total_branch_records'] == 413 and branch['OH_branch_count'] == 186
            and branch['cable_realizations'] == 40 and branch['composite_terminal_envelopes_corrected'] == 65,
            'Whole-network parameter coverage changed')
    plan = read(OUT / 'branches/sectioned_design_receipt.json')
    require(plan['designed_extra_buses'] == 75 and plan['criteria']['reactor_fraction'] == .75,
            'Declared section/reactor design changed')
    # Verify prior deliveries as bytes, without repeating earlier simulations.
    preserved = []
    for rel in ('output/nygrid_2025_p34_qualification/DELIVERY_MANIFEST.json',
                'output/nygrid_2025_dover_parameters/DELIVERY_MANIFEST.json'):
        p = ROOT / rel
        for path, entry in read(p)['files'].items():
            require(sha(ROOT / path) == entry['sha256'], 'Prior artifact changed: ' + path)
            checks += 1
        preserved.append(dict(path=rel, sha256=sha(p)))
    contract = dict(
        modeltype='whole_network_synthetic_balanced_positive_sequence_AC',
        power_scale='existing_gamma_scaled_injections;solved_currents_used_directly',
        gamma_current_lift=False, original_model_artifacts_preserved=True,
        explicit_OH_corridors=186, cable_equivalents=40, unresolved_composite_interiors=65,
        pre_Dover_buses=266, post_Dover_buses=267, added_numerical_zero_injection_buses=75,
        selected_electrical_attempts=7, qualified_electrical_and_ACPF_hours=qualified,
        unqualified_selected_electrical_hours=failed, whole_network_weather_attempts=8,
        qualified_weather_points=[dict(hour=c['hour'], scenario=c['scenario']) for c in successes],
        failed_weather_points_retained=4, no_global_infeasibility_proof=True,
        all_year_AC_feasibility_established=False, historical_weather_bound=False,
        reference_temperature_resistance_not_equilibrium=True,
        composite_physical_interior_conductor_coverage_established=False,
        asbuilt_parameters_or_actual_equipment_ratings_certified=False,
        internal_interface_fitting=False,
        primary_entrypoints=[p.relative_to(ROOT).as_posix() for p in PUBLIC],
        operating_evidence_seal=dict(path=sealpath.relative_to(ROOT).as_posix(), sha256=sha(sealpath)),
        preserved_deliveries=preserved)
    if verify:
        require(read(CONTRACT) == contract, 'AC use contract changed')
    else:
        CONTRACT.write_text(json.dumps(contract, indent=2) + '\n', encoding='utf-8')
    links = re.findall(r'\[[^\]]+\]\(([^)]+)\)', REPORT.read_text(encoding='utf-8'))
    local = [v for v in links if not v.startswith(('http://', 'https://', '#'))]
    for link in local:
        p = ROOT / unquote(link.split('#')[0])
        if p == MANIFEST and not verify:
            continue
        require(p.is_file(), 'Missing report target: ' + link)
    files = {p.relative_to(ROOT).as_posix(): dict(sha256=sha(p), bytes=p.stat().st_size) for p in package_files()}
    expected_manifest = dict(
        status='constructed_synthetic_AC_system_with_explicitly_partial_operating_qualification',
        verification_passed=True, all_selected_operating_points_feasible=False,
        current_and_prior_file_proof_checks=checks, report_local_links=len(local),
        qualified_electrical_hours=qualified, unqualified_electrical_hours=failed,
        qualified_thermal_points=4, attempted_thermal_points=8, files=files)
    if verify:
        require(read(MANIFEST) == expected_manifest, 'Delivery bytes or qualification metadata changed after sealing')
    else:
        MANIFEST.write_text(json.dumps(expected_manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(verification_passed=True, verify=verify, files=len(files),
        bytes=sum(v['bytes'] for v in files.values()), proof_checks=checks, report_local_links=len(local),
        qualified_electrical_hours=qualified, unqualified_electrical_hours=failed,
        thermal_qualified=4, thermal_attempted=8, all_operating_points_feasible=False), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--verify', action='store_true')
    main(parser.parse_args().verify)
