function report=smoke_nygrid_2025_handoff(output_dir,matpower_root)
%SMOKE_NYGRID_2025_HANDOFF Cold-path selected-hour reproducibility checks.
% Run from a fresh MATLAB process. Writes new evidence only to OUTPUT_DIR,
% default PACKAGE_ROOT/runtime_results. Does not rerun annual studies or OPF
% on the NYGRID system. The tiny synthetic MIPS fixture checks callbacks only.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
if nargin<1||isempty(output_dir),output_dir=fullfile(root,'runtime_results');end
if nargin<2,matpower_root='';end
output_dir=char(java.io.File(output_dir).getCanonicalPath());
if ~isfolder(output_dir),mkdir(output_dir);end
removed=reset_to_base_path();
addpath(fileparts(mfilename('fullpath')));
setup=setup_nygrid_2025_handoff(root,matpower_root);
assert(isempty(which('fmincon'))&&isempty(which('linprog')), ...
    'handoff:OptimizationPath','Optimization Toolbox entry points remain available.');
profile clear;profile on;
names=strings(0,1);passed=false(0,1);errors=zeros(0,1);
hour_cases=struct('hour_index',{},'buses',{},'branches',{},'generators',{},'fixed_transfers',{},'baseMVA',{});
mpopt=mpoption('verbose',0,'out.all',0,'pf.alg','NR','pf.tol',1e-10,'pf.nr.max_it',40, ...
    'pf.enforce_q_lims',0,'exp.use_legacy_core',1);
for h=[2630 3360 3576 8508]
    m=npcc_nygrid_2025_ac(h);
    hour_cases(end+1)=struct('hour_index',h,'buses',size(m.bus,1),'branches',size(m.branch,1), ...
        'generators',size(m.gen,1),'fixed_transfers',size(m.dcline,1),'baseMVA',m.baseMVA); %#ok<AGROW>
    record("dated_loader_hour_"+string(h),size(m.dcline,1)==6&&all(isfinite(m.bus),'all')&&all(isfinite(m.branch),'all'),0);
end
[legacy,success]=runpf(m,mpopt);record('legacy_detailed_PF_converges',success,0);
[compact,compact_audit,recovered]=run_nygrid_2025_compact_acpf(m,mpopt);
legacy_error=max(abs(complex_voltage(legacy)-complex_voltage(recovered)));
record('legacy_full_compact_complex_voltage_identity',legacy.success&&recovered.success&&size(compact.bus,1)==148&&legacy_error<2e-7,legacy_error);
[revised,revised_audit,full,allocation]=run_nygrid_2025_loss_consistent_acpf(m,struct());
record('revised_loss_and_equation_qualification',revised_audit.PF_converged&&revised_audit.AC_equation_gate ...
    &&revised_audit.loss_allocation_gate&&revised_audit.reduction_and_equation_gate,0);
