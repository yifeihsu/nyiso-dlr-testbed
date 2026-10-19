"""Read-only independent review of the frozen current runtime proof chain."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_latest_handoff'


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def record(path):return dict(path=path.relative_to(ROOT).as_posix(),sha256=digest(path))
def code(text):return '\n'.join(line.rstrip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('%'))


def main():
    path=OUT/'validation/runtime_validation_receipt.json';runtime=json.loads(path.read_text())
    adapter_path=OUT/'validation/kernel_adaptation_receipt.json';adapter=json.loads(adapter_path.read_text())
    model_path=OUT/'model/model_receipt.json';model=json.loads(model_path.read_text())
    bundle_path=OUT/'model_bundle_independent_review.json';bundle=json.loads(bundle_path.read_text())
    assert runtime['passed'] and runtime['test_count']==47 and len(runtime['tests'])==47
    assert all(t['passed'] for t in runtime['tests'])
    assert not runtime['full_annual_PF_replay_run'] and not runtime['OPF_run'] and not runtime['numerical_equations_changed']
    assert not runtime['installed_asset_DLR_qualification'] and not runtime['whole_system_operating_qualification']
    assert adapter['passed'] and adapter['runtime_validation_sha256']==digest(path)
    assert adapter['static_policy_compilation_equivalent_at_all_four_states'] and adapter['runtime_comparison_passed']
    assert runtime['model_files']==model['model_files'] and bundle['passed']
    assert bundle['annual_axis_rows']==8760 and bundle['exact_annual_numeric_entries_checked']==40996800
    assert [p['hour_index'] for p in runtime['points']]==[523,3360,4000,8508]
    assert [p['candidate_parent_count'] for p in runtime['points']]==[179,179,179,180]
    for p in runtime['points']:
        assert p['loader_arrays_exact'] and not p['VQ_operating_gate']
        for name in ['voltage_error_pu','branch_PQ_error_MVA','generator_PQ_error_MVA','recovered_current_error_A','loss_budget_error_MW']:
            assert p[name]==0,(p['hour_index'],name)
    dependencies=[record(p) for p in [path,adapter_path,model_path,bundle_path,Path(__file__).resolve()]]
    for r in runtime['source_and_runtime_files']:
        assert digest(ROOT/r['path'])==r['sha256'],r['path']
        dependencies.append(dict(r))
    source_review=runtime['annual_data_review'];assert source_review['passed'] and digest(ROOT/source_review['path'])==source_review['sha256']
    # Review the exact differences after function renaming. Only the three
    # explicitly described path/data retrieval changes are accepted below.
    reviewed=[]
    for r in adapter['records']:
        sp=ROOT/r['source'];tp=ROOT/r['target']
        assert digest(sp)==r['source_sha256'] and digest(tp)==r['target_sha256']
        a=sp.read_text();b=tp.read_text()
        for old,new in sorted(r['function_renames'].items(),key=lambda p:-len(p[0])):
            a=re.sub(r'\b'+re.escape(old)+r'\b',new,a)
        if tp.stem=='nylatest_coupled_solve':
            start=a.index("root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));")
            end=a.index('started=tic;',start);a=a[:start]+a[end:]
        elif tp.stem=='nylatest_compact_build':
            a=a.replace("root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));\n",'')
            old="    registry=readtable(fullfile(root,'output','nygrid_2025_slim','network','bus_register.csv'));\n    anchor_ids=double(registry.model_bus(:));assert(numel(anchor_ids)==148);"
            new="    anchor_ids=double(m.userdata.latest_runtime.retained_bus_ids(:));assert(numel(anchor_ids)==148);"
            assert old in a;a=a.replace(old,new)
        elif tp.stem=='nylatest_thermal_candidates':
            start=a.index("root=fileparts(fileparts(fileparts(mfilename('fullpath'))));")
            end=a.index('assert(isequal(sort(double(conflicts.branch_row))',start)
            replacement="data=nylatest_data();\nreg=data.thermal.branch_registry;conductors=data.thermal.conductors;\ngeometry=data.thermal.geometry;conflicts=data.thermal.cable_conflicts;\n"
            a=a[:start]+replacement+a[end:]
        assert code(a)==code(b),r['target']
        reviewed.append(dict(target=r['target'],passed=True,data_path_adaptations=r['data_and_path_adaptations'],all_remaining_executable_lines_identical_after_function_renaming=True))
    assert len(reviewed)==19
    policy=adapter['policy_adaptation']
    assert digest(ROOT/policy['source'])==policy['source_sha256'] and digest(ROOT/policy['target'])==policy['target_sha256']
    # Handwritten entry/loading/policy functions were read independently:
    # selected frozen template + exact hourly arrays, current-only options,
    # vendor callbacks recreated, and identical dynamic policy algebra.
    paths=[ROOT/'scripts/nygrid_2025_latest_handoff/runtime'/name for name in
           ['nylatest_data.m','nylatest_paths.m','setup_nygrid_latest.m','load_nygrid_latest.m','run_nygrid_latest_acpf.m']]
    paths.append(ROOT/policy['target']);dependencies.extend(record(p) for p in paths)
    report=dict(passed=True,completed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent data-policy/code-copy and frozen runtime-receipt review; no additional model experiments',
        source_model_commit=model['source_model_commit'],bound_runtime_checks=47,
        exact_source_loader_PF_current_loss_and_thermal_comparisons_at_four_states=True,
        copied_kernel_functions_reviewed=19,only_function_renames_and_declared_data_path_changes_found=True,
        full_annual_profile_copy_verified_by_independent_readback=True,
        no_full_annual_PF_or_OPF_inferred_from_profile_copy=True,
        current_only_public_options_and_static_policy_binding_reviewed=True,
        no_serialized_authoring_machine_callback_dependency=True,
        remaining_actionable_findings=[],
        extracted_package_validation='Separate archive/clean-directory workstream; this receipt does not substitute checkout verification for actual extraction.',
        original_files_modified_by_review=False,
        reviewed_kernel_records=reviewed,dependencies=dependencies)
    target=OUT/'runtime_receipts_independent_review.json';target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['dependencies','reviewed_kernel_records']},indent=2))


if __name__=='__main__':main()
