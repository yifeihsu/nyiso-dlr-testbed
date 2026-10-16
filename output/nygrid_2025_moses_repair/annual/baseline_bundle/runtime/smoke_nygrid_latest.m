function report=smoke_nygrid_latest(output_dir,matpower_root)
%SMOKE_NYGRID_LATEST Standalone current-model smoke, with no historical APIs.
% Fresh-process use is recommended. Default outputs: PACKAGE/runtime_results.
% Loads all four dated states, solves hour8508, checks independent detailed
% NR/current/loss identities and explicit-weather R/X thermal screening.
paths=nylatest_paths();if nargin<1||isempty(output_dir),output_dir=fullfile(paths.root,'runtime_results');end
if nargin<2,matpower_root='';end
if ~isfolder(output_dir),mkdir(output_dir);end
removed=base_only_path();addpath(paths.runtime);setup=setup_nygrid_latest(paths.root,matpower_root);
assert(isempty(which('fmincon'))&&isempty(which('linprog')),'nylatest:OptimizationPath','Optional Optimization Toolbox entry points remain on the path.');
profile clear;profile on;
names=strings(0,1);passed=false(0,1);values=zeros(0,1);states=struct([]);
data=nylatest_data();
record('complete8760UTCaxis_and8651source_mask',numel(data.axis.hour_index)==8760&&nnz(data.axis.source_qualified)==8651 ...
    &&numel(unique(string(data.axis.timestamp_utc)))==8760&&height(data.generator_registry)==1464,0);
for hour=[523 3360 4000 8508]
    [m,info]=load_nygrid_latest(hour);s=double(data.axis.state_index(hour));
    record("current_dated_loader_h"+string(hour),size(m.bus,1)==size(data.templates{s}.bus,1) ...
        &&size(m.branch,1)==size(data.templates{s}.branch,1)&&size(m.gen,1)==1464&&size(m.dcline,1)==6 ...
        &&~isfield(m.userdata,'source_dc')&&~info.historical_loader_chain_used,0);
    c=nylatest_compact_build(m);
    record("exact148bus_reduction_h"+string(hour),numel(c.retained_bus_ids)==148 ...
        &&isempty(c.promoted_bus_ids)&&c.validation.passed,c.validation.relative_full_lift_identity_error);
    state=struct('hour_index',hour,'state_index',s,'full_buses',size(m.bus,1),'full_branch_rows',size(m.branch,1), ...
        'active_branch_rows',nnz(m.branch(:,11)>0),'generator_rows',size(m.gen,1),'retained_buses',148);
    states=[states state]; %#ok<AGROW>
end
[compact,audit,full,allocation]=run_nygrid_latest_acpf(8508);
record('current_coupled_PF_equation_and_loss_gates',compact.success&&audit.PF_converged&&audit.AC_equation_gate ...
    &&audit.loss_allocation_gate&&audit.reduction_and_equation_gate,0);
