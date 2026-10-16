function report=run_representative_factorial()
% Four-cell attribution on fixed14points; no annual extrapolation or tuning.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
addpath(fullfile(root,'scripts','nygrid_2025_centraleast_diagnosis','experiments'));
out=fullfile(root,'output','nygrid_2025_ac_loss_revision','validation','representative_factorial');if ~isfolder(out),mkdir(out);end
hours=[2630 4194 523 4000 8508 8471 8472 3360 4746 4213 4740 3039 4860 3133];
cells={'legacy_engineering','legacy_single_slack';'released_equivalent','legacy_single_slack'; ...
    'legacy_engineering','boundary_consistent';'released_equivalent','boundary_consistent'};
qualified=false(numel(hours),4);CE=nan(numel(hours),4);checks=struct([]);started=tic;
source_records=loss_validation_source_records(root);
ws=warning;cleanup=onCleanup(@()warning(ws));warning('off','MATLAB:nearlySingularMatrix');warning('off','MATLAB:singularMatrix');
for j=1:numel(hours)
    h=hours(j);base=npcc_nygrid_2025_ac(h);prior=npcc_nygrid_2025_dover_dc(h,'bounded','x_nominal');parent=restore_full_DC_parent(prior,root);
    gamma=base.userdata.ac_system.gamma;
    for k=1:4
        options=struct('impedance_mode',cells{k,1},'loss_mode',cells{k,2},'backend','compact');
        [result,audit,r,allocation]=run_nygrid_2025_loss_consistent_acpf(base,options);
        values=physical_interface_flows(r,base.userdata.ac_system.branch_parent_row,parent)/gamma;
        nonref=true(size(base.gen,1),1);nonref(allocation.policy_contract.reference)=false;
        fixed_other_P=max(abs(r.gen(nonref,2)-base.gen(nonref,2)));
        compared=audit.PF_converged&&audit.AC_equation_gate&&audit.reduction_and_equation_gate;
        if strcmp(cells{k,2},'boundary_consistent'),compared=compared&&audit.loss_allocation_gate;
        else,compared=compared&&fixed_other_P<1e-7&&isequal(allocation.final_input.bus(:,3:4),base.bus(:,3:4));end
        qualified(j,k)=compared;if compared,CE(j,k)=values(5,1);end
        a=struct('hour_index',h,'cell_index',k,'impedance_mode',cells{k,1},'loss_mode',cells{k,2}, ...
            'PF_converged',audit.PF_converged,'equation_gate',audit.AC_equation_gate,'loss_policy_gate',audit.loss_allocation_gate, ...
            'reduction_equation_gate',audit.reduction_and_equation_gate,'comparison_qualified',compared, ...
            'physical_VQ_gate',audit.VQ_and_generator_assumption_gate,'status',audit.loss_status, ...
            'CE_qualified_public_MW',CE(j,k),'raw_CE_iterate_public_MW',values(5,1), ...
            'reference_PG_change_model_MW',audit.reference_PG_change_from_original_MW, ...
            'native_PG_change_model_MW',audit.native_PG_change_from_original_MW,'non_reference_source_PG_change_MW',fixed_other_P, ...
            'regional_import_residual_MW',audit.regional_NY_import_residual_MW,'NY_demand_accounting_residual_MW',audit.NY_gross_load_accounting_residual_MW, ...
            'total_AC_loss_model_MW',sum(allocation.actual_budget_MW),'maximum_NY_zonal_loss_fraction',audit.maximum_NY_zonal_loss_fraction, ...
            'minimum_NY_served_PD_model_MW',audit.minimum_NY_served_PD_MW,'NR_updates',audit.total_NR_iterations,'elapsed_seconds',audit.elapsed_seconds);
        save(fullfile(out,sprintf('h%04d_cell%d.mat',h,k)),'base','options','result','audit','r','allocation','values','a');
        checks=[checks a]; %#ok<AGROW>
        fprintf('LOSS_FACTORIAL h%d cell%d PF%d qualified%d CE%.3f status%s\n',h,k,a.PF_converged,compared,a.CE_qualified_public_MW,a.status);
    end
end
after=loss_validation_source_records(root);assert(isequal(source_records,after),'acLossFactorial:SourceChanged','Frozen source changed during representative replay.');
common=all(qualified,2);common_hours=hours(common);attribution=table();
for j=find(common)'
    dX=CE(j,2)-CE(j,1);dLoss=CE(j,3)-CE(j,1);combined=CE(j,4)-CE(j,1);interaction=combined-dX-dLoss;
    attribution=[attribution;table(hours(j),CE(j,1),CE(j,2),CE(j,3),CE(j,4),dX,dLoss,interaction,combined, ...
        'VariableNames',{'hour_index','legacy_public_MW','impedance_only_public_MW','loss_policy_only_public_MW','combined_public_MW', ...
        'impedance_effect_from_legacy_public_MW','loss_policy_effect_from_legacy_public_MW','interaction_public_MW','combined_effect_public_MW'})]; %#ok<AGROW>
end
report=struct('completed',true,'fixed_representative_hours',hours,'cell_order',{cells},'cell_qualified_counts',sum(qualified,1), ...
    'common_success_hour_count',numel(common_hours),'common_success_hours',common_hours,'qualification_matrix',qualified, ...
    'qualified_CE_public_MW',CE,'elapsed_seconds',toc(started),'source_records',source_records,'source_files_unchanged',true, ...
    'raw_failed_iterates_retained_but_excluded_from_attribution',true,'no_fitting_or_tuning',true, ...
    'representative_attribution_not_annual_effect_estimate',true,'physical_qualification_separate_from_PF_and_accounting',true);
writetable(struct2table(checks),fullfile(out,'factorial_checks.csv'));
if ~isempty(attribution),writetable(attribution,fullfile(out,'common_success_attribution.csv'));end
fid=fopen(fullfile(out,'factorial_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
disp(attribution);
end
