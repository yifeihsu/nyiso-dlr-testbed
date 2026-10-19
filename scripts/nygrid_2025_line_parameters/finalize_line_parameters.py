"""Seal current source, numerical and independent-validation evidence."""
from pathlib import Path
import argparse
import json
import re
from urllib.parse import unquote
from build_estimates import ROOT,OUT,sha,dump,require

SCRIPTS=ROOT/'scripts/nygrid_2025_line_parameters'
REPORT=ROOT/'NYGRID_2025_LINE_PARAMETER_ESTIMATION.md'
LOADER=ROOT/'System Matpower Format/npcc_nygrid_2025_line_estimated_dc.m'
MANIFEST=OUT/'DELIVERY_MANIFEST.json'
RECEIPTS=[
    'local_inventory/existing_assignment_receipt.json',
    'conductors/catalog_validation.json','estimates/engineering_basis.json',
    'validation/parameter_source_review.json','validation/physics_validation.json',
    'validation/estimate_values_validation.json','validation/cable_catalog_validation.json',
    'validation/independent_parameter_overlay_validation.json',
    'validation/annual_replay_validation.json','validation/comparison_validation.json',
    'validation/matlab_validation.json','replay/replay_receipt.json',
    'comparison/scoring_receipt.json']
SCENARIOS=['identity_reference','engineering_nominal','geometry_spacing_80pct','geometry_spacing_120pct','ground_image_30ft']


def resolve(path,directory):
    path=Path(path)
    if path.is_absolute():
        # MATLAB receipts retain their originating absolute path. Rebase only
        # paths demonstrably inside this named repository for another checkout.
        if path.is_file():return path
        text=str(path).replace('\\','/')
        marker='/WECC and NPCC Systems/'
        require(marker in text,'Missing absolute proof path outside repository: '+text)
        return ROOT/text.split(marker,1)[1]
    return ROOT/path if (ROOT/path).is_file() else directory/path


def verify_proof(obj,directory):
    n=0
    if isinstance(obj,list):return sum(verify_proof(x,directory) for x in obj)
    if not isinstance(obj,dict):return 0
    if isinstance(obj.get('path'),str) and isinstance(obj.get('sha256'),str):
        p=resolve(obj['path'],directory)
        require(p.is_file() and sha(p)==obj['sha256'],'Stale file proof: '+str(p));n+=1
    for key,val in obj.items():
        if key in ['dependencies','outputs','reviewed_hashes'] and isinstance(val,dict):
            for path,digest in val.items():
                if isinstance(digest,str) and re.fullmatch('[a-f0-9]{64}',digest):
                    p=resolve(path,directory)
                    require(p.is_file() and sha(p)==digest,'Stale dictionary proof: '+str(p));n+=1
        n+=verify_proof(val,directory)
    return n


def files():
    return sorted([REPORT,LOADER]+[p for base in (SCRIPTS,OUT) for p in base.rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p!=MANIFEST])


def main(verify=False):
    checks=0
    required=RECEIPTS+[f'overlays/{s}/overlay_receipt.json' for s in SCENARIOS]
    for relative in required:
        path=OUT/relative;proof=json.loads(path.read_text(encoding='utf-8'))
        require(proof.get('passed') is True,'Unpassed required proof: '+relative)
        checks+=verify_proof(proof,path.parent)
        if relative.startswith('overlays/'):
            require(proof['script_sha256']==sha(SCRIPTS/'build_parameter_overlay.py'),'Stale overlay code')
    physics=json.loads((OUT/'validation/physics_validation.json').read_text())
    require(physics['physics_code_sha256']==sha(SCRIPTS/'line_physics.py')
        and physics['test_code_sha256']==sha(SCRIPTS/'test_line_physics.py'),'Stale physics tests')
    annual=json.loads((OUT/'validation/annual_replay_validation.json').read_text())
    require(annual['scenario_hours']==43255 and annual['hours_per_scenario']==8651
        and not annual['internal_interface_observations_read'],'Annual cohort/qualification changed')
    matlab=json.loads((OUT/'validation/matlab_validation.json').read_text())
    require(matlab['fresh_MATPOWER_DC_snapshots']==35 and not matlab['full148_bus_AC_validated']
        and matlab['maximum_six_transfer_error_model_mw']==0,'MATLAB scope or transfer preservation failed')
    comparison=json.loads((OUT/'comparison/scoring_receipt.json').read_text())
    require(comparison['annual_rows']==35 and comparison['monthly_rows']==420
        and comparison['source_nominal_case_not_selected_by_scores'],'Comparison scope changed')
    basis=json.loads((OUT/'estimates/engineering_basis.json').read_text())
    require(basis['preferred_scenario']=='engineering_nominal'
        and not basis['rating_is_current_operational_facility_rating'],'Engineering qualification changed')
    links=re.findall(r'\[[^\]]+\]\(([^)]+)\)',REPORT.read_text(encoding='utf-8'))
    local=[p for p in links if not p.startswith(('http://','https://','#'))]
    for link in local:
        target=ROOT/unquote(link.split('#')[0])
        if target==MANIFEST and not verify:continue
        require(target.is_file(),'Missing report link: '+link)
    content={p.relative_to(ROOT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in files()}
    if verify:
        existing=json.loads(MANIFEST.read_text(encoding='utf-8'))
        require(content==existing['files'],'Packaged files changed since finalization')
    else:
        dump(MANIFEST,dict(status='validated_engineering_estimates_and_DC_replay;physical_gaps_explicit',
            active_full191_parameter_rows_changed=[391,410],retained_full191_project_rows_exact=[393,394,408,409],
            original_model_artifacts_preserved=True,source_observation_fitting=False,
            full_network_AC_or_actual_thermal_or_physical_flowgate_certification=False,
            source_proof_hash_checks=checks,report_local_links_checked=len(local),
            matched_annual_scenario_hours=43255,fresh_MATPOWER_snapshots=35,
            remaining_gaps=['Dover_PAR_series_impedance_and_tap_states','RCC_installed_cable_parameters',
                            'F84_route_average_geometry_and_terminal_limits','physical_flowgate_telemetry_bindings'],
            files=content))
    print(json.dumps(dict(passed=True,verify=verify,files=len(content),
        total_bytes=sum(x['bytes'] for x in content.values()),proof_hash_checks=checks,
        report_local_links=len(local),scenario_hours=43255,matlab_snapshots=35),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true')
    main(parser.parse_args().verify)
