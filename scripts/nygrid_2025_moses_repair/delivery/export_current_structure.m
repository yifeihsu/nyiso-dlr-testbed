function export_current_structure()
% Read-only current-model structural exports, with no PF, OPF or annual replay.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
runtime=fullfile(root,'scripts','nygrid_2025_moses_repair','delivery','runtime');addpath(runtime);
setup_nygrid_latest(root,'C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower');
data=nylatest_data();
out=fullfile(root,'output','nygrid_2025_moses_repair','delivery','structure_inputs');
if ~isfolder(out),mkdir(out);end
writetable(data.thermal.branch_registry,fullfile(out,'current_branch_registry.csv'));
hours=[523 3360 4000 8508];states={'pre_may','may21','may30','post_dover'};
summary=struct([]);
for k=1:numel(hours)
    hour=hours(k);state=states{k};
    m=load_nygrid_latest(hour);
    p=nylatest_prepare_policy(m);c=nylatest_compact_build(m);
    [segments,eligibility,~,forward]=nylatest_thermal_candidates(m);
    bus=m.bus;branch=m.branch;gen=m.gen;dcline=m.dcline;baseMVA=m.baseMVA;
    bus_name=m.bus_name;genfuel=m.genfuel;
    retained_ids=c.retained_bus_ids;retained_rows=c.retained_full_rows;eliminated_rows=c.eliminated_full_rows;
    Yred=c.Yred;Yfull=c.Yfull;voltage_lift=c.voltage_lift;
    Yf_full=c.Yf_full;Yt_full=c.Yt_full;Yseries_full=c.Yseries_full;
    YfL=c.YfL;YtL=c.YtL;YseriesL=c.YseriesL;
    branch_keys=cellstr(string(c.branch_keys));branch_parent_row=c.branch_parent_row;
    branch_map=m.userdata.ac_sections.branch_map;
    if istable(branch_map),branch_map=table2struct(branch_map);end
    from_current_base_A=c.from_current_base_A;to_current_base_A=c.to_current_base_A;
    bus_group=p.bus_group;group_labels=p.labels;loss_ownership=p.loss_ownership;
    external_gen_group=p.external_gen_group;generator_share=p.generator_share;HQ=p.HQ;native=p.native;
    reference_bus=p.reference_bus;reference_generator_row=p.reference;
    external_current_rows=find(data.external.generator_mask);
    original_external_parent_rows=[(244:271)';NaN]; % Appended PV20 has no original NPCC generator row.
    boundary_injections=data.boundary_injections;
    boundary_injection_rows=double(data.boundary_injections.generator_rows(:));
    moses_source_repair=data.moses_source_repair;
    reactor_ledger=m.userdata.ac_sections.reactor_ledger;
    reactor_BS_delta_all_buses=m.userdata.ac_sections.reactor_BS_delta_all_buses;
    reactor_BS_bus_ids=m.userdata.ac_sections.reactor_BS_bus_ids;
    physical_repair=m.userdata.physical_repair;
    assumed_s_cap=m.userdata.ac_system.generator_assumed_s_cap;
    gamma=m.userdata.ac_system.gamma;timestamp_utc=char(m.userdata.ac_system.timestamp_utc);
    compact_validation=c.validation;source_fingerprint=c.source_fingerprint;operator_fingerprint=c.operator_fingerprint;
    save(fullfile(out,[state '.mat']),'hour','state','bus','branch','gen','dcline','baseMVA','bus_name','genfuel', ...
        'retained_ids','retained_rows','eliminated_rows','Yred','Yfull','voltage_lift','Yf_full','Yt_full','Yseries_full', ...
        'YfL','YtL','YseriesL','branch_keys','branch_parent_row','branch_map','from_current_base_A','to_current_base_A', ...
        'bus_group','group_labels','loss_ownership','external_gen_group','generator_share','HQ','native','reference_bus', ...
        'reference_generator_row','external_current_rows','original_external_parent_rows','assumed_s_cap', ...
        'gamma','timestamp_utc','reactor_ledger','reactor_BS_delta_all_buses','reactor_BS_bus_ids','physical_repair','boundary_injections', ...
        'boundary_injection_rows','moses_source_repair','compact_validation','source_fingerprint','operator_fingerprint','-v7');
    writetable(c.retention,fullfile(out,[state '_retention.csv']));
    writetable(segments,fullfile(out,[state '_thermal_segments.csv']));
    writetable(eligibility,fullfile(out,[state '_thermal_eligibility.csv']));
    writetable(forward,fullfile(out,[state '_thermal_forward.csv']));
    item=struct('state',state,'representative_hour',hour,'timestamp_utc',timestamp_utc, ...
        'retained_buses',numel(retained_ids),'detailed_buses',size(bus,1),'eliminated_buses',numel(eliminated_rows), ...
        'runtime_branches',size(branch,1),'active_runtime_branches',nnz(branch(:,11)>0), ...
        'parent_corridors',numel(unique(branch_parent_row)),'generators',size(gen,1),'active_generators_at_fixture',nnz(gen(:,8)>0), ...
        'fixed_transfers',size(dcline,1),'reference_bus',reference_bus,'reference_generator_row',reference_generator_row, ...
        'synthetic_thermal_parent_count',nnz(eligibility.research_screen_eligible), ...
        'synthetic_thermal_runtime_branch_count',numel(unique(segments.branch_row)), ...
        'synthetic_thermal_material_segment_count',height(segments),'Yred_nonzeros',nnz(Yred),'Yred_shape',size(Yred), ...
        'voltage_lift_shape',size(voltage_lift),'original_branch_current_operator_shape',size(YseriesL), ...
        'compact_construction_passed',c.validation.passed,'PF_or_OPF_run',false);
    summary=[summary item]; %#ok<AGROW>
    fprintf('CURRENT_STRUCTURE %s buses%d branches%d active%d retained%d thermalparents%d\n',state,size(bus,1),size(branch,1),nnz(branch(:,11)>0),numel(retained_ids),nnz(eligibility.research_screen_eligible));
end
fid=fopen(fullfile(out,'structure_export_summary.json'),'w');assert(fid>=0);fprintf(fid,'%s\n',jsonencode(summary,'PrettyPrint',true));fclose(fid);
end
