"""Verify and seal the applied, explicitly qualified Dover reconstruction."""
from pathlib import Path
import argparse
import importlib.util
import json
import re
from urllib.parse import unquote
from build_dover_network import ROOT,OUT,SCRIPTS,sha,dump,require

REPORT=ROOT/'NYGRID_2025_DOVER_PARAMETERS_APPLIED.md'
LOADER=ROOT/'System Matpower Format/npcc_nygrid_2025_dover_dc.m'
MANIFEST=OUT/'DELIVERY_MANIFEST.json'
RECEIPTS=[
 'sources/dover_source_evidence_receipt.json','engineering/engineering_validation.json',
 'network/network_receipt.json','validation/source_model_review.json',
 'validation/independent_network_validation.json',
 'local_audit/Dover_P34_input_receipt.json','local_audit/Dover_P34_independent_validation.json',
 'local_audit/Dover_network_independent_validation.json',
 'local_audit/Dover_final_replay_validation.json','local_audit/Dover_comparison_validation.json',
 'replay/replay_receipt.json','comparison/scoring_receipt.json','validation/matlab_validation.json']


def files():
    return sorted([REPORT,LOADER]+[p for base in (SCRIPTS,OUT) for p in base.rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p!=MANIFEST])


def main(verify=False):
    # Reuse the already delivered generic path/hash verifier. It does not run
    # earlier builders or mutate their outputs.
    helper=ROOT/'scripts/nygrid_2025_line_parameters/finalize_line_parameters.py'
    spec=importlib.util.spec_from_file_location('line_proof_helper',helper)
    module=importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0,str(helper.parent));spec.loader.exec_module(module)
    checked=0
    for rel in RECEIPTS:
        p=OUT/rel;proof=json.loads(p.read_text(encoding='utf-8'))
        require(proof.get('passed') is True,'Unpassed required receipt: '+rel)
        checked+=module.verify_proof(proof,p.parent)
    engineer=json.loads((OUT/'engineering/engineering_validation.json').read_text())
    require(engineer['engineering_code_sha256']==sha(SCRIPTS/'engineering/pst_model.py')
        and engineer['test_code_sha256']==sha(SCRIPTS/'engineering/test_pst_model.py'),'Stale engineering tests')
    data=json.loads((OUT/'local_audit/Dover_P34_input_receipt.json').read_text())
    require(data['post_full_service_existing_common_hours']==287
        and not data['direction']['historical_2025_sign_effective_date_verified']
        and not data['units']['fresh_MW_unit_header_proof'],'Source qualification/count changed')
    replay=json.loads((OUT/'replay/replay_receipt.json').read_text())
    require(replay['preferred_scenario']=='bounded_x_nominal' and replay['fixed_annual_cohort']==8651
        and replay['post_cutover_source_hours']==287 and replay['new_source_cohort_loss']==0
        and not replay['internal_interface_observations_read']
        and replay['exact_tracking_is_diagnostic_only'],'Replay scope changed')
    preferred=[s for s in replay['scenarios'] if s['scenario']=='bounded_x_nominal']
    require(len(preferred)==1 and preferred[0]['phase_bound_active_hours']==49
        and preferred[0]['neutral_fallback_hours']==18
        and preferred[0]['maximum_abs_unscaled_angle_proxy_deg']<=40+1e-8,'Bounded controller policy changed')
    observed=json.loads((OUT/'comparison/scoring_receipt.json').read_text())
    require(observed['total_rows']==784 and observed['internal_observations_posthoc_only'],'Scoring scope changed')
    matlab=json.loads((OUT/'validation/matlab_validation.json').read_text())
    require(matlab['fresh_slim148_DC_solves']==49 and matlab['fresh_full192_DC_solves']==49
        and matlab['pre_cutover_exact_parent_identity_checks']==24
        and not matlab['full_system_AC_or_factory_impedance_or_hardware_taps_certified'],'MATLAB qualification changed')
    links=re.findall(r'\[[^\]]+\]\(([^)]+)\)',REPORT.read_text(encoding='utf-8'))
    local=[p for p in links if not p.startswith(('https://','http://','#'))]
    for link in local:
        p=ROOT/unquote(link.split('#')[0])
        if p==MANIFEST and not verify:continue
        require(p.is_file(),'Missing report link: '+link)
    content={p.relative_to(ROOT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in files()}
    if verify:
        previous=json.loads(MANIFEST.read_text())
        require(previous['files']==content,'Delivery files changed after sealing')
    else:
        dump(MANIFEST,dict(status='applied_Dover_line_and_parallel_PAR_engineering_model_with_bounded_conditional_controls',
            preferred_scenario='bounded_x_nominal',all_original_buses_and_source_circuits_preserved=True,
            old_artifacts_preserved=True,retained_buses=148,post_cutover_full_buses=192,
            paired_hours=8651,Dover_applied_hours=287,ambiguous_mode_hours=18,phase_bound_active_hours=49,
            internal_interface_fitting=False,factory_parameters_or_actual_hardware_state_certified=False,
            raw_P34_numeric_unit_and_historical_sign_date_qualifications_retained=True,
            source_proof_hash_checks=checked,report_local_links_checked=len(local),files=content))
    print(json.dumps(dict(passed=True,verify=verify,files=len(content),bytes=sum(v['bytes'] for v in content.values()),
        proof_hash_checks=checked,local_links=len(local),paired_hours=8651,applied_hours=287),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true')
    main(parser.parse_args().verify)
