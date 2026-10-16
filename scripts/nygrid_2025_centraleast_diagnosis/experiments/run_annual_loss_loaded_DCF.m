function report=run_annual_loss_loaded_DCF()
% Three allocation conventions for frozen baselineAC branch real losses.
% Adds diagnostic PD only; original production profiles/models remain intact.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'scripts','nygrid_2025_acpf_profile_audit','acpf'));
base=fullfile(root,'output','nygrid_2025_centraleast_diagnosis','experiments');out=fullfile(base,'annual_loss_loaded_DCF');if ~isfolder(out),mkdir(out);end
proof=jsondecode(fileread(fullfile(base,'annual_DC_bridge','annual_DC_bridge_receipt.json')));assert(proof.passed);
dc=load(fullfile(base,'annual_DC_bridge','annual_DC_bridge_arrays.mat'),'cohort','interface_model_MW','archived_DC_interface_model_MW','gamma');
cache=load_profile_cache();canonical=cache.canonical;cohort=dc.cohort;assert(nnz(cohort)==8494);
labels={'half_each_runtime_branch_end','all_at_runtime_from_end','all_at_runtime_to_end'};
weights=cell(4,1);ib=cell(4,1);il=cell(4,1);from_rows=cell(4,1);to_rows=cell(4,1);
for s=1:4
    hours=[523 3360 4000 8508];b=load(fullfile(base,'representative_bridge',sprintf('bridge_h%04d.mat',hours(s))),'weights','detailed');weights{s}=b.weights;
    [ok,ib{s}]=ismember(cache.templates{s}.bus(:,1),canonical.bus(:,1));assert(all(ok));
    [ok,il{s}]=ismember(string(cache.templates{s}.userdata.ac_system.branch_keys),string(canonical.userdata.ac_system.branch_keys));assert(all(ok));
    [ok,from_rows{s}]=ismember(cache.templates{s}.branch(:,1),cache.templates{s}.bus(:,1));assert(all(ok));
    [ok,to_rows{s}]=ismember(cache.templates{s}.branch(:,2),cache.templates{s}.bus(:,1));assert(all(ok));
end
opt=mpoption('model','DC','verbose',0,'out.all',0,'exp.use_legacy_core',1);started=tic;completed_hours=0;
interface_model_MW=nan(8760,7,3);baseline_AC_interface_model_MW=nan(8760,7);VA_deg=nan(8760,size(canonical.bus,1),3);
audit_passed=false(8760,3);max_KCL_MW=nan(8760,3);max_branch_law_MW=nan(8760,3);PF_seconds=nan(8760,3);
slack_increment_MW=nan(8760,3);baseline_AC_loss_MW=nan(8760,1);max_non_slack_PG_change_MW=nan(8760,3);
for month=1:12
    old=load(fullfile(root,'output','nygrid_2025_acpf_profile_audit','acpf','monthly',sprintf('profile_PF_2025_%02d.mat',month)), ...
        'hour_index','source_qualified','AC_equation_gate','P_profile_preservation_gate','PF','PT','PD','QD','branch_keys');
    assert(isequal(string(old.branch_keys),string(canonical.userdata.ac_system.branch_keys)));
    for j=1:numel(old.hour_index)
        h=old.hour_index(j);if ~cohort(h),continue;end
        assert(old.source_qualified(j)&&old.AC_equation_gate(j)&&old.P_profile_preservation_gate(j));
        m=profile_case_from_cache(cache,h);s=cache.state_index(h);w=weights{s};nb=size(m.bus,1);
        assert(isequal(m.bus(:,3)',old.PD(j,ib{s}))&&isequal(m.bus(:,4)',old.QD(j,ib{s})));
        pf=old.PF(j,il{s})';pt=old.PT(j,il{s})';loss=pf+pt;
        assert(all(isfinite(loss))&&min(loss)>-1e-6&&max(abs(loss(m.branch(:,11)==0)))<1e-6);
        from_loss=accumarray(from_rows{s},loss,[nb 1]);to_loss=accumarray(to_rows{s},loss,[nb 1]);
        baseline_AC_loss_MW(h)=sum(loss);baseline_AC_interface_model_MW(h,:)=w.PF(:,:,1)*pf+w.PT(:,:,1)*pt;
        for k=1:3
            if k==1,added=(from_loss+to_loss)/2;elseif k==2,added=from_loss;else,added=to_loss;end
            assert(abs(sum(added)-sum(loss))<1e-7);v=m;v.bus(:,3)=v.bus(:,3)+added;
            assert(isequal(v.branch,m.branch)&&isequal(v.gen,m.gen)&&isequal(v.dcline,m.dcline)&&isequal(v.bus(:,[1 2 4:end]),m.bus(:,[1 2 4:end])));
            t=tic;r=rundcpf(v,opt);PF_seconds(h,k)=toc(t);a=audit_diagnostic_DCPF(v,r);
            audit_passed(h,k)=a.passed;max_KCL_MW(h,k)=a.max_nodal_P_residual_MW;max_branch_law_MW(h,k)=a.max_branch_law_error_MW;
            slack_increment_MW(h,k)=a.slack_PG_change_MW;max_non_slack_PG_change_MW(h,k)=a.max_non_slack_PG_change_MW;
            VA_deg(h,ib{s},k)=r.bus(:,9);interface_model_MW(h,:,k)=w.PF(:,:,1)*r.branch(:,14)+w.PT(:,:,1)*r.branch(:,16);
            assert(abs(slack_increment_MW(h,k)-sum(loss))<1e-6);
        end
        completed_hours=completed_hours+1;
    end
    progress=struct('completed',false,'months_complete',month,'hours_complete',completed_hours,'DCPF_solves_complete',3*completed_hours,'elapsed_seconds',toc(started));
    fid=fopen(fullfile(out,'progress.json'),'w');fprintf(fid,'%s\n',jsonencode(progress,'PrettyPrint',true));fclose(fid);
    fprintf('CE_ANNUAL_LOSS_DCF month%02d hours%d/8494 solves%d %.1fs\n',month,completed_hours,3*completed_hours,progress.elapsed_seconds);
