function report=validate_latest_runtime(matpower_root)
%VALIDATE_LATEST_RUNTIME Compare compiled current runtime to source behavior.
% Authoring-only. Four selected PF points, never a full annual PF replay.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
out=fullfile(root,'output','nygrid_2025_latest_handoff','validation');if ~isfolder(out),mkdir(out);end
addpath(fullfile(root,'scripts','nygrid_2025_dlr_handoff','runtime'));
setup_nygrid_2025_handoff(root,matpower_root);
addpath(fullfile(root,'scripts','nygrid_2025_conductor_inference'));
runtime=fullfile(root,'scripts','nygrid_2025_latest_handoff','runtime');addpath(runtime);
setup=setup_nygrid_latest(root,matpower_root);
[data,model_receipt]=nylatest_data();source_before=source_records(root);
names=strings(0,1);passed=false(0,1);values=zeros(0,1);points=struct([]);
independent_file=fullfile(root,'output','nygrid_2025_latest_handoff','independent','current_data_review.json');
independent=jsondecode(fileread(independent_file));assert(independent.passed);
record('independent_full_annual_array_and_four_template_data_review_passed',independent.passed,0);
weather=table(25,.6096,90,1000,101325,'VariableNames',{'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'});
for hour=[523 3360 4000 8508]
    old=ac_loss_prepare_case(npcc_nygrid_2025_ac(hour),'released_equivalent');fresh=load_nygrid_latest(hour);
    arrays={'bus','gen','branch','dcline','gencost'};exact=true;
    for k=1:numel(arrays),name=arrays{k};exact=exact&&isequaln(old.(name),fresh.(name));end
    record("exact_current_loader_numeric_arrays_h"+string(hour),exact,0);
    metadata=isequal(string(old.bus_name),string(fresh.bus_name))&&isequal(string(old.genfuel),string(fresh.genfuel)) ...
        &&isequaln(old.userdata.ac_sections.branch_map,fresh.userdata.ac_sections.branch_map) ...
        &&isequaln(old.userdata.ac_sections.reactor_ledger,fresh.userdata.ac_sections.reactor_ledger);
    for name={'branch_keys','branch_parent_row','external_generator_mask','generator_p_reference','generator_q_cap', ...
            'generator_assumed_s_cap','thermal_segments','cable_segments','terminal_current_limits','cable_section_static_current_limits'}
        metadata=metadata&&isequaln(old.userdata.ac_system.(name{1}),fresh.userdata.ac_system.(name{1}));
    end
    record("exact_current_control_and_thermal_metadata_h"+string(hour),metadata,0);
    oldpolicy=ac_loss_prepare_policy(old);newpolicy=nylatest_prepare_policy(fresh);fields=fieldnames(oldpolicy);exact=true;
    for k=1:numel(fields),name=fields{k};exact=exact&&isfield(newpolicy,name)&&isequaln(oldpolicy.(name),newpolicy.(name));end
    record("exact_loss_policy_contract_h"+string(hour),exact,0);
    oldc=compact_ac_build(old);newc=nylatest_compact_build(fresh);
    reduction=max([max(abs(oldc.Yred-newc.Yred),[],'all'),max(abs(oldc.voltage_lift-newc.voltage_lift),[],'all'), ...
        max(abs(oldc.YseriesL-newc.YseriesL),[],'all'),max(abs(oldc.YfL-newc.YfL),[],'all'),max(abs(oldc.YtL-newc.YtL),[],'all')]);
    record("exact148bus_reduction_and_current_operators_h"+string(hour),reduction<1e-12 ...
        &&isequal(oldc.retained_bus_ids,newc.retained_bus_ids)&&numel(newc.retained_bus_ids)==148,reduction);
    [oldresult,olda,oldfull,oldallocation]=run_nygrid_2025_loss_consistent_acpf(hour);
    [result,audit,full,allocation]=run_nygrid_latest_acpf(hour);
    gate=oldresult.success&&result.success&&olda.loss_allocation_gate&&audit.loss_allocation_gate ...
        &&olda.reduction_and_equation_gate&&audit.reduction_and_equation_gate;
    record("source_and_packaged_coupled_PF_qualified_h"+string(hour),gate,0);
    v_error=max(abs(complex_voltage(oldfull)-complex_voltage(full)));
    pq_error=max(abs(oldfull.branch(:,14:17)-full.branch(:,14:17)),[],'all');
    gen_error=max(abs(oldfull.gen(:,2:3)-full.gen(:,2:3)),[],'all');
    current_error=max(abs(oldresult.recovered_line_current_A-result.recovered_line_current_A),[],'all');
    budget_error=max(abs(oldallocation.actual_budget_MW-allocation.actual_budget_MW));
    record("same_PF_voltage_generator_branch_and_loss_result_h"+string(hour),gate&&v_error<1e-9 ...
        &&pq_error<1e-6&&gen_error<1e-6&&budget_error<1e-6,max([v_error,pq_error,gen_error,budget_error]));
    record("same_recovered_physical_branch_currents_h"+string(hour),current_error<1e-6,current_error);
    newcache=struct('full',full,'audit',audit,'allocation',allocation);
    oldscreen=screen_nygrid_2025_rx_thermal(struct('full',oldfull,'audit',olda,'allocation',oldallocation),weather);
    screen=screen_nygrid_latest_dlr(newcache,weather);
    screen_error=max(abs(oldscreen.branch_screen.series_phase_current_A-screen.branch_screen.series_phase_current_A));
    limits_error=max(abs(oldscreen.branch_screen.declared_phase_ampacity_A-screen.branch_screen.declared_phase_ampacity_A));
    record("same_RX_admission_and_thermal_current_limits_h"+string(hour), ...
        isequaln(oldscreen.candidate_and_exclusion_ledger,screen.candidate_and_exclusion_ledger) ...
        &&isequaln(oldscreen.candidate_segments,screen.candidate_segments)&&screen_error<1e-6&&limits_error<1e-9,max(screen_error,limits_error));
    record("same_unqualified_operating_flags_h"+string(hour),audit.VQ_and_generator_assumption_gate==olda.VQ_and_generator_assumption_gate ...
        &&~screen.whole_system_operating_qualification&&~screen.installed_asset_DLR_qualification,0);
    point=struct('hour_index',hour,'state_index',double(data.axis.state_index(hour)), ...
        'loader_arrays_exact',exact,'voltage_error_pu',v_error,'branch_PQ_error_MVA',pq_error, ...
        'generator_PQ_error_MVA',gen_error,'recovered_current_error_A',current_error,'loss_budget_error_MW',budget_error, ...
        'candidate_parent_count',screen.candidate_parent_count,'candidate_runtime_branch_count',screen.candidate_runtime_branch_count, ...
        'candidate_segment_count',screen.candidate_segment_count,'max_Joule_identity_error_MW',screen.maximum_Joule_loss_identity_error_MW, ...
        'maximum_series_utilization',screen.maximum_series_ampacity_utilization,'VQ_operating_gate',audit.VQ_and_generator_assumption_gate);
    points=[points point]; %#ok<AGROW>
    prefix=sprintf('hour_%04d',hour);
    writetable(screen.candidate_and_exclusion_ledger,fullfile(out,[prefix '_thermal_ledger.csv']));
    witness=struct('hour_index',hour,'baseMVA',fresh.baseMVA,'input_bus',fresh.bus,'input_gen',fresh.gen, ...
        'input_branch',fresh.branch,'input_dcline',fresh.dcline,'input_gencost',fresh.gencost, ...
        'solved_bus',full.bus,'solved_gen',full.gen,'solved_branch',full.branch,'solved_dcline',full.dcline, ...
        'retained_bus_ids',result.retained_bus_ids,'recovered_line_current_A',result.recovered_line_current_A, ...
        'loss_budget_MW',allocation.actual_budget_MW,'comparison',point);
    save(fullfile(out,[prefix '_compact_witness.mat']),'witness','-v7');
