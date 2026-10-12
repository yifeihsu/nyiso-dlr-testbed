function report = run_electrical_validation(stage)
% Selected seasonal/load/topology checks; never an annual AC feasibility claim.
if nargin<1,stage='final';end
assert(any(strcmp(stage,{'provisional','revision02','revision03','final'})));
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
out=fullfile(root,'output','nygrid_2025_ac_system','ac_validation',['electrical_' stage]);
if ~isfolder(out),mkdir(out);end
states=load(fullfile(root,'output','nygrid_2025_dover_parameters','replay','operating_states.mat'), ...
    'qualified','post_full_service','timestamp_utc');
dispatch=load(fullfile(root,'output','nygrid_2025_dispatch','dispatch','dispatch.mat'),'bus_pd');
reg=readtable(fullfile(root,'output','nygrid_2025_dispatch','dispatch','model_generator_register.csv'),'TextType','string');
q=logical(states.qualified(:));post=logical(states.post_full_service(:));demand=sum(dispatch.bus_pd,2);
clock=datetime(string(states.timestamp_utc(:)),'InputFormat','yyyy-MM-dd''T''HH:mm:ss''Z''','TimeZone','UTC');
eligible=find(q);[~,lo]=min(demand(q));[~,hi]=max(demand(q));
winter=find(q&ismember(month(clock),[1 2 12]));[~,wi]=max(demand(winter));
summer=find(q&ismember(month(clock),[6 7 8]));[~,su]=max(demand(summer));
selection=[eligible(lo);eligible(hi);winter(wi);summer(su);4000;8508;find(q&~post,1,'last');find(q&post,1,'first')];
reasons=["annual_qualified_minimum_load";"annual_qualified_maximum_load";"winter_qualified_maximum_load"; ...
    "summer_qualified_maximum_load";"pre_Dover_midyear_reference";"post_Dover_reference"; ...
    "last_qualified_pre_Dover_hour";"first_qualified_post_Dover_hour"];
selection_table=table(selection,reasons,'VariableNames',{'hour_index','selection_reason'});
writetable(selection_table,fullfile(out,'selection_plan.csv'));
hours=unique(selection,'stable');assert(all(q(hours)));
opt=mpoption('model','AC','verbose',0,'out.all',0,'opf.ac.solver','IPOPT', ...
    'opf.violation',1e-7,'ipopt.opts.max_iter',250,'ipopt.opts.tol',1e-9, ...
    'ipopt.opts.bound_relax_factor',0);
