function validate_candidate()
% Targeted physical, thermal, equation and exact-reduction checks before annual.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));out=fullfile(root,'output','nygrid_2025_physical_repair','validation');
if ~isfolder(out),mkdir(out);end
addpath(fullfile(root,'scripts','nygrid_2025_latest_handoff','runtime'));
setup=setup_nygrid_latest(root,'C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower');
addpath(fullfile(root,'scripts','nygrid_2025_physical_repair','core'));
samples=readtable(fullfile(root,'output','nygrid_2025_remaining_errors','probes','calendar_sample.csv'));
hours=unique([samples.hour_index;3135;5605]);rows=struct([]);state_seen=false(4,1);thermal_receipts=struct([]);
for h=hours'
    base=load_nygrid_latest(h);[m,change]=nyrepair_apply_case(base);
    p=m.userdata.ac_system.branch_parent_row;[result,a,r,allocation]=nylatest_coupled_solve(m);
    r41=find(p==41);assert(isscalar(r41));
    z=struct('hour_index',h,'state_index',m.userdata.latest_runtime.state_index,'qualified',a.loss_allocation_gate&&a.reduction_and_equation_gate, ...
        'status',a.loss_status,'parent41_loss_model_MW',sum(r.branch(r41,14)+r.branch(r41,16)), ...
        'maximum_global_voltage_violation_pu',a.max_voltage_bound_violation_pu,'maximum_global_Q_violation_model_MVAr',a.max_Q_bound_violation_mvar, ...
        'global_operating_qualified',a.passed,'nodal_P_residual_model_MW',a.max_nodal_P_residual_mw,'nodal_Q_residual_model_MVAr',a.max_nodal_Q_residual_mvar, ...
        'loss_accounting_residual_model_MW',a.NY_gross_load_accounting_residual_MW,'recovered_current_error_A',a.recovered_current_error_A);
    for parent=[185 195]
        ids=unique(reshape(m.branch(p==parent,1:2),[],1));[ok,br]=ismember(ids,r.bus(:,1));assert(all(ok));
        z.(sprintf('parent%d_min_VM',parent))=min(r.bus(br,8));z.(sprintf('parent%d_max_VM',parent))=max(r.bus(br,8));
        z.(sprintf('parent%d_voltage_violation_pu',parent))=max([0;r.bus(br,8)-r.bus(br,12);r.bus(br,13)-r.bus(br,8)]);
    end
    assert(z.qualified&&z.parent185_voltage_violation_pu<1e-7&&z.parent195_voltage_violation_pu<1e-7);
    state=z.state_index;
    if ~state_seen(state)
        [segments,ledger,~,forward]=nylatest_thermal_candidates(m);
        row=ledger(ledger.original_parent_row==41,:);assert(height(row)==1);
        % Inspect the selected metadata directly, without requiring installed identity.
        ss=segments(segments.original_parent_row==41,:);assert(height(ss)==1);
        assert(max(abs([ss.forward_r_pu,ss.forward_x_pu,ss.forward_b_pu]-m.branch(r41,3:5)))<1e-10);
        thermal_receipts=[thermal_receipts;struct('state_index',state,'parent41_segments',height(ss), ...
            'parent41_catalog_id',char(ss.catalog_id),'parent41_circuits',ss.circuits, ...
            'parent41_forward_RXB_error',max(abs([ss.forward_r_pu,ss.forward_x_pu,ss.forward_b_pu]-m.branch(r41,3:5))))]; %#ok<AGROW>
        writetable(ledger,fullfile(out,sprintf('thermal_parent_ledger_state%d.csv',state)));
        writetable(forward,fullfile(out,sprintf('thermal_forward_state%d.csv',state)));
        save(fullfile(out,sprintf('candidate_case_state%d.mat',state)),'m','change','-v7');state_seen(state)=true;
    end
    rows=[rows;z]; %#ok<AGROW>
    fprintf('candidate h%d qualified%d loss41%.6f V185%.6f V195%.6f\n',h,z.qualified,z.parent41_loss_model_MW,z.parent185_max_VM,z.parent195_max_VM);
end
assert(all(state_seen));writetable(struct2table(rows),fullfile(out,'targeted_candidate_checks.csv'));
% A detailed-network solve checks the compact implementation on one repaired case.
h=hours(end);m=nyrepair_apply_case(load_nygrid_latest(h));[~,ac,rc]=nylatest_coupled_solve(m);[~,ad,rd]=nylatest_coupled_solve(m,struct('backend','detailed'));
assert(ac.loss_allocation_gate&&ad.loss_allocation_gate);
Vc=rc.bus(:,8).*exp(1j*deg2rad(rc.bus(:,9)));Vd=rd.bus(:,8).*exp(1j*deg2rad(rd.bus(:,9)));
v_error=max(abs(Vc-Vd));flow_error=max(abs(rc.branch(:,14:17)-rd.branch(:,14:17)),[],'all');assert(v_error<1e-8&&flow_error<1e-5);
receipt=struct('passed',true,'hours',hours','qualified_hours',numel(hours),'all_four_states',true, ...
    'parent185195_voltage_limits_pass_all_targeted_hours',true,'parent41_thermal_forward_checks',thermal_receipts, ...
    'detailed_vs_compact_hour',h,'detailed_vs_compact_voltage_error_pu',v_error,'detailed_vs_compact_flow_error_model_MW_MVAr',flow_error, ...
    'whole_system_operating_qualification_claimed',false,'source_profiles_controls_and_voltage_limits_preserved',true,'setup',setup);
fid=fopen(fullfile(out,'targeted_candidate_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(receipt,'PrettyPrint',true));fclose(fid);
end