end
reject('zero_hour_rejected',@()load_nygrid_latest(0),'nylatest:Hour');
reject('out_of_range_hour_rejected',@()load_nygrid_latest(8761),'nylatest:Hour');
reject('fractional_hour_rejected',@()load_nygrid_latest(1.5),'nylatest:Hour');
reject('NaN_hour_rejected',@()load_nygrid_latest(NaN),'nylatest:Hour');
excluded=find(~data.axis.source_qualified,1);reject('source_excluded_hour_rejected',@()load_nygrid_latest(excluded),'nylatest:UnqualifiedHour');
reject('unsupported_policy_rejected',@()run_nygrid_latest_acpf(8508,struct('loss_mode','unsupported')),'nylatest:LossPolicy');
reject('unsupported_impedance_rejected',@()run_nygrid_latest_acpf(8508,struct('impedance_mode','unsupported')),'nylatest:Impedance');
reject('weather_required',@()screen_nygrid_latest_dlr(newcache,[]),'rxThermal:ExplicitWeather');
bad=newcache;bad.audit.loss_allocation_gate=false;
reject('failed_PF_cannot_be_thermally_screened',@()screen_nygrid_latest_dlr(bad,weather),'rxThermal:UnqualifiedPF');
source_after=source_records(root);record('source_and_compiled_files_unchanged_during_validation',isequaln(source_before,source_after),0);
tests=table(names,passed,values,'VariableNames',{'test','passed','reported_value'});writetable(tests,fullfile(out,'runtime_tests.csv'));
report=struct('passed',all(passed),'test_count',numel(passed),'scope','Four source-versus-current-package loader/PF/current/thermal comparisons and negative guards', ...
    'setup',setup,'model_files',model_receipt.model_files,'points',points,'source_excluded_test_hour',excluded, ...
    'annual_data_review',struct('path','output/nygrid_2025_latest_handoff/independent/current_data_review.json', ...
        'sha256',nylatest_file_sha256(independent_file),'passed',true), ...
    'source_and_runtime_files',source_after,'tests',table2struct(tests),'weather',table2struct(weather), ...
    'full_annual_PF_replay_run',false,'OPF_run',false,'numerical_equations_changed',false, ...
    'installed_asset_DLR_qualification',false,'whole_system_operating_qualification',false);
