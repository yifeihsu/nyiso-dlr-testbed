function report=test_compact_nyiso_snapshot_inputs
%TEST_COMPACT_NYISO_SNAPSHOT_INPUTS Source pins, chronology and fit separation.
h=fileparts(mfilename('fullpath'));root=fileparts(fileparts(h));
o=build_compact_nyiso_snapshot_inputs;
assert(height(o.snapshots)==12&&height(o.loads)==132&&height(o.interfaces)==84 ...
    && height(o.boundaries)==48&&height(o.external_records)==132&&height(o.source_manifest)==20 ...
    && height(o.boundary_channels)==120&&height(o.boundary_policy)==11);
names="twelve_registered_scenarios_and_complete_source_rows";
assert(all(o.source_manifest.daily_archive_match)&&numel(unique(o.source_manifest.source_id))==20);
names(end+1)="twenty_pinned_daily_sources_equal_original_archive_members";
for k=1:height(o.snapshots)
    s=o.snapshots(k,:);l=o.loads(o.loads.scenario_id==s.scenario_id,:);
    assert(isequal(l.zone,string(('A':'K')'))&&abs(sum(l.target_load_mw)-s.benchmark_total_load_mw)<1e-8 ...
        && max(abs(l.target_load_mw/sum(l.target_load_mw)-l.load_share))<1e-14 ...
        && max(abs(l.target_load_mw-l.actual_load_mw*s.scale_factor_gamma))<1e-10);
end
names(end+1)="all_eleven_zonal_shares_exact_at_declared_benchmark_load";
for vintage=[2019 2025]
    s=o.snapshots(o.snapshots.vintage==vintage,:);peak=s(s.scenario_index==1,:);
    assert(all(s.scale_policy=="fixed_year_peak")&&numel(unique(s.scale_factor_gamma))==1 ...
        && abs(peak.benchmark_total_load_mw-10902.2197987)<1e-8 ...
        && max(abs(s.benchmark_total_load_mw/peak.benchmark_total_load_mw ...
        -s.actual_total_load_mw/peak.actual_total_load_mw))<1e-14 ...
        && all(s.scale_reference_source_id==peak.load_source_id) ...
        && all(ismember(s.scale_reference_source_id,o.source_manifest.source_id)));
end
assert(o.scale_policy=="fixed_year_peak"&&o.power_scale=="year_peak_scaled_benchmark_MW");
names(end+1)="one_pinned_year_peak_scale_preserves_seasonal_load_ratios";
diagnostic=build_compact_nyiso_snapshot_inputs(struct('scale_policy','per_snapshot_constant_total'));
assert(all(abs(diagnostic.snapshots.benchmark_total_load_mw-10902.2197987)<1e-8) ...
    && diagnostic.power_scale=="shape_normalized_benchmark_MW" ...
    && isequal(diagnostic.source_manifest,o.source_manifest) ...
    && isequal(diagnostic.loads.actual_load_mw,o.loads.actual_load_mw) ...
    && isequal(diagnostic.interfaces.actual_flow_mw,o.interfaces.actual_flow_mw) ...
    && isequal(diagnostic.external_records.actual_import_mw,o.external_records.actual_import_mw));
names(end+1)="old_constant_total_scaling_is_explicit_diagnostic_with_identical_raw_sources";
shoulder=build_compact_nyiso_snapshot_inputs(struct('scenario_ids',"S3_2025_SHOULDER_LIGHT_LOAD_EXACT"));
assert(height(shoulder.source_manifest)==3 ...
    && abs(shoulder.snapshots.scale_factor_gamma-10902.2197987/30644.9878)<1e-14 ...
    && abs(shoulder.snapshots.benchmark_total_load_mw-11083.2248*10902.2197987/30644.9878)<1e-8 ...
    && ismember(shoulder.snapshots.scale_reference_source_id,shoulder.source_manifest.source_id));
names(end+1)="nonpeak_subset_independently_pins_its_summer_reference_source";
reject(@()build_compact_nyiso_snapshot_inputs(struct('scale_policy','silent_rescale')), ...
    'compact_snapshots:ScalePolicy');
names(end+1)="unknown_scale_policy_is_rejected";
for field=["interfaces","external_records"]
    t=o.(field);assert(max(abs(t.target_positive_limit_mw-t.scale_factor_gamma.*t.actual_positive_limit_mw))<1e-9);
    if field=="interfaces",a=t.actual_flow_mw;b=t.target_flow_mw;else,a=t.actual_import_mw;b=t.target_import_mw;end
    assert(max(abs(b-t.scale_factor_gamma.*a))<1e-9);
end
names(end+1)="load_interface_and_boundary_values_share_one_gamma";
assert(all(isnan(o.loads.actual_load_q_mvar))&&all(isnan(o.loads.target_load_q_mvar)) ...
    && all(isnan(o.external_records.actual_q_mvar))&&all(isnan(o.generation_observations.actual_generation_mw)) ...
    && ~o.zonal_generation_observations_available&&~o.boundary_reactive_observations_available);
names(end+1)="unobserved_generation_and_reactive_power_remain_missing";
assert(~any(o.interfaces.training_target(o.interfaces.vintage==2019)) ...
    && ~any(o.interfaces.training_target(o.interfaces.dataset_split=="heldout")) ...
    && nnz(o.interfaces.training_target)==28 ...
    && all(o.loads.target_use=="operating_input")&&all(o.boundaries.target_use=="operating_input"));
names(end+1)="historical_and_heldout_interfaces_cannot_enter_default_2025_fit";
for vintage=[2019 2025]
    s=o.snapshots(o.snapshots.vintage==vintage,:);
    assert(all(s.dataset_split(1:4)=="training")&&all(s.dataset_split(5:6)=="heldout"));
end
names(end+1)="first_four_last_two_partition_is_explicit_per_vintage";
assert(all(o.snapshots.exact_timestamp_match)&&all(~o.snapshots.sampling_intervals_equal) ...
    && all(o.snapshots.timestamp==o.snapshots.interface_timestamp) ...
    && all(o.snapshots.timestamp==o.snapshots.boundary_timestamp));
names(end+1)="published_timestamps_match_without_claiming_equal_sampling_intervals";
replaced=o.snapshots(o.snapshots.scenario_id=="S3_2025_SHOULDER_LIGHT_LOAD_EXACT",:);
assert(height(replaced)==1&&replaced.timestamp=="2025-04-20 13:00" ...
    && abs(replaced.actual_total_load_mw-11083.2248)<1e-8 ...
    && height(o.rejected_pairings)==1&&o.rejected_pairings.offset_minutes==3 ...
    && ~o.rejected_pairings.use_for_calibration&&~o.rejected_pairings.use_for_validation ...
    && ~any(o.snapshots.scenario_id==o.rejected_pairings.scenario_id));
names(end+1)="archived_three_minute_pairing_excluded_and_exact_replacement_registered";
assert(all(~o.external_records.include_in_unreviewed_total) ...
    && nnz(~o.external_records.overlap_resolved)==12 ...
    && all(o.external_records.public_interface_name(~o.external_records.overlap_resolved)=="SCH - HQ_IMPORT_EXPORT") ...
    && ~o.complete_external_interchange_established);
names(end+1)="HQ_overlap_and_additional_components_cannot_be_silently_summed";
assert(nnz(o.boundary_policy.default_channel_include)==10 ...
    && ~any(o.boundary_channels.public_interface_name=="SCH - HQ_IMPORT_EXPORT") ...
    && nnz(o.boundary_channels.public_interface_name=="SCH - HQ_CEDARS")==12 ...
    && all(o.boundary_channels.default_channel_include)&&o.all_p32_external_records_accounted);
names(end+1)="ten_default_channels_include_Cedars_and_exclude_nested_HQ_report";
bs=o.boundary_sensitivity;
assert(height(bs)==1&&bs.default_HQ_actual_mw==1450&&bs.alternative_HQ_actual_mw==1157 ...
    && bs.actual_import_change_mw==-293&&~bs.electrical_sensitivity_solved ...
    && abs(bs.alternative_total_actual_import_mw-bs.default_total_actual_import_mw+293)<1e-9);
names(end+1)="HQ_sensitivity_replaces_one_channel_without_double_counting";
assert(all(~o.interfaces.source_limit_is_equipment_rating)&&any(o.interfaces.directional_limit_is_placeholder) ...
    && all(o.interfaces.source_field=="Flow (MWH)")&&~o.actual_MW_operating_model&&~o.dlr_ready);
names(end+1)="raw_unit_label_and_interface_limit_scope_remain_explicit";

% Published-value regression and exact source-row extraction, separate from
% the older derived targets. This covers a sign-changing external exchange.
sid="S1_2025_SUMMER_PEAK_PUBLIC";
one=build_compact_nyiso_snapshot_inputs(struct('scenario_ids',char(sid)));
assert(height(one.snapshots)==1&&height(one.source_manifest)==2 ...
    && abs(one.snapshots.actual_total_load_mw-30644.9878)<1e-8 ...
    && one.snapshots.timestamp_utc=="2025-07-29T22:00:00Z" ...
    && abs(one.boundaries.actual_import_mw(one.boundaries.external_region=="ISONE")+587.36)<1e-8);
names(end+1)="char_scenario_subset_preserves_S1_timestamp_total_and_export_sign";
for field=["loads","interfaces","external_records"]
    t=one.(field);
    for k=1:height(t)
        mf=one.source_manifest(one.source_manifest.source_id==t.source_id(k),:);
        raw=readtable(fullfile(root,mf.relative_path),'TextType','string','VariableNamingRule','preserve');
        if field=="loads",value=t.actual_load_mw(k);col="Integrated Load";else,value=t.source_flow_value(k);col="Flow (MWH)";end
        assert(raw.(col)(t.source_csv_line(k)-1)==value);
    end
end
names(end+1)="every_S1_public_value_reextracts_from_its_registered_CSV_line";
expected=one.source_manifest;expected.sha256_lf_normalized(1)="tampered";
reject(@()build_compact_nyiso_snapshot_inputs(struct('scenario_ids',sid,'expected_source_manifest',expected)), ...
    'compact_snapshots:Manifest');
names(end+1)="manifest_drift_is_rejected";
reject(@()build_compact_nyiso_snapshot_inputs(struct('scenario_ids',"S1_2026_UNREGISTERED")), ...
    'compact_snapshots:ScenarioSelection');
reject(@()build_compact_nyiso_snapshot_inputs(struct('scenario_ids',[sid;sid])), ...
    'compact_snapshots:ScenarioSelection');
names(end+1)="unregistered_or_duplicate_scenario_requests_are_rejected";

% Changes to a cache copy must fail the independent pin; production source
% files and archived target tables are not modified by these fixtures.
folder=tempname;mkdir(folder);cleanup=onCleanup(@()cleanup_fixture(folder)); %#ok<NASGU>
cache=fullfile(folder,'cache');mkdir(cache);
for k=1:height(one.source_manifest)
    mf=one.source_manifest(k,:);
    [~,member,ext]=fileparts(mf.relative_path);sub=extractBefore(member,7)+"_"+extractAfter(member,8);
    dest=fullfile(cache,sub);mkdir(dest);
    copyfile(fullfile(root,mf.relative_path),fullfile(dest,member+ext));
    [~,arc,ae]=fileparts(mf.archive_relative_path);
    copyfile(fullfile(root,mf.archive_relative_path),fullfile(dest,arc+ae));
end
path=fullfile(cache,'202507_palIntegrated','20250729palIntegrated.csv');
f=fopen(path,'a');assert(f>=0);fprintf(f,'\n');fclose(f);
reject(@()build_compact_nyiso_snapshot_inputs(struct('scenario_ids',sid,'cache_dir',cache)), ...
    'compact_snapshots:SourceHash');
names(end+1)="changed_daily_source_is_rejected_before_numeric_use";
report=table(names(:),true(numel(names),1),'VariableNames',{'test','passed'});
disp(report);
end

function reject(f,id)
try,f();catch e,assert(strcmp(e.identifier,id),'Unexpected rejection %s: %s',e.identifier,e.message);return;end
error('test_compact_nyiso_snapshot_inputs:MissedGuard','Expected rejection %s',id);
end
function cleanup_fixture(folder)
base=char(java.io.File(tempdir).getCanonicalPath());resolved=char(java.io.File(folder).getCanonicalPath());
assert(startsWith(resolved,[base filesep])&&~strcmp(base,resolved),'test_compact_nyiso_snapshot_inputs:Cleanup','Unsafe fixture cleanup.');
if isfolder(resolved),rmdir(resolved,'s');end
end