rows=struct([]);capabilities=table();expected_overlay_sha='';expected_design_sha='';expected_plan_sha='';expected_generator_sha='';
for h=hours'
    m=npcc_nygrid_2025_ac(h);prior=npcc_nygrid_2025_dover_dc(h,'bounded','x_nominal');
    u=m.userdata.ac_system;
    if isempty(expected_generator_sha),expected_generator_sha=u.generator_capability_policy_sha256;end
    assert(strcmp(expected_generator_sha,u.generator_capability_policy_sha256), ...
        'AC:GeneratorPolicyChangedDuringValidation','Reactive capability policy changed during validation.');
    if isempty(expected_overlay_sha),expected_overlay_sha=u.branch_parameter_overlay_sha256;end
    assert(strcmp(expected_overlay_sha,u.branch_parameter_overlay_sha256), ...
        'AC:OverlayChangedDuringValidation','Branch overlay changed during this validation.');
    if isfield(u,'line_design_receipt_sha256')
        if isempty(expected_design_sha),expected_design_sha=u.line_design_receipt_sha256;end
        assert(strcmp(expected_design_sha,u.line_design_receipt_sha256), ...
            'AC:DesignChangedDuringValidation','Line-section/reactor design changed during validation.');
    end
    if isfield(u,'sectioned_design_plan_sha256')
        if isempty(expected_plan_sha),expected_plan_sha=u.sectioned_design_plan_sha256;end
        assert(strcmp(expected_plan_sha,u.sectioned_design_plan_sha256), ...
            'AC:PlanChangedDuringValidation','Section plan changed during validation.');
    end
    if strcmp(stage,'final')
        assert(u.sectioned_design_construction_checked&&~contains(string(u.sectioned_design_status),'provisional'), ...
            'AC:ProvisionalDesign','Final electrical validation requires checked derived line design.');
    end
    [found,ix]=ismember(prior.bus(:,1),m.bus(:,1));assert(all(found));
    added=~ismember(m.bus(:,1),prior.bus(:,1));
    preserve=isequal(m.bus(ix,3:4),prior.bus(:,3:4))&&all(m.bus(added,3:4)==0,'all') ...
        &&isequal(m.gen(:,[1 2 8 9 10]),prior.gen(:,[1 2 8 9 10]))&&isequal(m.dcline,prior.dcline);
    assert(preserve&&m.baseMVA==100&&~u.current_gamma_lift&&~isfield(m.userdata,'slim'));
    assert(isequal(reg.gen_row,(1:size(m.gen,1))'));
    assert(isequal(reg.bus_id(reg.role=="fixed_external"),m.gen(u.external_generator_mask,1)));
    cap=table(repmat(h,size(m.gen,1),1),reg.gen_row,reg.device_key,reg.role,reg.bus_id,m.gen(:,1), ...
        m.gen(:,8),m.gen(:,2),m.gen(:,10),m.gen(:,9),m.gen(:,5),m.gen(:,4), ...
        u.generator_capability_reference,u.generator_assumed_s_cap,u.p_objective_weight,u.q_objective_weight, ...
        'VariableNames',{'hour_index','generator_row','device_key','role','original_register_bus_id','current_corrected_bus_id','status', ...
        'PG_prior_MW','Pmin_MW','Pmax_MW','Qmin_MVAr','Qmax_MVAr','capability_reference_MW', ...
        'assumed_S_proxy_MVA','P_objective_weight','Q_objective_weight'});
    capabilities=[capabilities;cap]; %#ok<AGROW>
    t=tic;[r,success]=runopf(m,opt);elapsed=toc(t);
    [a,detail]=audit_ac_solution(m,r);
    a.hour_index=h;a.timestamp_utc=char(u.timestamp_utc);a.seconds=elapsed;
    a.baseMVA=m.baseMVA;a.buses=size(m.bus,1);a.branches=size(m.branch,1);a.active_branches=nnz(m.branch(:,11));
    a.original_power_inputs_preserved=preserve;a.total_PD_MW=sum(m.bus(:,3));a.total_QD_MVAr=sum(m.bus(:,4));
    a.branch_overlay_sha256=u.branch_parameter_overlay_sha256;
    a.line_design_receipt_sha256=expected_design_sha;
    a.sectioned_design_plan_sha256=expected_plan_sha;
    a.generator_capability_policy_sha256=expected_generator_sha;
    a.generator_reactive_policy_version=u.generator_reactive_policy_version;
    a.electrical_equipment_limits_only=true;a.thermal_conductor_limits_audited=false;
    a.source_status=char(u.sectioned_design_status);
    a.ACPF_replay_attempted=false;a.ACPF_replay_passed=false;
    if success
        [pf,pa,pf_detail,pf_input,pf_options]=replay_acpf_solution(m,r);
        a.ACPF_replay_attempted=true;a.ACPF_replay_passed=pa.passed;
        save(fullfile(out,sprintf('hour_%04d_ACPF.mat',h)),'pf','pa','pf_detail','pf_input','pf_options');
        fid=fopen(fullfile(out,sprintf('hour_%04d_ACPF.json',h)),'w');fprintf(fid,'%s\n',jsonencode(pa,'PrettyPrint',true));fclose(fid);
        a.passed=a.passed&&pa.passed;
    end
    save(fullfile(out,sprintf('hour_%04d.mat',h)),'m','r','opt','a','detail');
    fid=fopen(fullfile(out,sprintf('hour_%04d.json',h)),'w');fprintf(fid,'%s\n',jsonencode(a,'PrettyPrint',true));fclose(fid);
    residuals=table(detail.bus_id,detail.P_residual_mw,detail.Q_residual_mvar, ...
        'VariableNames',{'bus_id','P_balance_residual_MW','Q_balance_residual_MVAr'});
    writetable(residuals,fullfile(out,sprintf('hour_%04d_nodal_balance.csv',h)));
    rows=[rows a]; %#ok<AGROW>
    fprintf('ELECTRICAL h%d nb%d success%d audit%d %.2fs P%.3g Q%.3g V%.3g MVA%.3g\n', ...
        h,size(m.bus,1),success,a.passed,elapsed,a.max_nodal_P_residual_mw,a.max_nodal_Q_residual_mvar,a.max_voltage_bound_violation_pu,a.max_equipment_MVA_violation);
end
writetable(capabilities,fullfile(out,'selected_hour_generator_assumptions.csv'));
report=struct('complete',true,'passed',all([rows.passed]),'stage',stage, ...
    'modeltype','bounded_synthetic_AC','selection_based_on_load_season_and_topology_not_success',true, ...
    'selected_hour_count',numel(hours),'hour_index',hours,'annual_ACOPF_performed',false, ...
    'all_8760_hours_or_all_qualified_hours_AC_feasible_claimed',false, ...
    'thermal_conductor_constraints_checked',false,'physical_historical_AC_replay_claimed',false, ...
    'checks',rows,'solver','IPOPT','bound_relax_factor',0,'solver_tolerance',1e-9, ...
    'branch_parameter_overlay_sha256',expected_overlay_sha,'all_selected_ACPF_replays_passed',all([rows.ACPF_replay_passed]), ...
    'line_design_receipt_sha256',expected_design_sha, ...
    'sectioned_design_plan_sha256',expected_plan_sha, ...
    'generator_capability_policy_sha256',expected_generator_sha, ...
    'original_all_native_P_boxes_external_schedules_six_transfers_and_loads_preserved',true);
fid=fopen(fullfile(out,'electrical_validation.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
end