write_json(fullfile(out,'runtime_validation_receipt.json'),report);
copy=jsondecode(fileread(fullfile(root,'output','nygrid_2025_latest_handoff','build','kernel_copy_receipt.json')));
copy.static_policy_compilation_equivalent_at_all_four_states=all(passed(contains(names,'exact_loss_policy_contract')));
copy.runtime_comparison_passed=report.passed;
copy.runtime_validation_sha256=nylatest_file_sha256(fullfile(out,'runtime_validation_receipt.json'));
copy.policy_adaptation=struct('source','scripts/nygrid_2025_ac_loss_revision/core/ac_loss_prepare_policy.m', ...
    'source_sha256',nylatest_file_sha256(fullfile(root,'scripts','nygrid_2025_ac_loss_revision','core','ac_loss_prepare_policy.m')), ...
    'target','scripts/nygrid_2025_latest_handoff/runtime/kernels/nylatest_prepare_policy.m', ...
    'target_sha256',nylatest_file_sha256(fullfile(runtime,'kernels','nylatest_prepare_policy.m')), ...
    'description','Frozen ownership, membership, shares and finite external bounds compiled once; original hourly load/generation/reference algebra preserved.');
write_json(fullfile(out,'kernel_adaptation_receipt.json'),copy);
disp(tests);fprintf('LATEST_RUNTIME_VALIDATION pass%d tests%d\n',report.passed,report.test_count);
assert(report.passed,'nylatest:Validation','A current source/package comparison or guard failed.');
    function record(name,ok,value)
        value=builtin('full',value);ok=builtin('full',logical(ok));
        names(end+1,1)=string(name);passed(end+1,1)=logical(ok);values(end+1,1)=value;
        fprintf('LATEST_COMPARE %s pass%d value%.12g\n',name,ok,value);
    end
    function reject(name,fn,id)
        yes=false;try,fn();catch ex,yes=strcmp(ex.identifier,id);if ~yes,fprintf('UNEXPECTED %s %s\n',ex.identifier,ex.message);end,end
        record(name,yes,0);
    end
end

function V=complex_voltage(m),V=m.bus(:,8).*exp(1j*deg2rad(m.bus(:,9)));end

function records=source_records(root)
code=jsondecode(fileread(fullfile(root,'output','nygrid_2025_latest_handoff','build','kernel_copy_receipt.json')));
paths=[string({code.records.source})';string({code.records.target})'];
old=jsondecode(fileread(fullfile(root,'output','nygrid_2025_dlr_handoff','runtime_data_closure.json')));
paths=[paths;string({old.entries.path})';"scripts/nygrid_2025_ac_loss_revision/core/ac_loss_prepare_case.m"; ...
    "scripts/nygrid_2025_ac_loss_revision/core/ac_loss_prepare_policy.m"; ...
    "scripts/nygrid_2025_acpf_profile_audit/acpf/load_profile_cache.m";"scripts/nygrid_2025_acpf_profile_audit/acpf/profile_case_from_cache.m"];
files=dir(fullfile(root,'scripts','nygrid_2025_latest_handoff','runtime','**','*.m'));
for k=1:numel(files),paths(end+1)=string(strrep(fullfile(files(k).folder,files(k).name),[root filesep],''));end %#ok<AGROW>
model=jsondecode(fileread(fullfile(root,'output','nygrid_2025_latest_handoff','model','model_receipt.json')));
for k=1:numel(model.model_files),paths(end+1)="output/nygrid_2025_latest_handoff/model/"+string(model.model_files(k).name);end %#ok<AGROW>
paths=unique(strrep(paths,'\','/'));records=struct('path',{},'sha256',{});
for k=1:numel(paths),records(end+1)=struct('path',char(paths(k)),'sha256',nylatest_file_sha256(fullfile(root,paths(k))));end %#ok<AGROW>
end

function write_json(path,value)
fid=fopen(path,'w');assert(fid>=0);clean=onCleanup(@()fclose(fid));fprintf(fid,'%s\n',jsonencode(value,'PrettyPrint',true));
end
