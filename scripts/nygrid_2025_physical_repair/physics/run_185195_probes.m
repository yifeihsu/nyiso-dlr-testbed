function run_185195_probes()
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
out=fullfile(root,'output','nygrid_2025_physical_repair','physics');if ~isfolder(out),mkdir(out);end
addpath(fullfile(root,'scripts','nygrid_2025_latest_handoff','runtime'));
setup_nygrid_latest(root,'C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower');
plan=jsondecode(fileread(fullfile(root,'output','nygrid_2025_remaining_errors','probes','probe_plan.json')));
hours=[plan.samples.hour_index];rows=struct([]);profiles=struct([]);
for h=hours
    base=load_nygrid_latest(h);[candidate,change]=nyrepair_apply_185195(base);
    for variant=1:2
        if variant==1,m=base;label='baseline';else,m=candidate;label='distributed_75pct';end
        [~,a,r,allocation]=nylatest_coupled_solve(m);
        c=nylatest_compact_build(m);qualified=a.loss_allocation_gate&&a.reduction_and_equation_gate;
        row=struct('hour_index',h,'variant',label,'qualified',qualified,'status',char(a.loss_status), ...
            'retained_bus_count',c.validation.retained_bus_count,'max_voltage_bound_violation_pu',a.max_voltage_bound_violation_pu, ...
            'max_Q_bound_violation_MVAr',a.max_Q_bound_violation_mvar,'regional_import_residual_MW',a.regional_NY_import_residual_MW, ...
            'max_nodal_P_residual_MW',a.max_nodal_P_residual_mw,'max_nodal_Q_residual_MVAr',a.max_nodal_Q_residual_mvar, ...
            'NY_assigned_loss_MW',sum(allocation.actual_budget_MW(1:11)));
        for parent=[185,195]
            rr=find(m.userdata.ac_system.branch_parent_row==parent);nodes=unique(reshape(m.branch(rr,1:2),[],1));
            br=ismember(r.bus(:,1),nodes);voltage=r.bus(br,8);violation=max([0;voltage-r.bus(br,12);r.bus(br,13)-voltage]);
            row.(sprintf('parent%d_min_VM',parent))=min(voltage);row.(sprintf('parent%d_max_VM',parent))=max(voltage);
            row.(sprintf('parent%d_max_V_violation',parent))=violation;
            profiles=[profiles;struct('hour_index',h,'variant',label,'parent_row',parent, ...
                'bus_ids',r.bus(br,1),'VM',voltage,'VA',r.bus(br,9),'BS_MVAr_at1pu',m.bus(br,6))]; %#ok<AGROW>
        end
        assert(c.validation.retained_bus_count==148);
        rows=[rows;row];fprintf('h%d %s qualified%d V185 %.6f V195 %.6f totalVviolation %.6f\n', ...
            h,label,qualified,row.parent185_max_VM,row.parent195_max_VM,row.max_voltage_bound_violation_pu); %#ok<AGROW>
    end
    writetable(struct2table(rows),fullfile(out,'selected_coupled_probes.csv'));
    save(fullfile(out,'selected_coupled_probes.mat'),'rows','profiles','change','hours','-v7');
end
end