probe=allocation.final_input;probe.bus(:,8:9)=full.bus(:,8:9);pq=find(probe.bus(:,2)==1);nonref=find(probe.bus(:,2)~=3);
probe.bus(pq,8)=probe.bus(pq,8).*(1+1e-4*sin((1:numel(pq))'));
probe.bus(nonref,9)=probe.bus(nonref,9)+.001*cos((1:numel(nonref))');
opt=mpoption('model','AC','verbose',0,'out.all',0,'pf.alg','NR','pf.tol',1e-10,'pf.nr.max_it',50, ...
    'pf.enforce_q_lims',0,'exp.use_legacy_core',1);
[independent,success]=runpf(probe,opt);v1=complex_voltage(full);v2=complex_voltage(independent);voltage_error=max(abs(v1-v2));
record('independent_detailed_NR_voltage_identity',success&&voltage_error<1e-7,voltage_error);
a=nylatest_audit_ac_solution(allocation.final_input,independent);kcl=max(a.max_nodal_P_residual_mw,a.max_nodal_Q_residual_mvar);
record('independent_detailed_NR_KCL',kcl<1e-5,kcl);
w=table(25,.6096,90,1000,101325,'VariableNames',{'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'});
cached=struct('full',full,'audit',audit,'allocation',allocation);before=cached;
screen=screen_nygrid_latest_dlr(cached,w);
record('current_RX_thermal_scope_and_identities',screen.candidate_parent_count==180&&screen.candidate_runtime_branch_count==252 ...
    &&screen.candidate_segment_count==253&&screen.numerical_identities_passed,screen.maximum_Joule_loss_identity_error_MW);
record('screen_preserves_electrical_case_and_qualification_flags',isequaln(before,cached) ...
    &&~screen.electrical_solution_changed&&~screen.OPF_run&&~screen.installed_asset_DLR_qualification ...
    &&~screen.whole_system_operating_qualification,0);
excluded=find(~data.axis.source_qualified,1);
reject('source_excluded_hour_rejected',@()load_nygrid_latest(excluded),'nylatest:UnqualifiedHour');
reject('invalid_hour_rejected',@()load_nygrid_latest(0),'nylatest:Hour');
reject('unsupported_loss_mode_rejected',@()run_nygrid_latest_acpf(8508,struct('loss_mode','unsupported')),'nylatest:LossPolicy');
reject('weather_required',@()screen_nygrid_latest_dlr(cached,[]),'rxThermal:ExplicitWeather');
profile off;prof=profile('info');[in_memory,~]=inmem('-completenames');
executed=unique([string({prof.FunctionTable.FileName})';string(in_memory(:))]);executed(executed=="")=[];
closure=struct('path',{},'scope',{},'sha256',{});outside=strings(0,1);
for k=1:numel(executed)
    item=char(executed(k));if ~isfile(item),continue;end
    absolute=char(java.io.File(item).getCanonicalPath());scope='unapproved_external';
    if startsWith(absolute,[setup.matpower_root filesep],'IgnoreCase',true),scope='selected_vendor';
    elseif startsWith(absolute,[paths.runtime filesep],'IgnoreCase',true),scope='current_runtime';
    elseif startsWith(absolute,[matlabroot filesep],'IgnoreCase',true),scope='MATLAB_distribution';
    else,outside(end+1)=string(absolute);end %#ok<AGROW>
    closure(end+1)=struct('path',absolute,'scope',scope,'sha256',nylatest_file_sha256(absolute)); %#ok<AGROW>
end
record('executed_code_is_only_current_runtime_vendor_and_MATLAB',isempty(outside),numel(outside));
search=strsplit(path,pathsep);badpaths=strings(0,1);
for k=1:numel(search)
    item=char(java.io.File(search{k}).getCanonicalPath());
    if ~strcmpi(item,paths.runtime)&&~startsWith(item,[paths.runtime filesep],'IgnoreCase',true) ...
        &&~strcmpi(item,setup.matpower_root)&&~startsWith(item,[setup.matpower_root filesep],'IgnoreCase',true) ...
        &&~strcmpi(item,matlabroot)&&~startsWith(item,[matlabroot filesep],'IgnoreCase',true)
        badpaths(end+1)=string(item); %#ok<AGROW>
    end
end
record('search_path_has_no_historical_or_unapproved_project_folder',isempty(badpaths),numel(badpaths));
tests=table(names,passed,values,'VariableNames',{'test','passed','reported_value'});
report=struct('passed',all(passed),'test_count',numel(passed),'setup',setup,'loaded_states',states,'PF_hours',8508, ...
    'source_excluded_test_hour',excluded,'independent_detailed_voltage_error_pu',voltage_error,'independent_KCL_error_MW_MVAr',kcl, ...
    'thermal_candidate_parent_count',screen.candidate_parent_count,'thermal_candidate_segment_count',screen.candidate_segment_count, ...
    'maximum_Joule_identity_error_MW',screen.maximum_Joule_loss_identity_error_MW, ...
    'maximum_terminal_current_identity_error_A',screen.maximum_terminal_current_crosscheck_error_A, ...
    'maximum_series_utilization',screen.maximum_series_ampacity_utilization,'VQ_operating_gate',audit.VQ_and_generator_assumption_gate, ...
    'removed_external_and_optional_optimization_paths',{removed},'license_features_in_use',license('inuse'), ...
    'unapproved_executed_files',outside,'unapproved_search_paths',badpaths,'complete_search_path',{search}, ...
    'historical_model_API_called',false,'annual_PF_replay_run',false,'OPF_run',false, ...
    'installed_asset_DLR_qualification',false,'whole_system_operating_qualification',false,'tests',table2struct(tests));
writetable(tests,fullfile(output_dir,'smoke_tests.csv'));writetable(struct2table(closure),fullfile(output_dir,'loaded_function_dependencies.csv'));
writetable(screen.candidate_and_exclusion_ledger,fullfile(output_dir,'thermal_candidate_and_exclusion_ledger.csv'));
writetable(screen.branch_screen,fullfile(output_dir,'thermal_branch_screen.csv'));
witness=struct('hour_index',8508,'baseMVA',full.baseMVA,'input_bus',allocation.final_input.bus, ...
    'input_gen',allocation.final_input.gen,'input_branch',allocation.final_input.branch,'input_dcline',allocation.final_input.dcline, ...
    'solved_bus',full.bus,'solved_gen',full.gen,'solved_branch',full.branch,'solved_dcline',full.dcline, ...
    'retained_bus_ids',compact.retained_bus_ids,'recovered_line_current_A',compact.recovered_line_current_A,'actual_loss_budget_MW',allocation.actual_budget_MW);
save(fullfile(output_dir,'compact_numerical_witness.mat'),'witness','-v7');
fid=fopen(fullfile(output_dir,'smoke_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
disp(tests);fprintf('LATEST_SMOKE pass%d tests%d\n',report.passed,report.test_count);
assert(report.passed,'nylatest:Smoke','One or more current package smoke checks failed.');
    function record(name,ok,value)
        names(end+1,1)=string(name);passed(end+1,1)=logical(ok);values(end+1,1)=value;
        fprintf('LATEST_SMOKE_CHECK %s pass%d value%.12g\n',name,ok,value);
    end
    function reject(name,fn,id)
        yes=false;try,fn();catch ex,yes=strcmp(ex.identifier,id);if ~yes,fprintf('UNEXPECTED %s %s\n',ex.identifier,ex.message);end,end
        record(name,yes,0);
    end
end

function V=complex_voltage(m),V=m.bus(:,8).*exp(1j*deg2rad(m.bus(:,9)));end

function removed=base_only_path()
restoredefaultpath;parts=strsplit(path,pathsep);removed={};
for k=1:numel(parts)
    normalized=lower(strrep(parts{k},'\','/'));
    if ~startsWith(parts{k},[matlabroot filesep],'IgnoreCase',true)||contains(normalized,'/toolbox/optim')||contains(normalized,'/toolbox/shared/optim')
        removed{end+1}=parts{k};rmpath(parts{k}); %#ok<AGROW>
    end
end
end
