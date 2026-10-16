function check_export_schema()
% One already validated frozen-candidate hour exercises the annual API contract.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
annual=fullfile(root,'output','nygrid_2025_physical_repair','annual');bundle=fullfile(annual,'baseline_bundle');
addpath(fullfile(bundle,'runtime'));setup_nygrid_latest(bundle,'C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower');
addpath(fullfile(root,'scripts','nygrid_2025_physical_repair','core'));
proof=jsondecode(fileread(fullfile(root,'output','nygrid_2025_physical_repair','candidate_receipt.json')));assert(proof.passed);
m=nyrepair_apply_case(load_nygrid_latest(349));[c,a,r,allocation]=nylatest_coupled_solve(m);
a.HQ_PG_change_from_original_MW=r.gen(allocation.policy_contract.HQ,2)-m.gen(allocation.policy_contract.HQ,2);a.full_operating_gate=a.passed;
% Parse the producer's declared audit fields rather than maintain a second list.
code=fileread(fullfile(root,'scripts','nygrid_2025_physical_repair','annual','run_nyrepair_annual.m'));
for name={'flags','scalars'}
    declaration=regexp(code,[name{1},'=\{(.*?)\};'],'tokens','once');assert(~isempty(declaration));
    keys=regexp(declaration{1},'''([^'']+)''','tokens');
    for k=1:numel(keys),key=keys{k}{1};assert(isfield(a,key)&&isscalar(a.(key)),'nyrepair:Schema','Annual audit field missing or nonscalar: %s',key);end
end
assert(a.PF_converged&&a.AC_equation_gate&&a.loss_allocation_gate&&a.reduction_and_equation_gate);
assert(isequal(size(r.gen(:,2:3)),[1464,2])&&isequal(size(c.recovered_line_current_A),[size(r.branch,1),3]));
assert(numel(c.retained_bus_ids)==148&&numel(allocation.actual_budget_MW)==14&&numel(allocation.NY_gross_target_MW)==11);
assert(all(isfinite(r.gen(:,2:3)),'all')&&all(isfinite(c.recovered_line_current_A),'all'));
issues=checkcode(fullfile(root,'scripts','nygrid_2025_physical_repair','annual','run_nyrepair_annual.m'),'-id');assert(isempty(issues));
out=struct('passed',true,'hour_index',349,'candidate_sha256',nylatest_file_sha256(fullfile(root,'output','nygrid_2025_physical_repair','candidate_receipt.json')), ...
    'all_declared_audit_fields_exist_and_scalar',true,'generator_and_current_array_shapes_checked',true, ...
    'baseline_snapshot_used',true,'solver_schema_errors_are_fatal_in_annual',true,'annual_started',false);
fid=fopen(fullfile(annual,'export_schema_preflight.json'),'w');fprintf(fid,'%s\n',jsonencode(out,'PrettyPrint',true));fclose(fid);
disp('PHYSICAL_REPAIR_ANNUAL_EXPORT_SCHEMA_PASS');
end
