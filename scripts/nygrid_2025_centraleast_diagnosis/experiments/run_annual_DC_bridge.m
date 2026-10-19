function report=run_annual_DC_bridge()
% Four fresh MATPOWER DCPF variants on the fixed8494 detailed-AC cohort.
% Original public148/archive/fullparent parity is established by11freshpoints.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'scripts','nygrid_2025_acpf_profile_audit','acpf'));
base=fullfile(root,'output','nygrid_2025_centraleast_diagnosis','experiments');out=fullfile(base,'annual_DC_bridge');if ~isfolder(out),mkdir(out);end
proof=jsondecode(fileread(fullfile(base,'representative_bridge','bridge_receipt.json')));assert(proof.passed);
archive=load(fullfile(base,'archived_DC_reference.mat'));cache=load_profile_cache();canonical=cache.canonical;
cohort=false(8760,1);
for month=1:12
    d=load(fullfile(root,'output','nygrid_2025_acpf_profile_audit','acpf','monthly',sprintf('profile_PF_2025_%02d.mat',month)), ...
        'hour_index','source_qualified','AC_equation_gate','P_profile_preservation_gate');
    cohort(d.hour_index)=d.source_qualified&d.AC_equation_gate&d.P_profile_preservation_gate;
end
assert(nnz(cohort)==8494&&all(cache.qualified(cohort))&&isequal(cache.qualified,logical(archive.qualified(:))));
variant_names={'detailed_AC_network_DCPF','restore_parent224_X','restore_parent41_X','restore_all33_X'};
templates=cell(4,1);weights=cell(4,1);ib=cell(4,1);member_rows=cell(4,1);member_sign=cell(4,1);
for s=1:4
    h=[523 3360 4000 8508];b=load(fullfile(base,'representative_bridge',sprintf('bridge_h%04d.mat',h(s))), 'full','weights','detailed');
    assert(isequal(b.detailed.branch(:,[1 2 3:9 11:13]),cache.templates{s}.branch(:,[1 2 3:9 11:13])));
    templates{s}=b.full;weights{s}=b.weights;
    [ok,ib{s}]=ismember(cache.templates{s}.bus(:,1),canonical.bus(:,1));assert(all(ok));
    signed=double(b.full.('if').map(b.full.('if').map(:,1)==5,2));assert(isequal(signed(:),[-33;-36;-40;-42]));
    member_sign{s}=sign(signed);member_rows{s}=zeros(4,1);
    for j=1:4
        p=abs(signed(j));member_rows{s}(j)=find(b.detailed.userdata.ac_system.branch_parent_row==p & b.detailed.branch(:,1)==b.full.branch(p,1));
    end
end
opt=mpoption('model','DC','verbose',0,'out.all',0,'exp.use_legacy_core',1);
interface_model_MW=nan(8760,7,4);CE_member_model_MW=nan(8760,4,4);VA_deg=nan(8760,size(canonical.bus,1),4);
converged=false(8760,4);audit_passed=false(8760,4);max_KCL_MW=nan(8760,4);max_branch_law_MW=nan(8760,4);PF_seconds=nan(8760,4);
slack_increment_MW=nan(8760,4);all33_parity_MW=nan(8760,1);hours=find(cohort);started=tic;
for ii=1:numel(hours)
    h=hours(ii);s=cache.state_index(h);m=profile_case_from_cache(cache,h);full=templates{s};w=weights{s};
    for k=1:4
        if k==1,v=m;elseif k==2,v=restore_parent_X_only(m,full,224);elseif k==3,v=restore_parent_X_only(m,full,41);else,v=restore_parent_X_only(m,full,'all_changed');end
        t=tic;r=rundcpf(v,opt);PF_seconds(h,k)=toc(t);a=audit_diagnostic_DCPF(v,r);
        converged(h,k)=r.success;audit_passed(h,k)=a.passed;max_KCL_MW(h,k)=a.max_nodal_P_residual_MW;max_branch_law_MW(h,k)=a.max_branch_law_error_MW;
        slack_increment_MW(h,k)=a.slack_PG_change_MW;VA_deg(h,ib{s},k)=r.bus(:,9);
        interface_model_MW(h,:,k)=w.PF(:,:,1)*r.branch(:,14)+w.PT(:,:,1)*r.branch(:,16);
        CE_member_model_MW(h,:,k)=member_sign{s}.*r.branch(member_rows{s},14);
        assert(abs(sum(CE_member_model_MW(h,:,k))-interface_model_MW(h,5,k))<1e-8);
    end
    all33_parity_MW(h)=max(abs(interface_model_MW(h,:,4)-archive.interface_pf(h,:)));
    if mod(ii,1000)==0||ii==100||ii==numel(hours)
        progress=struct('completed',false,'fixed_cohort_hours',numel(hours),'hours_complete',ii,'DCPF_solves_complete',4*ii, ...
            'elapsed_seconds',toc(started),'all_audits_passed_so_far',all(audit_passed(hours(1:ii),:),'all'), ...
            'maximum_all33_restoration_vs_archived_DC_MW',max(all33_parity_MW(hours(1:ii))));
        fid=fopen(fullfile(out,'progress.json'),'w');fprintf(fid,'%s\n',jsonencode(progress,'PrettyPrint',true));fclose(fid);
        fprintf('CE_ANNUAL_DC %d/%d h %d solves %.1fs allpass%d all33parity%.3gMW\n',ii,numel(hours),4*ii,progress.elapsed_seconds,progress.all_audits_passed_so_far,progress.maximum_all33_restoration_vs_archived_DC_MW);
    end