end
assert(completed_hours==8494);hour_index=(1:8760)';timestamp_utc=cache.dispatch.timestamp_utc;gamma=dc.gamma;
bus_id=canonical.bus(:,1);state_index=cache.state_index;state_names=cache.state_names;source_qualified=cache.qualified;
baseline_detailed_DCF_interface_model_MW=dc.interface_model_MW(:,:,1);archived_DC_interface_model_MW=dc.archived_DC_interface_model_MW;
construction_delta_model_MW=baseline_detailed_DCF_interface_model_MW-archived_DC_interface_model_MW;
loss_allocation_delta_model_MW=interface_model_MW-baseline_detailed_DCF_interface_model_MW;
remaining_AC_minus_loss_loaded_DCF_model_MW=baseline_AC_interface_model_MW-interface_model_MW;
identity=construction_delta_model_MW+loss_allocation_delta_model_MW+remaining_AC_minus_loss_loaded_DCF_model_MW ...
    -(baseline_AC_interface_model_MW-archived_DC_interface_model_MW);
identity_max=max(abs(identity(cohort,:,:)),[],'all');assert(identity_max<1e-8);
elapsed=toc(started);
save(fullfile(out,'annual_loss_loaded_arrays.mat'),'hour_index','timestamp_utc','gamma','source_qualified','cohort','labels', ...
    'interface_model_MW','baseline_AC_interface_model_MW','baseline_detailed_DCF_interface_model_MW','archived_DC_interface_model_MW', ...
    'construction_delta_model_MW','loss_allocation_delta_model_MW','remaining_AC_minus_loss_loaded_DCF_model_MW', ...
    'VA_deg','bus_id','state_index','state_names','audit_passed','max_KCL_MW','max_branch_law_MW','PF_seconds', ...
    'slack_increment_MW','baseline_AC_loss_MW','max_non_slack_PG_change_MW','-v7');
file=dir(fullfile(out,'annual_loss_loaded_arrays.mat'));assert(file.bytes<100e6);
checks=struct([]);
for k=1:3
    contribution=loss_allocation_delta_model_MW(cohort,5,k)/gamma;remaining=remaining_AC_minus_loss_loaded_DCF_model_MW(cohort,5,k)/gamma;
    checks=[checks struct('allocation',labels{k},'hours',8494,'DCPF_audits_passed',all(audit_passed(cohort,k)), ...
        'CE_mean_public_MW',mean(interface_model_MW(cohort,5,k))/gamma, ...
        'mean_construction_delta_public_MW',mean(construction_delta_model_MW(cohort,5))/gamma, ...
        'mean_loss_allocation_delta_public_MW',mean(contribution),'mean_remaining_AC_minus_loss_loaded_public_MW',mean(remaining), ...
        'mean_absolute_remaining_public_MW',mean(abs(remaining)),'maximum_absolute_remaining_public_MW',max(abs(remaining)), ...
        'mean_baseline_AC_loss_model_MW',mean(baseline_AC_loss_MW(cohort)), ...
        'maximum_slack_minus_baseline_loss_MW',max(abs(slack_increment_MW(cohort,k)-baseline_AC_loss_MW(cohort))), ...
        'maximum_nodal_P_residual_MW',max(max_KCL_MW(cohort,k)),'maximum_branch_law_error_MW',max(max_branch_law_MW(cohort,k)))]; %#ok<AGROW>
end
report=struct('completed',true,'passed',all(audit_passed(cohort,:),'all'),'fixed_matched_cohort_hours',8494, ...
    'solves',3*8494,'elapsed_seconds',elapsed,'output_bytes',file.bytes,'checks',checks,'maximum_decomposition_identity_error_model_MW',identity_max, ...
    'original_branch_orientation_preserved',true,'losses_allocated_at_actual_runtime_section_ends',true, ...
    'negative_roundoff_losses_not_clipped',true,'all_three_allocate_same_total_baseline_AC_losses',true, ...
    'only_diagnostic_PD_changed',true,'non_slack_PG_six_transfers_and_network_parameters_preserved',true, ...
    'allocation_is_nonunique_sensitivity_not_confidence_interval',true,'no_actual_meter_or_causal_uniqueness_claim',true, ...
    'production_profiles_models_and_results_unchanged',true,'OPF_or_fitting_used',false,'observed_interface_values_read_by_solver',false);
writetable(struct2table(checks),fullfile(out,'allocation_summary.csv'));
fid=fopen(fullfile(out,'annual_loss_loaded_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
progress.completed=true;progress.final_receipt='annual_loss_loaded_receipt.json';progress.elapsed_seconds=elapsed;
fid=fopen(fullfile(out,'progress.json'),'w');fprintf(fid,'%s\n',jsonencode(progress,'PrettyPrint',true));fclose(fid);
disp(struct2table(checks));
end
