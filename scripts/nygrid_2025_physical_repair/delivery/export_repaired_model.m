function receipt=export_repaired_model()
% Compile only the frozen physical repair into the four released templates.
% Both annual profile shards are copied byte-for-byte from the prior bundle.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
out=fullfile(root,'output','nygrid_2025_physical_repair','model');
source=fullfile(root,'output','nygrid_2025_latest_handoff','model');
oldruntime=fullfile(root,'scripts','nygrid_2025_latest_handoff','runtime');addpath(oldruntime);
setup_nygrid_latest(root,'C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower');
addpath(fullfile(root,'scripts','nygrid_2025_physical_repair','core'));
candidate_path=fullfile(root,'output','nygrid_2025_physical_repair','candidate_receipt.json');
assert(isfile(candidate_path),'nyrepair:Unfrozen','Freeze the physical candidate first.');
candidate=jsondecode(fileread(candidate_path));assert(candidate.passed);
assert(~isfile(fullfile(out,'latest_model.mat')),'nyrepair:PreserveModel','A repaired model export already exists; preserve it.');
prior=jsondecode(fileread(fullfile(source,'model_receipt.json')));assert(prior.passed);
for j=1:numel(prior.model_files)
    rec=prior.model_files(j);assert(strcmp(nylatest_file_sha256(fullfile(source,rec.name)),rec.sha256));
end
loaded=load(fullfile(source,'latest_model.mat'),'model');model=loaded.model;original=model;
changes=cell(4,1);
for j=1:4
    before=load_nygrid_latest(double(model.axis.template_hours(j)));[after,changes{j}]=nyrepair_apply_case(before);
    assert(isequal(before.bus(:,1),after.bus(:,1))&&isequal(before.branch(:,1:2),after.branch(:,1:2)));
    assert(isequaln(before.gen,after.gen)&&isequaln(before.gencost,after.gencost)&&isequaln(before.dcline,after.dcline));
    assert(isequal(before.bus(:,3:4),after.bus(:,3:4))&&isequal(before.bus(:,12:13),after.bus(:,12:13)));
    after.userdata=rmfield(after.userdata,'latest_runtime');
    if isfield(after,'userfcn'),after=rmfield(after,'userfcn');end
    assert(isfield(after.userdata,'physical_repair')&&isfield(after.userdata,'physical_repair_185195'));
    assert(isfield(after.userdata.ac_sections,'reactor_BS_delta_all_buses') ...
        &&isequal(after.userdata.ac_sections.reactor_BS_bus_ids,after.bus(:,1)));
    model.templates{j}=after;
end
model.model_id='NYGRID_2025_physical_repair_loss_consistent_RX_thermal';
model.created_utc=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd HH:mm:ss Z'));
model.baseline_source_model_commit=original.source_model_commit;
p41=jsondecode(fileread(fullfile(root,'output','nygrid_2025_physical_repair','physics','parent41_parameters.json')));
reg=model.thermal.branch_registry;row=find(reg.branch_row==41);assert(isscalar(row));
reg.parameter_basis(row)=string(p41.thermal_registry_parameter_basis);
reg.length_min_m(row)=p41.thermal_registry_length_min_m;reg.length_max_m(row)=p41.thermal_registry_length_max_m;
model.thermal.branch_registry=reg;
model.physical_repair=struct('schema_version',1,'candidate_receipt',candidate, ...
    'candidate_receipt_sha256',nylatest_file_sha256(candidate_path),'template_changes',{changes}, ...
    'baseline_static_model_sha256',prior.model_file.sha256,'profile_shards_byte_identical',true);
model.policy.R_X_B_and_control_policies_changed=true;
model.policy.physical_repair_scope='Parent41 coherent RXB and thermal metadata; parent185/195 section-local fixed 75pct reactors';
assert(isequaln(model.axis,original.axis)&&isequaln(model.loss_static,original.loss_static) ...
    &&isequaln(model.external,original.external)&&isequaln(model.generator_bus_ids,original.generator_bus_ids) ...
    &&isequaln(model.retained_bus_ids,original.retained_bus_ids)&&isequaln(model.profile_shards,original.profile_shards));
if ~isfolder(out),mkdir(out);end
for j=1:2
    rec=model.profile_shards(j);dest=fullfile(out,rec.name);
    if ~isfile(dest),copyfile(fullfile(source,rec.name),dest);end
    assert(strcmp(nylatest_file_sha256(dest),rec.sha256));
end
file=fullfile(out,'latest_model.mat');save(file,'model','-v7');fi=dir(file);
receipt=prior;receipt.model_file=struct('name','latest_model.mat','bytes',fi.bytes,'sha256',nylatest_file_sha256(file));
receipt.model_files(1)=receipt.model_file;receipt.physical_arrays_changed=true;
receipt.physical_repair=model.physical_repair;receipt.baseline_model_receipt_sha256=nylatest_file_sha256(fullfile(source,'model_receipt.json'));
receipt.baseline_source_model_commit=original.source_model_commit;
receipt.source_model_commit_role='Baseline source model; physical-repair implementation and parameters are bound by the candidate receipt hash';
receipt.created_utc=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd HH:mm:ss Z'));
receipt.all_annual_profile_arrays_copied_without_numeric_conversion=true;receipt.profile_shards_byte_identical_to_baseline=true;
receipt.fresh_PF_solve_run=false;receipt.annual_replay_run=false;receipt.OPF_run=false;
fid=fopen(fullfile(out,'model_receipt.json'),'w');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));fprintf(fid,'%s\n',jsonencode(receipt,'PrettyPrint',true));
fprintf('PHYSICAL_MODEL_EXPORTED staticbytes%d profilebytes%d\n',fi.bytes,sum([model.profile_shards.bytes]));
end