probe=allocation.final_input;probe.bus(:,8:9)=full.bus(:,8:9);
pq=find(probe.bus(:,2)==1);nonref=find(probe.bus(:,2)~=3);
probe.bus(pq,8)=probe.bus(pq,8).*(1+1e-4*sin((1:numel(pq))'));
probe.bus(nonref,9)=probe.bus(nonref,9)+.001*cos((1:numel(nonref))');
[independent,success]=runpf(probe,mpopt);
reference_error=max(abs(complex_voltage(independent)-complex_voltage(full)));
record('revised_full_NR_from_perturbed_start_identity',success&&reference_error<2e-7,reference_error);
independent_audit=audit_ac_solution(allocation.final_input,independent);
record('revised_independent_detailed_KCL',max(independent_audit.max_nodal_P_residual_mw,independent_audit.max_nodal_Q_residual_mvar)<1e-5, ...
    max(independent_audit.max_nodal_P_residual_mw,independent_audit.max_nodal_Q_residual_mvar));
w=table(25,1.5,90,1000,101325,'VariableNames',{'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'});
cached=struct('full',full,'audit',revised_audit,'allocation',allocation);
screen=screen_nygrid_2025_loss_pf_thermal(cached,w);
record('one_way_thermal_numeric_identities',screen.numerical_identities_passed,screen.maximum_Joule_loss_identity_error_MW);
record('one_way_thermal_preserves_electrical_case',isequaln(cached.full,full)&&isequaln(cached.allocation,allocation) ...
    &&~screen.current_gamma_rescaling_applied&&~screen.OPF_run&&~screen.resistance_temperature_feedback_run,0);
record('thermal_excludes_equivalent_and_identity_conflicts', ...
    ~any(ismember(screen.branch_screen.original_parent_row,[224 300 309 310 386])),0);
bad=allocation.final_input;
sg=bad.userdata.ac_system.thermal_segments;
if iscell(sg),sg=struct2table([sg{:}]);elseif isstruct(sg),sg=struct2table(sg);end
candidate_row=screen.candidate_segments.branch_row(1);bad_parent=bad.userdata.ac_system.branch_parent_row(candidate_row);
hit=find(double(sg.branch_row)==candidate_row,1);sg.base_kv(hit)=sg.base_kv(hit)+1;
bad.userdata.ac_system.thermal_segments=sg;
[~,badledger]=nygrid_handoff_thermal_candidates(bad);badrow=badledger.original_parent_row==bad_parent;
record('malformed_segment_kV_is_rejected',~badledger.research_screen_eligible(badrow) ...
    &&contains(string(badledger.reason(badrow)),'segment_voltage_base_differs_from_electrical_endpoints'),0);
rejected=false;rejection_id='';
try,ac_dlr_prepare_case(allocation.final_input,w,'reference');catch ex,rejection_id=ex.identifier;rejected=strcmp(ex.identifier,'acDLR:HardwareLimits');end
record('legacy_DLR_adapter_rejects_revised_unqualified_hardware_case',rejected,0);
[adapted,legacy_limits]=ac_dlr_prepare_case(m,w,'reference');
record('historical_adapter_preserves_load_dispatch_transfers',isequal(adapted.bus,m.bus)&&isequal(adapted.gen,m.gen) ...
    &&isequal(adapted.dcline,m.dcline)&&isequal(adapted.gencost,m.gencost),0);
[tiny_result,tiny]=small_MIPS_fixture();
record('small_MIPS_current_constraint_callback_fixture',tiny.passed,0);
profile off;prof=profile('info');[loaded,~]=inmem('-completenames');
executed=unique([string({prof.FunctionTable.FileName})';string(loaded(:))]);executed(executed=="")=[];
closure=struct('path',{},'scope',{},'sha256',{});outside=strings(0,1);
for k=1:numel(executed)
    name=char(executed(k));if ~isfile(name),continue;end
    absolute=char(java.io.File(name).getCanonicalPath());scope='unapproved_external';
    if startsWith(absolute,[setup.matpower_root filesep],'IgnoreCase',true),scope='selected_MATPOWER';
    elseif startsWith(absolute,[root filesep],'IgnoreCase',true),scope='package_project';
    elseif startsWith(absolute,[matlabroot filesep],'IgnoreCase',true),scope='MATLAB_distribution';
    else,outside(end+1)=string(absolute);end %#ok<AGROW>
    closure(end+1)=struct('path',absolute,'scope',scope,'sha256',filehash(absolute)); %#ok<AGROW>
end
record('executed_files_resolve_only_inside_package_selected_vendor_or_MATLAB',isempty(outside),numel(outside));
runtime_path=strsplit(path,pathsep);badpath=strings(0,1);
for k=1:numel(runtime_path)
    p=char(java.io.File(runtime_path{k}).getCanonicalPath());
    if ~strcmpi(p,root)&&~startsWith(p,[root filesep],'IgnoreCase',true) ...
            &&~strcmpi(p,matlabroot)&&~startsWith(p,[matlabroot filesep],'IgnoreCase',true) ...
            &&~strcmpi(p,setup.matpower_root)&&~startsWith(p,[setup.matpower_root filesep],'IgnoreCase',true)
        badpath(end+1)=string(p); %#ok<AGROW>
    end
end
record('search_path_has_no_hidden_external_project_folders',isempty(badpath),numel(badpath));
tests=table(names,passed,errors,'VariableNames',{'test','passed','error'});
report=struct('passed',all(passed),'test_count',numel(passed),'generated_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd HH:mm:ss Z')), ...
    'setup',setup,'output_dir',output_dir,'hour_case_dimensions',hour_cases,'tests',table2struct(tests), ...
    'selected_hour',8508,'standard_full_PF_uses_declared_legacy_core',true, ...
    'legacy_full_compact_voltage_error_pu',legacy_error,'revised_full_NR_voltage_error_pu',reference_error, ...
    'revised_audit',revised_audit,'independent_detailed_audit',independent_audit, ...
    'thermal_candidate_parent_count',screen.candidate_parent_count,'thermal_candidate_runtime_branch_count',screen.candidate_runtime_branch_count, ...
    'thermal_candidate_segment_count',screen.candidate_segment_count,'thermal_maximum_series_utilization',screen.maximum_series_ampacity_utilization, ...
    'thermal_maximum_section_end_utilization',screen.maximum_section_end_ampacity_utilization, ...
    'thermal_Joule_identity_error_MW',screen.maximum_Joule_loss_identity_error_MW, ...
    'thermal_terminal_current_identity_error_A',screen.maximum_terminal_current_crosscheck_error_A, ...
    'thermal_heat_identity_error_W_per_m',screen.maximum_heat_residual_at_ampacity_W_per_m, ...
    'legacy_adapter_revised_case_rejection_id',rejection_id,'legacy_adapter_branch_count',height(legacy_limits.branch), ...
    'small_MIPS_fixture',tiny,'removed_optimization_toolbox_paths',{removed},'license_features_in_use',license('inuse'), ...
    'fmincon_resolution',which('fmincon'),'linprog_resolution',which('linprog'), ...
    'executed_file_count',numel(closure),'unapproved_executed_files',outside,'unapproved_search_paths',badpath, ...
    'complete_search_path',{runtime_path},'annual_replay_run',false,'NYGRID_OPF_run',false, ...
    'installed_asset_DLR_qualification',false,'whole_system_operating_qualification',false, ...
    'scope','selected-hour portable PF and one-way synthetic thermal smoke; no annual rerun; fixture OPF only');
writetable(tests,fullfile(output_dir,'smoke_tests.csv'));
writetable(struct2table(closure),fullfile(output_dir,'loaded_function_dependencies.csv'));
writetable(screen.candidate_and_exclusion_ledger,fullfile(output_dir,'thermal_candidate_and_exclusion_ledger.csv'));
writetable(screen.candidate_segments,fullfile(output_dir,'thermal_candidate_segments.csv'));
writetable(screen.branch_screen,fullfile(output_dir,'thermal_branch_screen.csv'));
writetable(screen.segment_screen,fullfile(output_dir,'thermal_segment_screen.csv'));
save(fullfile(output_dir,'smoke_selected_hour_results.mat'),'m','legacy','compact','compact_audit','recovered', ...
    'revised','revised_audit','full','allocation','independent','screen','tiny_result','report','-v7.3');
fid=fopen(fullfile(output_dir,'smoke_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
disp(tests);fprintf('HANDOFF_SMOKE pass%d tests%d candidates%d runtimebranches%d\n',report.passed,report.test_count,screen.candidate_parent_count,screen.candidate_runtime_branch_count);
assert(report.passed,'handoff:SmokeFailure','One or more reproducibility checks failed; inspect smoke_receipt.json.');
    function record(name,ok,error_value)
        names(end+1,1)=string(name);passed(end+1,1)=logical(ok);errors(end+1,1)=error_value;
        fprintf('SMOKE %s pass%d error%.12g\n',name,ok,error_value);
    end
end

function V=complex_voltage(m),V=m.bus(:,8).*exp(1j*deg2rad(m.bus(:,9)));end

function removed=reset_to_base_path()
% Keep this script call out of the main function's static nested workspace.
restoredefaultpath;
% Optional MATPOWER backends may be detected statically; selected NR/MIPS
% execution must work with Optimization Toolbox removed from the path.
pathparts=strsplit(path,pathsep);removed={};
for j=1:numel(pathparts)
    if ~startsWith(pathparts{j},[matlabroot filesep],'IgnoreCase',true) ...
            ||contains(lower(strrep(pathparts{j},'\','/')),'/toolbox/optim') ...
            ||contains(lower(strrep(pathparts{j},'\','/')),'/toolbox/shared/optim')
        removed{end+1}=pathparts{j};rmpath(pathparts{j}); %#ok<AGROW>
    end
end
end

function [r,report]=small_MIPS_fixture()
m=struct('version','2','baseMVA',100);
m.bus=[1 3 0 0 0 0 1 1 0 345 1 1.1 .9;2 1 50 20 0 0 1 1 0 345 1 1.1 .9];
m.branch=[1 2 .01 .1 .02 1000 0 0 0 0 1 -360 360];
m.gen=[1 50 0 100 -100 1 100 1 200 0 zeros(1,11)];m.gencost=[2 0 0 3 .01 1 0];
realization=table(1,1,1,345,'VariableNames',{'branch_row','circuits','bundle_count','base_kv'});
m=add_dlr_series_current_constraints(m,realization,400);
ends=table(1,450,450,'VariableNames',{'branch_row','total_terminal_current_limit_from_a','total_terminal_current_limit_to_a'});
m=add_ac_terminal_current_limits(m,ends);
mpopt=mpoption('verbose',0,'out.all',0,'opf.ac.solver','MIPS','mips.max_it',100);
[r,success]=runopf(m,mpopt);a=ac_terminal_current_audit(r,ends);
V=complex_voltage(r);I=abs((V(1)-V(2))/complex(m.branch(3),m.branch(4)))*100000/(sqrt(3)*345);
report=struct('passed',logical(success&&a.passed&&I<=400*(1+1e-6)),'solver','MIPS', ...
    'success',logical(success),'series_current_A',I,'series_limit_A',400,'terminal_limit_A',450, ...
    'maximum_terminal_fraction',a.maximum_fraction,'user_authored_fixture_not_MATPOWER_case_data',true, ...
    'NYGRID_operating_feasibility_evidence',false);
end

function digest=filehash(path)
fid=fopen(path,'rb');assert(fid>=0);clean=onCleanup(@()fclose(fid));e=java.security.MessageDigest.getInstance('SHA-256');
while ~feof(fid),b=fread(fid,1048576,'*uint8');if ~isempty(b),e.update(typecast(b,'int8'));end,end
digest=lower(reshape(dec2hex(typecast(e.digest(),'uint8'),2)',1,[]));
end
