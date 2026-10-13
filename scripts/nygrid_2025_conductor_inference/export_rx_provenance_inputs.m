function report=export_rx_provenance_inputs()
% Read-only structural snapshots for catalog/geometry/RX provenance review.
% Constructs four dated cases but performs no PF, OPF, or annual replay.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(root,'System Matpower Format'));
addpath(fullfile(root,'scripts','nygrid_2025_ac_loss_revision','core'));
addpath(fullfile(root,'scripts','nygrid_2025_ac_system','thermal'));
addpath(fullfile(root,'scripts','nygrid_2025_dlr_handoff','runtime'));
out=fullfile(root,'output','nygrid_2025_conductor_inference','provenance_inputs');
if ~isfolder(out),mkdir(out);end
hours=[523 3360 4000 8508];states={'pre_may','may21','may30','post_dover'};
old=load(fullfile(root,'output','nygrid_2025_line_parameters','overlays','engineering_nominal','full191_network_cases.mat'));
post=load(fullfile(root,'output','nygrid_2025_dover_parameters','network','x_nominal.mat'));
rows=struct([]);
for i=1:numel(hours)
    h=hours(i);state=states{i};base=npcc_nygrid_2025_ac(h);
    m=ac_loss_prepare_case(base,'released_equivalent');
    if strcmp(state,'post_dover'),original=post.full_case;
    else,original=old.(['refined_2025_',state,'_case']);end
    [legacy_segments,legacy_ledger]=nygrid_handoff_thermal_candidates(m);
    thermal_segments=table2struct(m.userdata.ac_system.thermal_segments);
    branch=m.branch;bus=m.bus;baseMVA=m.baseMVA;
    branch_keys=cellstr(string(m.userdata.ac_system.branch_keys(:)));
    branch_parent_row=double(m.userdata.ac_system.branch_parent_row(:));
    branch_map=table2struct(m.userdata.ac_sections.branch_map);
    original_parent_branch=original.branch;original_parent_bus=original.bus;
    legacy_eligibility=table2struct(legacy_ledger);
    snapshot_metadata=struct('hour_index',h,'dated_state',state, ...
        'timestamp_utc',char(m.userdata.ac_system.timestamp_utc), ...
        'source_commit','51e424a139e0d0ec42fcbbb35749deaf119cffc2', ...
        'current_parameter_overlay','released_equivalent', ...
        'operating_case_not_solved',true,'PF_or_OPF_run',false, ...
        'thermal_records_taken_from_current_ac_system_table',true, ...
        'original_parent_parameters_are_before_AC_engineering_overlay',true);
    assert(~any(ismember([thermal_segments.original_branch_row],224)));
    assert(max(branch_parent_row)==size(original_parent_branch,1));
    for p=1:size(original_parent_branch,1)
        members=find(branch_parent_row==p);
        first=members([branch_map(members).physical_terminal_from]);
        last=members([branch_map(members).physical_terminal_to]);
        assert(isscalar(first)&&isscalar(last));
        assert(isequal([branch(first,1) branch(last,2)],original_parent_branch(p,1:2)));
    end
    file=fullfile(out,[state,'.mat']);
    save(file,'h','state','baseMVA','branch','bus','branch_keys','branch_parent_row','branch_map', ...
        'thermal_segments','original_parent_branch','original_parent_bus','legacy_eligibility','snapshot_metadata','-v7');
    writetable(struct2table(thermal_segments),fullfile(out,[state,'_thermal_segments.csv']));
    writetable(legacy_ledger,fullfile(out,[state,'_handoff_v1_eligibility.csv']));
    rows=[rows struct('state',state,'hour_index',h,'runtime_branch_count',size(branch,1), ...
        'runtime_OH_segment_count',numel(thermal_segments), ...
        'runtime_OH_parent_count',numel(unique([thermal_segments.original_branch_row])), ...
        'handoff_v1_segment_count',height(legacy_segments), ...
        'handoff_v1_parent_count',nnz(legacy_ledger.research_screen_eligible))]; %#ok<AGROW>
end
report=struct('passed',true,'PF_or_OPF_run',false,'annual_replay_run',false,'source_files_modified',false,'states',rows);
fid=fopen(fullfile(out,'export_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
disp(struct2table(rows));
end
