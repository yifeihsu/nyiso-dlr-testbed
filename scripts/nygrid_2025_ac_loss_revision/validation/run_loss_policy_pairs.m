function report=run_loss_policy_pairs(hours,label)
% Fresh independent compact/detailed solves of identical regional accounting.
if nargin<1,hours=[8508 4194 4860 3133];end
if nargin<2,label='initial_stress';end
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
addpath(fullfile(root,'scripts','nygrid_2025_ac_loss_revision','core'));
addpath(fullfile(root,'scripts','nygrid_2025_centraleast_diagnosis','experiments'));
out=fullfile(root,'output','nygrid_2025_ac_loss_revision','validation','pairs',label);if ~isfolder(out),mkdir(out);end
checks=struct([]);started=tic;
ws=warning;cleanup=onCleanup(@()warning(ws));warning('off','MATLAB:nearlySingularMatrix');warning('off','MATLAB:singularMatrix');
for h=hours(:)'
    base=npcc_nygrid_2025_ac(h);errors=struct([]);c=[];ca=[];cf=[];cl=[];d=[];da=[];df=[];dl=[];standard=[];standard_audit=[];
    options=struct('impedance_mode','released_equivalent','loss_mode','boundary_consistent','backend','compact');
    try,[c,ca,cf,cl]=run_nygrid_2025_loss_consistent_acpf(base,options);catch err,errors=[errors struct('backend','compact','identifier',err.identifier,'message',err.message,'report',getReport(err,'extended'))];end %#ok<AGROW>
    options.backend='detailed';
    try,[d,da,df,dl]=run_nygrid_2025_loss_consistent_acpf(base,options);catch err,errors=[errors struct('backend','detailed','identifier',err.identifier,'message',err.message,'report',getReport(err,'extended'))];end %#ok<AGROW>
    a=struct('hour_index',h,'compact_returned',~isempty(ca),'detailed_returned',~isempty(da), ...
        'compact_PF_converged',false,'detailed_PF_converged',false,'compact_loss_policy_gate',false,'detailed_loss_policy_gate',false, ...
        'compact_loss_iterations',NaN,'detailed_loss_iterations',NaN,'compact_seconds',NaN,'detailed_seconds',NaN, ...
        'maximum_complex_voltage_difference_pu',NaN,'maximum_branch_PQ_difference_MVA',NaN,'maximum_original_current_difference_A',NaN, ...
        'maximum_final_gen_PQ_difference_MVA',NaN,'maximum_scheduled_PG_difference_MW',NaN,'maximum_served_PQ_difference_MVA',NaN, ...
        'maximum_native_PG_change_from_original_MW',NaN,'maximum_DC_P_change_from_original_MW',NaN, ...
        'independent_compact_KCL_P_MW',NaN,'independent_compact_KCL_Q_MVAr',NaN, ...
        'maximum_budget_terminal_loss_identity_MW',NaN,'minimum_served_PD_MW',NaN,'maximum_NY_loss_fraction',NaN, ...
        'compact_Pbound_violation_MW',NaN,'compact_VQ_physical_gate',false, ...
        'standard_full_PF_replay_passed',false,'standard_full_PF_iterations',NaN, ...
        'standard_replay_voltage_error_pu',NaN,'standard_replay_branch_PQ_error_MVA',NaN, ...
        'native_HQ_and_fixed_DC_contract_passed',false,'per_bus_load_power_factor_preserved',false, ...
        'source_branch_and_control_arrays_match_backends',false,'both_qualified',false,'passed',false);
    if ~isempty(ca)
        a.compact_PF_converged=ca.PF_converged;a.compact_loss_policy_gate=ca.loss_allocation_gate;
        a.compact_loss_iterations=ca.loss_iterations;a.compact_seconds=ca.elapsed_seconds;
        a.minimum_served_PD_MW=ca.minimum_NY_served_PD_MW;a.maximum_NY_loss_fraction=ca.maximum_NY_zonal_loss_fraction;
        a.compact_Pbound_violation_MW=ca.max_P_bound_violation_mw;a.compact_VQ_physical_gate=ca.VQ_and_generator_assumption_gate;
    end
    if ~isempty(da)
        a.detailed_PF_converged=da.PF_converged;a.detailed_loss_policy_gate=da.loss_allocation_gate;
        a.detailed_loss_iterations=da.loss_iterations;a.detailed_seconds=da.elapsed_seconds;
    end
    a.both_qualified=a.compact_loss_policy_gate&&a.detailed_loss_policy_gate;
    if a.compact_loss_policy_gate
        seed=cl.final_input;seed.bus(:,8:9)=cf.bus(:,8:9);
        pq=find(seed.bus(:,2)==1);nonref=find(seed.bus(:,2)~=3);
        seed.bus(pq,8)=seed.bus(pq,8).*(1+1e-4*sin((1:numel(pq))'));
        seed.bus(nonref,9)=seed.bus(nonref,9)+.001*cos((1:numel(nonref))');
        opt=mpoption('model','AC','pf.alg','NR','pf.tol',1e-10,'pf.nr.max_it',50,'pf.enforce_q_lims',0,'exp.use_legacy_core',1,'verbose',0,'out.all',0);
        standard=runpf(seed,opt);standard_audit=audit_bridge_AC_solution(cl.final_input,standard);
        vs=standard.bus(:,8).*exp(1j*deg2rad(standard.bus(:,9)));vc=cf.bus(:,8).*exp(1j*deg2rad(cf.bus(:,9)));
        a.standard_full_PF_iterations=standard.iterations;
        a.standard_replay_voltage_error_pu=max(abs(vs-vc));
        a.standard_replay_branch_PQ_error_MVA=max(abs(standard.branch(:,14:17)-cf.branch(:,14:17)),[],'all');
        a.standard_full_PF_replay_passed=standard_audit.equation_and_profile_qualified&&a.standard_replay_voltage_error_pu<1e-7&&a.standard_replay_branch_PQ_error_MVA<1e-4;
    end
    if a.both_qualified
        m=cl.final_input;independent=audit_bridge_AC_solution(m,cf);
        vd=df.bus(:,8).*exp(1j*deg2rad(df.bus(:,9)));vc=cf.bus(:,8).*exp(1j*deg2rad(cf.bus(:,9)));
        a.maximum_complex_voltage_difference_pu=max(abs(vc-vd));
        a.maximum_branch_PQ_difference_MVA=max(abs(cf.branch(:,14:17)-df.branch(:,14:17)),[],'all');
        a.maximum_original_current_difference_A=max(abs(c.recovered_line_current_A-d.recovered_line_current_A),[],'all');
        a.maximum_final_gen_PQ_difference_MVA=max(abs(cf.gen(:,2:3)-df.gen(:,2:3)),[],'all');
        a.maximum_scheduled_PG_difference_MW=max(abs(m.gen(:,2)-dl.final_input.gen(:,2)));
        a.maximum_served_PQ_difference_MVA=max(abs(m.bus(:,3:4)-dl.final_input.bus(:,3:4)),[],'all');
        native=~base.userdata.ac_system.external_generator_mask;hq=find(base.userdata.ac_system.external_generator_mask&base.gen(:,1)==48);assert(isscalar(hq));
        a.maximum_native_PG_change_from_original_MW=max(abs(cf.gen(native,2)-base.gen(native,2)));
        a.maximum_DC_P_change_from_original_MW=max(abs(cf.dcline(:,4:5)-base.dcline(:,4:5)),[],'all');
        a.native_HQ_and_fixed_DC_contract_passed=a.maximum_native_PG_change_from_original_MW<1e-7 ...
            &&abs(cf.gen(hq,2)-base.gen(hq,2))<1e-8&&a.maximum_DC_P_change_from_original_MW<1e-8;
        use=base.bus(:,3)>0;ratio=m.bus(use,3)./base.bus(use,3);
        a.per_bus_load_power_factor_preserved=max(abs(m.bus(use,4)-base.bus(use,4).*ratio))<1e-8 ...
            &&all(m.bus(~use,3:4)==base.bus(~use,3:4),'all');
        a.independent_compact_KCL_P_MW=independent.max_P_residual_MW;a.independent_compact_KCL_Q_MVAr=independent.max_Q_residual_MVAr;
        a.maximum_budget_terminal_loss_identity_MW=abs(sum(cl.actual_budget_MW)-sum(cf.branch(:,14)+cf.branch(:,16)));
        a.source_branch_and_control_arrays_match_backends=isequal(m.branch,dl.final_input.branch)&&isequal(m.gen(:,[1 6 8]),dl.final_input.gen(:,[1 6 8])) ...
            &&isequal(m.dcline,dl.final_input.dcline)&&isequal(m.bus(:,[1 2 5:7 10:13]),dl.final_input.bus(:,[1 2 5:7 10:13]));
        a.passed=independent.equation_and_profile_qualified&&a.standard_full_PF_replay_passed&&a.native_HQ_and_fixed_DC_contract_passed&&a.per_bus_load_power_factor_preserved ...
            &&a.source_branch_and_control_arrays_match_backends&&a.maximum_complex_voltage_difference_pu<1e-7 ...
            &&a.maximum_branch_PQ_difference_MVA<1e-4&&a.maximum_original_current_difference_A<1e-3 ...
            &&a.maximum_final_gen_PQ_difference_MVA<1e-4&&a.maximum_scheduled_PG_difference_MW<1e-5 ...
            &&a.maximum_served_PQ_difference_MVA<1e-5&&a.maximum_budget_terminal_loss_identity_MW<1e-6;
    end
    save(fullfile(out,sprintf('h%04d.mat',h)),'base','c','ca','cf','cl','d','da','df','dl','standard','standard_audit','a','errors');
    checks=[checks a]; %#ok<AGROW>
    fprintf('LOSS_POLICY_PAIR h%d Cpf%d Cpolicy%d Dpf%d Dpolicy%d pass%d iter%.0f/%.0f V%.3g PQ%.3g nativePG%.3g minServed%.3g maxNYlossfrac%.4f\n', ...
        h,a.compact_PF_converged,a.compact_loss_policy_gate,a.detailed_PF_converged,a.detailed_loss_policy_gate,a.passed,a.compact_loss_iterations,a.detailed_loss_iterations, ...
        a.maximum_complex_voltage_difference_pu,a.maximum_branch_PQ_difference_MVA,a.maximum_native_PG_change_from_original_MW,a.minimum_served_PD_MW,a.maximum_NY_loss_fraction);
    if ~isempty(errors),disp(struct2table(errors));end
end
same_outcomes=[checks.compact_loss_policy_gate]==[checks.detailed_loss_policy_gate];both=[checks.both_qualified];
validation_passed=all([checks.compact_returned])&&all([checks.detailed_returned])&&all(same_outcomes)&&all([checks(both).passed]);
report=struct('completed',true,'passed',validation_passed,'all_attempted_cases_converged',all(both), ...
    'qualified_pair_count',nnz(both),'both_failed_hours',[checks(~[checks.compact_loss_policy_gate]&~[checks.detailed_loss_policy_gate]).hour_index], ...
    'outcome_disagreement_hours',[checks(~same_outcomes).hour_index], ...
    'failed_iterates_not_compared_as_solutions',true,'hours',hours,'label',label,'checks',checks,'elapsed_seconds',toc(started), ...
    'numerical_equivalence_not_physical_VQ_qualification',true,'OPF_used',false,'annual_run_started',false);
writetable(struct2table(checks),fullfile(out,'pair_checks.csv'));
fid=fopen(fullfile(out,'pair_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
end
