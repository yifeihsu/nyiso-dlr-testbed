function read_compiled_metadata()
% Read-only compiled model inspection; no setup helper or power-flow call.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
new=load(fullfile(root,'output','nygrid_2025_physical_repair','model','latest_model.mat'),'model');
old=load(fullfile(root,'output','nygrid_2025_physical_repair','annual','baseline_bundle','model','latest_model.mat'),'model');
p=jsondecode(fileread(fullfile(root,'output','nygrid_2025_physical_repair','physics','parent41_parameters.json')));
reg=new.model.thermal.branch_registry;r=reg(reg.branch_row==41,:);assert(height(r)==1);
assert(strcmp(string(r.parameter_basis),p.thermal_registry_parameter_basis));
assert(abs(r.original_r_pu-p.repaired_R_X_B(1))<1e-12&&abs(r.original_x_pu-p.repaired_R_X_B(2))<1e-12);
assert(r.length_min_m==5&&r.length_max_m==250000);
rows=struct([]);
for state=1:4
    m=new.model.templates{state};b=old.model.templates{state};sec=m.userdata.ac_sections;
    assert(max(abs(m.branch(41,3:5)-p.repaired_R_X_B(:)'))<1e-12);
    assert(isequal(m.gen,b.gen)&&isequal(m.dcline,b.dcline));
    assert(isequal(m.bus(:,[1:5 7:end]),b.bus(:,[1:5 7:end])));
    assert(numel(sec.reactor_BS_delta_all_buses)==size(m.bus,1)&&isequal(sec.reactor_BS_bus_ids(:),m.bus(:,1)));
    assert(abs(sum(m.bus(:,6)-b.bus(:,6)))<1e-8);
    T=m.userdata.ac_system.thermal_segments;if iscell(T),T=struct2table([T{:}]);elseif isstruct(T),T=struct2table(T);end
    s=T(T.branch_row==41,:);assert(height(s)==1);
    assert(s.circuits==4&&s.bundle_count==1&&s.reference_temperature_c==95&&s.temperature_max_c==95);
    assert(strcmp(string(s.catalog_id),p.selected_candidate.catalog_id));
    assert(abs(s.segment_length_m-p.selected_candidate.length_m)<1e-8&&abs(s.reference_b_pu-p.repaired_R_X_B(3))<1e-12);
    assert(isequaln(sec.terminal_current_limit_A,b.userdata.ac_sections.terminal_current_limit_A));
    assert(all(sec.terminal_current_limit_A(41,:)==2000));
    reactors=sec.reactor_ledger(ismember([sec.reactor_ledger.original_branch_row],[185 195]));assert(numel(reactors)==2);
    for j=1:2
        rr=reactors(j);assert(rr.fraction==.75&&~rr.asbuilt_equipment_claim&&rr.intermediate_compensation_is_synthetic);
        assert(abs(sum(rr.distributed_bus_BS_delta_mvar)+rr.applied_total_reactor_mvar_at1pu)<1e-8);
    end
    rows=[rows;struct('state_index',state,'full_bus_count',size(m.bus,1),'full_branch_count',size(m.branch,1), ...
        'parent41_thermal',table2struct(s),'reactor_metadata',reactors, ...
        'generator_controls_and_transfers_preserved',true,'full_axis_BS_metadata_present',true, ...
        'aggregate_hardware_current_A',sec.terminal_current_limit_A(41,:))]; %#ok<AGROW>
end
receipt=struct('passed',true,'scope','Read-only compiled static model registry, thermal metadata, shunt ledger and source control comparison; no PF.', ...
    'parent41_registry',table2struct(r),'state_checks',rows,'source_profiles_byte_validation_separate',true);
out=fullfile(root,'output','nygrid_2025_physical_repair','independent','compiled_model_metadata_readback.json');
fid=fopen(out,'w');assert(fid>=0);fprintf(fid,'%s\n',jsonencode(receipt,'PrettyPrint',true));fclose(fid);
fprintf('COMPILED_METADATA_REVIEW_PASS states4 parent41circuits4 thermal95C hardware2000A\n');
end
