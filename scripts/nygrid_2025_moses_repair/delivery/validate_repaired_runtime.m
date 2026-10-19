function report=validate_repaired_runtime()
% Bind source preflight, full annual replay, and fresh runtime-only smoke.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
base=fullfile(root,'output','nygrid_2025_moses_repair');
out=fullfile(base,'delivery','validation');
pre=jsondecode(fileread(fullfile(base,'validation','candidate_readiness.json')));
annual=jsondecode(fileread(fullfile(base,'annual','moses_repair_v1','annual_receipt.json')));
model=jsondecode(fileread(fullfile(base,'model','model_receipt.json')));
smoke=jsondecode(fileread(fullfile(out,'cold_smoke','smoke_receipt.json')));
assert(pre.passed&&pre.all_four_states&&pre.fixed_PQ_contract_passed);
assert(annual.completed&&annual.months_complete==12&&annual.attempted_hours==8651);
assert(annual.policy_equation_qualified_hours==8651&&annual.solver_exceptions==0);
assert(smoke.passed&&smoke.test_count==20);
assert(strcmp(smoke.setup.model_sha256,model.model_file.sha256));
assert(strcmp(pre.setup.model_sha256,model.model_file.sha256));
report=struct('passed',true,'scope','Compiled Moses model source preflight, full annual replay, and fresh runtime smoke', ...
    'model_sha256',model.model_file.sha256,'source_mask_preserved',true,'source_qualified_hours',8651, ...
    'generator_rows',1466,'profile_shards_byte_identical_to_baseline',false, ...
    'source_preflight',pre,'annual_qualified_hours',annual.policy_equation_qualified_hours, ...
    'annual_operating_qualified_hours',annual.full_operating_qualified_hours,'fresh_smoke',smoke, ...
    'whole_system_operating_qualification_claimed',false,'portable_extraction_check','separate receipt');
fid=fopen(fullfile(out,'runtime_validation_receipt.json'),'w');assert(fid>=0);
cleanup=onCleanup(@()fclose(fid));fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));
end