end
hour_index=(1:8760)';timestamp_utc=cache.dispatch.timestamp_utc;gamma=archive.gamma;source_qualified=cache.qualified;
bus_id=canonical.bus(:,1);state_index=cache.state_index;state_names=cache.state_names;CE_signed_parent_rows=[-33;-36;-40;-42];
archived_DC_interface_model_MW=archive.interface_pf;elapsed=toc(started);
save(fullfile(out,'annual_DC_bridge_arrays.mat'),'hour_index','timestamp_utc','gamma','source_qualified','cohort','variant_names', ...
    'interface_model_MW','CE_member_model_MW','CE_signed_parent_rows','VA_deg','bus_id','state_index','state_names', ...
    'converged','audit_passed','max_KCL_MW','max_branch_law_MW','PF_seconds','slack_increment_MW','all33_parity_MW','archived_DC_interface_model_MW','-v7');
file=dir(fullfile(out,'annual_DC_bridge_arrays.mat'));assert(file.bytes<100e6);
summary=struct([]);
for k=1:4
    values=interface_model_MW(cohort,5,k)/gamma;baseline=archive.interface_pf(cohort,5)/gamma;
    summary=[summary struct('variant',variant_names{k},'hours',numel(hours),'DCPF_audits_passed',all(audit_passed(cohort,k)), ...
        'CE_mean_public_MW',mean(values),'CE_mean_minus_archived_DC_public_MW',mean(values-baseline), ...
        'CE_min_minus_archived_DC_public_MW',min(values-baseline),'CE_max_minus_archived_DC_public_MW',max(values-baseline), ...
        'max_nodal_P_residual_MW',max(max_KCL_MW(cohort,k)),'max_branch_law_error_MW',max(max_branch_law_MW(cohort,k)), ...
        'total_DCPF_seconds',sum(PF_seconds(cohort,k)))]; %#ok<AGROW>
end
report=struct('completed',true,'passed',all(audit_passed(cohort,:),'all')&&max(all33_parity_MW(cohort))<1e-7, ...
    'fixed_original_AC_qualified_cohort_hours',8494,'solves',4*8494,'elapsed_seconds',elapsed,'output_bytes',file.bytes, ...
    'variants',{variant_names},'summary',summary,'maximum_all33_X_restore_vs_archived_DC_interface_error_model_MW',max(all33_parity_MW(cohort)), ...
    'all_original_8760_clock_positions_exported',true,'no_new_cohort_selection',true,'OPF_or_fitting_used',false, ...
    'source_profiles_transfers_and_R_B_taps_phase_status_shunts_preserved',true,'only_X_changes_in_three_diagnostic_variants',true, ...
    'observed_interface_values_read_by_solver',false,'diagnostic_not_production_model_change',true);
writetable(struct2table(summary),fullfile(out,'variant_summary.csv'));
fid=fopen(fullfile(out,'annual_DC_bridge_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
progress.completed=true;progress.elapsed_seconds=elapsed;progress.final_receipt='annual_DC_bridge_receipt.json';
fid=fopen(fullfile(out,'progress.json'),'w');fprintf(fid,'%s\n',jsonencode(progress,'PrettyPrint',true));fclose(fid);
disp(struct2table(summary));
end
