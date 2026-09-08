function out=build_compact_nyiso_snapshot_inputs(options)
%BUILD_COMPACT_NYISO_SNAPSHOT_INPUTS Pinned NYISO snapshot evidence, no fitting.
% The 2019/2025 public scenario hours are reconstructed from cached P-58C
% and P-32 CSVs, each checked against a pinned normalized SHA256 and its
% original monthly ZIP member. Historical target tables are never modified.
% Published load and flow values remain separate from benchmark MW. Default
% fixed_year_peak uses one gamma per vintage, preserving seasonal demand.
% per_snapshot_constant_total is an explicit shape-only diagnostic.
% Equal timestamps do not imply equal averaging intervals.
% First four hours per vintage are the training partition; S5/S6 are held
% out. 2019 remains historical validation in the 2025 target campaign.
if nargin<1,options=struct();end
h=fileparts(mfilename('fullpath'));root=fileparts(fileparts(h));
if ~isfield(options,'cache_dir'),options.cache_dir=fullfile(h,'nyiso_public_cache');end
if ~isfield(options,'scenario_ids'),options.scenario_ids=strings(0,1);end
if ~isfield(options,'write_outputs'),options.write_outputs=false;end
if ~isfield(options,'output_dir'),options.output_dir=fullfile(root,'output','compact_nyiso_snapshot_inputs');end
if ~isfield(options,'scale_policy'),options.scale_policy="fixed_year_peak";end
scale_policy=string(options.scale_policy);
assert(isscalar(scale_policy)&&ismember(scale_policy,["fixed_year_peak","per_snapshot_constant_total"]), ...
    'compact_snapshots:ScalePolicy','Use fixed_year_peak or per_snapshot_constant_total.');
power_scale="year_peak_scaled_benchmark_MW";
if scale_policy=="per_snapshot_constant_total",power_scale="shape_normalized_benchmark_MW";end
total=10902.2197987;
[catalog,rejected_pairings]=scenario_catalog(h);
peak_catalog=catalog(catalog.scenario_index==1,:);
requested=string(options.scenario_ids);requested=requested(:);
if ~isempty(requested)
    assert(numel(unique(requested))==numel(requested)&&all(ismember(requested,catalog.scenario_id)), ...
        'compact_snapshots:ScenarioSelection','Only unique, registered scenario IDs are supported.');
    catalog=catalog(ismember(catalog.scenario_id,requested),:);
end
rejected_pairings=rejected_pairings(ismember(rejected_pairings.replacement_scenario_id,catalog.scenario_id),:);
snapshots=table();loads=table();interfaces=table();boundaries=table();external_records=table();
boundary_channels=table();boundary_sensitivity=table();boundary_policy=external_policy;
source_manifest=table();cache=containers.Map('KeyType','char','ValueType','any');
zone_names=["WEST";"GENESE";"CENTRL";"NORTH";"MHK VL";"CAPITL";"HUD VL";"MILLWD";"DUNWOD";"N.Y.C.";"LONGIL"];
zone_letters=string(('A':'K')');
interface_names=["Dysinger_East";"West_Central";"Moses_South";"Central_East";"Total_East_proxy";"UPNY_ConEd";"Dunwoodie_South"];
public_names=["DYSINGER EAST";"WEST CENTRAL";"MOSES SOUTH";"CENTRAL EAST - VC";"TOTAL EAST";"UPNY CONED";"SPR/DUN-SOUTH"];
point_ids=[23326;23312;23319;23330;23314;23315;23320];
zone_boundaries=["A-B";"B-C";"D-E";"E-F";"F-G";"G-H";"I-J"];
primary_names=["SCH - HQ - NY";"SCH - OH - NY";"SCH - NE - NY";"SCH - PJ - NY"];
primary_regions=["HQ";"ONTARIO";"ISONE";"PJM"];
for k=1:height(catalog)
    sc=catalog(k,:);ts=datetime(sc.timestamp,'InputFormat','yyyy-MM-dd HH:mm');
    day=string(ts,'yyyyMMdd');
    data=cell(2,1);sources=cell(2,1);kinds=["palIntegrated","ExternalLimitsFlows"];
    for j=1:2
        key=char(day+kinds(j));
        if isKey(cache,key),pair=cache(key);else
            [tbl,manifest]=source_table(day,kinds(j),options.cache_dir);
            pair={tbl,manifest};cache(key)=pair;source_manifest=[source_manifest;manifest]; %#ok<AGROW>
        end
        data{j}=pair{1};sources{j}=pair{2};
    end
    p58=data{1};p32=data{2};ls=sources{1}.source_id;fs=sources{2}.source_id;
    lt=datetime(p58.("Time Stamp"),'InputFormat','MM/dd/yyyy HH:mm:ss');
    ft=datetime(p32.Timestamp,'InputFormat','MM/dd/yyyy HH:mm');
    lr=find(lt==ts);fr=find(ft==ts);
    assert(numel(lr)==11&&~isempty(fr),'compact_snapshots:ExactTimestamp', ...
        'Exactly 11 zones and exact P-32 timestamp are required for %s.',sc.scenario_id);
    [found,order]=ismember(zone_names,string(p58.Name(lr)));
    assert(all(found)&&numel(unique(order))==11,'compact_snapshots:ZoneIdentity','Missing/duplicate NYISO load zones.');
    lr=lr(order);lp=p58.("Integrated Load")(lr);
    assert(all(isfinite(lp)&lp>=0)&&sum(lp)>0,'compact_snapshots:Load','Invalid published zonal load.');
    assert(abs(sum(lp)-sc.expected_source_total_load_mw)<1e-5,'compact_snapshots:ArchivedTotal', ...
        'Source load total differs from the registered historical scenario.');
    tz=unique(string(p58.("Time Zone")(lr)));
    assert(isscalar(tz)&&ismember(tz,["EST","EDT"]),'compact_snapshots:TimeZone','Ambiguous local source timezone.');
    local=datetime(sc.timestamp,'InputFormat','yyyy-MM-dd HH:mm','TimeZone','America/New_York');
    expected="EST";if isdst(local),expected="EDT";end
    assert(tz==expected,'compact_snapshots:TimeZone','Published timezone contradicts scenario date.');
    local.TimeZone='UTC';utc=string(local,'yyyy-MM-dd''T''HH:mm:ss''Z''');
    scale_ref=sc;scale_source_id=ls;scale_reference_load=sum(lp);
    if scale_policy=="fixed_year_peak"
        scale_ref=peak_catalog(peak_catalog.vintage==sc.vintage,:);
        assert(height(scale_ref)==1,'compact_snapshots:ScaleReference','Exactly one registered summer peak is required.');
        scale_day=string(datetime(scale_ref.timestamp,'InputFormat','yyyy-MM-dd HH:mm'),'yyyyMMdd');
        scale_key=char(scale_day+"palIntegrated");
        if isKey(cache,scale_key),scale_pair=cache(scale_key);else
            [scale_tbl,scale_manifest]=source_table(scale_day,"palIntegrated",options.cache_dir);
            scale_pair={scale_tbl,scale_manifest};cache(scale_key)=scale_pair;
            source_manifest=[source_manifest;scale_manifest]; %#ok<AGROW>
        end
        scale_tbl=scale_pair{1};scale_source_id=scale_pair{2}.source_id;
        scale_rows=datetime(scale_tbl.("Time Stamp"),'InputFormat','MM/dd/yyyy HH:mm:ss')== ...
            datetime(scale_ref.timestamp,'InputFormat','yyyy-MM-dd HH:mm');
        scale_values=scale_tbl.("Integrated Load")(scale_rows);
        assert(nnz(scale_rows)==11&&numel(unique(string(scale_tbl.Name(scale_rows))))==11 ...
            &&all(ismember(zone_names,string(scale_tbl.Name(scale_rows)))) ...
            &&all(isfinite(scale_values)&scale_values>=0) ...
            &&abs(sum(scale_values)-scale_ref.expected_source_total_load_mw)<1e-5, ...
            'compact_snapshots:ScaleReference','Pinned peak reference must contain all 11 expected source loads.');
        scale_reference_load=sum(scale_values);
    end
    gamma=total/scale_reference_load;split="training";if sc.scenario_index>=5,split="heldout";end
    campaign="historical_validation";if sc.vintage==2025,campaign="2025_target";end
    fit_allowed=split=="training"&&sc.vintage==2025;
    ss=table(sc.scenario_id,sc.vintage,sc.scenario_index,sc.timestamp,utc,tz,split,campaign, ...
        sum(lp),gamma*sum(lp),gamma,ls,fs,false,false,false, ...
        "same_published_hour_label_hourly_load_and_five_minute_flow", ...
        'VariableNames',{'scenario_id','vintage','scenario_index','timestamp','timestamp_utc','source_time_zone', ...
        'dataset_split','campaign_role','actual_total_load_mw','benchmark_total_load_mw','scale_factor_gamma', ...
        'load_source_id','p32_source_id','zonal_generation_observed','boundary_q_observed', ...
        'sampling_intervals_equal','temporal_policy'});
    ss.default_campaign_interface_fit_allowed=fit_allowed;
    ss.scale_policy=scale_policy;ss.scale_reference_scenario_id=scale_ref.scenario_id;
    ss.scale_reference_timestamp=scale_ref.timestamp;ss.scale_reference_source_id=scale_source_id;
    ss.scale_reference_actual_load_mw=scale_reference_load;ss.benchmark_peak_load_mw=total;
    ss.interface_timestamp=sc.timestamp;ss.boundary_timestamp=sc.timestamp;ss.exact_timestamp_match=true;
    ss.replacement_for_scenario_id=sc.replacement_for_scenario_id;
    ss.source_selection_basis=sc.selection_basis;snapshots=[snapshots;ss]; %#ok<AGROW>
    l=table(zone_letters,zone_names,lp,gamma*lp,lp/sum(lp),nan(11,1),nan(11,1),lr+1, ...
        'VariableNames',{'zone','zone_name','actual_load_mw','target_load_mw','load_share', ...
        'actual_load_q_mvar','target_load_q_mvar','source_csv_line'});
    l=metadata(l,ss,ls,"operating_input");
    l.source_field=repmat("Integrated Load",11,1);l.actual_unit=repmat("MW",11,1);
    l.model_power_scale=repmat(power_scale,11,1);loads=[loads;l]; %#ok<AGROW>

    % Point identities are part of the source join; CSV row order is not.
    hour_names=string(p32.("Interface Name")(fr));
    assert(numel(unique(hour_names))==numel(hour_names),'compact_snapshots:DuplicateP32','Duplicate P-32 interface at the selected timestamp.');
    [found,order]=ismember(public_names,hour_names);
    assert(all(found),'compact_snapshots:InterfaceMissing','A registered internal interface is missing.');
    ir=fr(order);
    assert(isequal(p32.("Point ID")(ir),point_ids),'compact_snapshots:PointIdentity','Internal interface Point ID changed.');
    t=flow_rows(p32,ir);
    t.interface_name=interface_names;t.public_interface_name=public_names;t.zone_boundary=zone_boundaries;
    t.actual_flow_mw=t.source_flow_value;t.target_flow_mw=gamma*t.actual_flow_mw;
    t=scale_limits(t,gamma);
    role="training_target";if split=="heldout",role="heldout_validation_target";end
    if sc.vintage==2019,role="historical_validation_target";end
    t=metadata(t,ss,fs,role);t.training_target=repmat(fit_allowed,height(t),1);
    t.partition_training=repmat(split=="training",height(t),1);
    t.model_operator_qualification=repmat("public_observation_model_proxy_mapping_separate",height(t),1);
    interfaces=[interfaces;t]; %#ok<AGROW>

    er=fr(startsWith(hour_names,"SCH - "));
    e=flow_rows(p32,er);e.public_interface_name=string(p32.("Interface Name")(er));
    e.actual_import_mw=e.source_flow_value;e.target_import_mw=gamma*e.actual_import_mw;
    e.actual_q_mvar=nan(height(e),1);e.target_q_mvar=nan(height(e),1);
    e=scale_limits(e,gamma);e=metadata(e,ss,fs,"operating_input");
    e.direction_positive=repmat("into_NY_per_published_interface_orientation",height(e),1);
    e.quantity_scope=repmat("P32_SCH_labelled_interface_flow_not_terminal_PQ",height(e),1);
    e.coverage_role=repmat("additional_controllable_interface",height(e),1);
    [is_primary,pi]=ismember(e.public_interface_name,primary_names);
    e.coverage_role(is_primary)="primary_interregional_interface";
    e.coverage_role(e.public_interface_name=="SCH - HQ_CEDARS")="additional_Cedars_interface";
    e.coverage_role(e.public_interface_name=="SCH - HQ_IMPORT_EXPORT")="excluded_nonadditive_HQ_net_market_report";
    e.default_primary_scope=is_primary;
    e.include_in_unreviewed_total=false(height(e),1);
    e.overlap_resolved=e.public_interface_name~="SCH - HQ_IMPORT_EXPORT";
    [found,policy_row]=ismember(e.public_interface_name,boundary_policy.public_interface_name);
    assert(all(found)&&numel(unique(policy_row))==11&&height(e)==11, ...
        'compact_snapshots:ExternalPolicy','Every raw external channel needs an explicit nonoverlapping policy.');
    assert(isequal(e.point_id,boundary_policy.point_id(policy_row)), ...
        'compact_snapshots:PointIdentity','External interface Point ID changed.');
    e.default_channel_include=boundary_policy.default_channel_include(policy_row);
    e.accounting_policy=boundary_policy.accounting_policy(policy_row);
    e.accounting_evidence_url=boundary_policy.evidence_url(policy_row);
    e.external_region=repmat("UNALLOCATED_COMPONENT",height(e),1);
    e.external_region(is_primary)=primary_regions(pi(is_primary));
    external_records=[external_records;e]; %#ok<AGROW>
    channels=e(e.default_channel_include,:);
    channels.accounting_scope=repmat("ten_distinct_P32_channels_HQ_net_subreport_excluded",height(channels),1);
    boundary_channels=[boundary_channels;channels]; %#ok<AGROW>
    if sc.scenario_id=="S1_2025_SUMMER_PEAK_PUBLIC"
        hq=e(e.public_interface_name=="SCH - HQ - NY",:);
        nested=e(e.public_interface_name=="SCH - HQ_IMPORT_EXPORT",:);
        delta=nested.actual_import_mw-hq.actual_import_mw;
        boundary_sensitivity=table(sc.scenario_id,sc.timestamp, ...
            hq.actual_import_mw,nested.actual_import_mw,delta,gamma*delta, ...
            sum(channels.actual_import_mw),sum(channels.actual_import_mw)+delta, ...
            sum(channels.target_import_mw),sum(channels.target_import_mw)+gamma*delta, ...
            "replace_HQ_NY_with_HQ_IMPORT_EXPORT_do_not_add_both",false, ...
            'VariableNames',{'scenario_id','timestamp','default_HQ_actual_mw','alternative_HQ_actual_mw', ...
            'actual_import_change_mw','benchmark_import_change_mw','default_total_actual_import_mw', ...
            'alternative_total_actual_import_mw','default_total_benchmark_import_mw', ...
            'alternative_total_benchmark_import_mw','alternative_policy','electrical_sensitivity_solved'});
    end
    [found,bi]=ismember(primary_names,e.public_interface_name);
    assert(all(found),'compact_snapshots:BoundaryMissing','A primary external interface is missing.');
    b=e(bi,:);b.accounting_scope=repmat("four_primary_interfaces_additional_components_excluded",4,1);
    b.complete_external_interchange=false(4,1);boundaries=[boundaries;b]; %#ok<AGROW>
end
% No generation observations or estimated Q are inferred from interface fits.
generation_observations=loads(:,{'scenario_id','timestamp','timestamp_utc','vintage','zone','dataset_split','campaign_role'});
generation_observations.actual_generation_mw=nan(height(generation_observations),1);
generation_observations.provenance_class=repmat("missing_public_zonal_generation_observation",height(generation_observations),1);
generation_observations.target_use=repmat("unavailable_not_a_fit_target",height(generation_observations),1);
if isfield(options,'expected_source_manifest')
    assert(isequaln(source_manifest,options.expected_source_manifest),'compact_snapshots:Manifest', ...
        'Rebuilt source manifest differs from the frozen input manifest.');
end
out=struct('snapshots',snapshots,'loads',loads,'interfaces',interfaces,'boundaries',boundaries, ...
    'external_records',external_records,'source_manifest',source_manifest, ...
    'boundary_channels',boundary_channels,'boundary_policy',boundary_policy, ...
    'boundary_sensitivity',boundary_sensitivity, ...
    'rejected_pairings',rejected_pairings, ...
    'generation_observations',generation_observations, ...
    'benchmark_peak_load_mw',total,'power_scale',power_scale,'scale_policy',scale_policy, ...
    'actual_MW_operating_model',false,'source_parameter_fit_performed',false, ...
    'zonal_generation_observations_available',false,'boundary_reactive_observations_available',false, ...
    'complete_external_interchange_established',false,'heldout_interface_fit_allowed',false, ...
    'all_p32_external_records_accounted',true, ...
    'historical_tables_modified',false,'thermal_model_implemented',false,'dlr_ready',false);
if options.write_outputs
    if ~isfolder(options.output_dir),mkdir(options.output_dir);end
    for name=["snapshots","loads","interfaces","boundaries","external_records","source_manifest", ...
            "generation_observations","rejected_pairings","boundary_channels","boundary_policy","boundary_sensitivity"]
        ny_lite_writetable_lf(out.(name),fullfile(options.output_dir,"compact_nyiso_"+name+".csv"));
    end
end

function p=external_policy
name=["SCH - HQ - NY";"SCH - HQ_CEDARS";"SCH - HQ_IMPORT_EXPORT";"SCH - NE - NY"; ...
    "SCH - NPX_1385";"SCH - NPX_CSC";"SCH - OH - NY";"SCH - PJ - NY"; ...
    "SCH - PJM_HTP";"SCH - PJM_NEPTUNE";"SCH - PJM_VFT"];
point=[23324;325274;325376;23318;325277;325154;23317;23316;325905;325305;325658];
include=true(11,1);include(3)=false;
policy=repmat("include_distinct_additional_or_primary_P32_channel",11,1);
policy(1)="include_gross_Chateauguay_interface_with_wheel_throughs";
policy(2)="include_separate_Cedars_interface";
policy(3)="exclude_nested_HQ_import_export_reporting_scope_never_sum_with_HQ_NY";
url=repmat("https://www.nyiso.com/documents/20142/2926255/2010Report_NYISO_2011-08-02_NMB.pdf/b532cb34-64b9-86e7-f794-25870de8d717",11,1);
url([1 3])="https://www.nyiso.com/documents/20142/1409680/Seams_Closed.pdf/e523b0d3-907c-e7a6-fe27-628875cfafad";
url(2)="https://eta-publications.lbl.gov/sites/default/files/assessment-of-historic-transmission-schedules-and-flows-2014.pdf";
url(9)="https://www.nyiso.com/documents/20142/1407325/Constraint%20Reliability%20Margin%20CRM.pdf/b9de3cb5-855a-ca32-b66e-86c6933c88ef";
confidence=repmat("distinct_named_public_interface_with_declared_landing_approximation",11,1);
confidence([1 3])="inference_from_dual_HQ_proxy_documentation_exact_reporting_algebra_unresolved";
p=table(name,point,include,policy,url,confidence,false(11,1), ...
    'VariableNames',{'public_interface_name','point_id','default_channel_include','accounting_policy', ...
    'evidence_url','evidence_scope','terminal_PQ_observed'});
end
end

function t=metadata(t,s,source_id,use)
n=height(t);t.scenario_id=repmat(s.scenario_id,n,1);t.timestamp=repmat(s.timestamp,n,1);
t.timestamp_utc=repmat(s.timestamp_utc,n,1);t.vintage=repmat(s.vintage,n,1);
t.dataset_split=repmat(s.dataset_split,n,1);t.campaign_role=repmat(s.campaign_role,n,1);
t.scale_factor_gamma=repmat(s.scale_factor_gamma,n,1);t.source_id=repmat(source_id,n,1);
t.scale_policy=repmat(s.scale_policy,n,1);t.scale_reference_scenario_id=repmat(s.scale_reference_scenario_id,n,1);
t.scale_reference_source_id=repmat(s.scale_reference_source_id,n,1);
t.target_use=repmat(use,n,1);t.provenance_class=repmat("source_verified_public_record",n,1);
end

function t=flow_rows(p,rows)
t=table(p.("Point ID")(rows),p.("Flow (MWH)")(rows),p.("Positive Limit (MWH)")(rows), ...
    p.("Negative Limit (MWH)")(rows),rows+1,'VariableNames',{'point_id','source_flow_value', ...
    'actual_positive_limit_mw','actual_negative_limit_mw','source_csv_line'});
assert(all(isfinite(t.source_flow_value))&&all(isfinite(t.point_id)), ...
    'compact_snapshots:Flow','Nonfinite published flow or Point ID.');
t.source_field=repmat("Flow (MWH)",height(t),1);
t.unit_interpretation=repmat("published_interface_power_as_MW_raw_MWH_header_preserved_no_energy_conversion",height(t),1);
t.source_limit_is_equipment_rating=false(height(t),1);
end

function t=scale_limits(t,gamma)
t.target_positive_limit_mw=gamma*t.actual_positive_limit_mw;
t.target_negative_limit_mw=gamma*t.actual_negative_limit_mw;
t.actual_limit_mw=t.actual_positive_limit_mw;
negative=t.source_flow_value<0;t.actual_limit_mw(negative)=abs(t.actual_negative_limit_mw(negative));
t.target_limit_mw=gamma*t.actual_limit_mw;
t.directional_limit_is_placeholder=abs(t.actual_limit_mw)>=9999;
end

function [c,rejected]=scenario_catalog(h)
names=["SUMMER_PEAK_PUBLIC";"WINTER_PEAK_PUBLIC";"SHOULDER_LIGHT_LOAD_PUBLIC"; ...
    "HIGH_NYC_LI_LOAD_PUBLIC";"HIGH_TOTAL_EAST_PUBLIC";"LOW_TOTAL_EAST_PUBLIC"];
dates=["2019-07-20 16:00";"2019-01-21 18:00";"2019-04-21 04:00"; ...
    "2019-07-17 16:00";"2019-07-17 08:00";"2019-07-27 02:00"; ...
    "2025-07-29 18:00";"2025-01-22 18:00";"2025-04-20 14:00"; ...
    "2025-07-29 17:00";"2025-07-17 16:00";"2025-07-27 17:00"];
c=table();paths=[string(fullfile(h,'nyiso_public_scenarios.csv')); ...
    string(fullfile(h,'archives','targets_2025_scaled_backup','nyiso_public_scenarios.csv'))];
for k=1:2
    vintage=[2019 2025];year=vintage(k);
    seed=readtable(paths(k),'TextType','string');
    ids="S"+string((1:6)')+"_"+string(year)+"_"+names;
    [found,j]=ismember(ids,string(seed.scenario_id));
    assert(all(found)&&numel(unique(j))==6,'compact_snapshots:Catalog','Historical scenario registry changed.');
    seed=seed(j,:);stamp=string(seed.timestamp);
    assert(isequal(stamp,dates((k-1)*6+(1:6))),'compact_snapshots:Catalog','Registered exact scenario timestamps changed.');
    c=[c;table(ids,repmat(year,6,1),(1:6)',stamp,seed.nyiso_total_load_mw,string(seed.notes), ...
        'VariableNames',{'scenario_id','vintage','scenario_index','timestamp','expected_source_total_load_mw','selection_basis'})]; %#ok<AGROW>
end
c.replacement_for_scenario_id=repmat("",height(c),1);
% The archived 2025 shoulder selection paired the 14:00 hourly load with
% 14:03 P-32. Keep that exclusion explicit. Of the immediately adjacent exact
% common hours, 13:00 has lower load (11083.2248) than 15:00 (11230.3445 MW).
old="S3_2025_SHOULDER_LIGHT_LOAD_PUBLIC";replacement="S3_2025_SHOULDER_LIGHT_LOAD_EXACT";
at=c.scenario_id==old;assert(nnz(at)==1);
c.scenario_id(at)=replacement;c.timestamp(at)="2025-04-20 13:00";
c.expected_source_total_load_mw(at)=11083.2248;c.replacement_for_scenario_id(at)=old;
c.selection_basis(at)="explicit_replacement_nearest_exact_common_hour_lower_load_than_15_00_not_monthly_minimum";
rejected=table(old,"2025-04-20 14:00","2025-04-20 14:03",3,11060.559, ...
    10902.2197987/11060.559,false,false,false,"NYISO:P58C:20250420","NYISO:P32:20250420", ...
    replacement,"2025-04-20 13:00", ...
    "archived_three_minute_offset_no_exact_P32_row_at_load_timestamp", ...
    'VariableNames',{'scenario_id','load_timestamp','interface_timestamp','offset_minutes', ...
    'actual_total_load_mw','archived_gamma','exact_timestamp_match','use_for_calibration', ...
    'use_for_validation','load_source_id','p32_source_id','replacement_scenario_id', ...
    'replacement_timestamp','exclusion_reason'});
end

function [t,m]=source_table(day,kind,cache_dir)
member=day+kind+".csv";month=extractBefore(day,7);sub=month+"_"+kind;
archive=month+"01"+kind+"_csv.zip";file=fullfile(cache_dir,sub,member);zip_path=fullfile(cache_dir,sub,archive);
assert(isfile(file)&&isfile(zip_path),'compact_snapshots:SourceMissing','Pinned CSV or monthly ZIP is missing: %s',member);
raw=read_bytes(file);sha=sha_lf(raw);pin=pinned_hashes;
idx=find(pin(:,1)==member);assert(isscalar(idx)&&sha==pin(idx,2), ...
    'compact_snapshots:SourceHash','Pinned NYISO daily source changed: %s',member);
z=java.util.zip.ZipFile(char(zip_path));close_zip=onCleanup(@()z.close()); %#ok<NASGU>
entries=z.entries();matches={};
while entries.hasMoreElements()
    e=entries.nextElement();[~,name,ext]=fileparts(char(e.getName()));
    if string(name)+string(ext)==member,matches{end+1}=e;end %#ok<AGROW>
end
assert(numel(matches)==1,'compact_snapshots:ArchiveMember','Daily member is absent or duplicated in the monthly ZIP.');
stream=z.getInputStream(matches{1});close_stream=onCleanup(@()stream.close()); %#ok<NASGU>
scan=java.util.Scanner(stream,'UTF-8');scan.useDelimiter('\A');
assert(scan.hasNext(),'compact_snapshots:ArchiveMember','Empty archived CSV member.');
bytes=unicode2native(char(scan.next()),'UTF-8');
assert(sha_lf(bytes)==sha,'compact_snapshots:ArchiveMismatch','Cached daily CSV differs from its archived member.');
t=readtable(file,'TextType','string','VariableNamingRule','preserve');
role="P58C_hourly_integrated_zonal_load";code="P58C";
if kind=="ExternalLimitsFlows",role="P32_five_minute_interface_flow";code="P32";end
relative="System Matpower Format/NY_Lite/nyiso_public_cache/"+sub+"/";
m=table("NYISO:"+code+":"+day,relative+member, ...
    "https://mis.nyiso.com/public/csv/"+kind+"/"+archive,sha,relative+archive, ...
    ny_reference_file_sha256(zip_path),string(matches{1}.getName()),true,role, ...
    'VariableNames',{'source_id','relative_path','source_uri','sha256_lf_normalized', ...
    'archive_relative_path','archive_sha256','archive_member','daily_archive_match','source_data_class'});
end

function b=read_bytes(path)
f=fopen(path,'rb');assert(f>=0,'compact_snapshots:Read','Cannot open source.');cl=onCleanup(@()fclose(f)); %#ok<NASGU>
b=fread(f,Inf,'*uint8');
end
function hash=sha_lf(bytes)
txt=native2unicode(bytes(:)','UTF-8');txt=strrep(strrep(txt,sprintf('\r\n'),sprintf('\n')),sprintf('\r'),sprintf('\n'));
md=java.security.MessageDigest.getInstance('SHA-256');md.update(unicode2native(txt,'UTF-8'));
hash=string(lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2)',1,[])));
end
function p=pinned_hashes
% Normalized daily-file hashes verified against committed original ZIPs.
p=["20190720palIntegrated.csv" "78023e6015dd393a247551d663c53cbc7ea01d330e21160a2fe853d4e9d0c551"; ...
"20190720ExternalLimitsFlows.csv" "8656ef12ab30ea5714fe4d2cd93743e133b3a8c5dcf1245099f93e89868718f2"; ...
"20190121palIntegrated.csv" "73d09fb0f888420c6685d0b748c040e944c60cbbefd15d8987e5aa31326f5be5"; ...
"20190121ExternalLimitsFlows.csv" "555f403dea70f27217ea4b81e09a91962ca654e792acbe0d487957e92e8ccf1a"; ...
"20190421palIntegrated.csv" "dba7e63fbfb0d65eb09cb317bcf31537c2cf98ca76db1ff2d94a7ed1e9e34a76"; ...
"20190421ExternalLimitsFlows.csv" "083a4ffd279064d215c5e361d9a9474eb73e56bd7eba1a8f02d21303e350fd4e"; ...
"20190717palIntegrated.csv" "c054627a7bdfda1828dc5db559cda7a0ffbcda26ca9e778a3e7f6b11fe08a595"; ...
"20190717ExternalLimitsFlows.csv" "5bdc210c3b7fb1804388bb2d59b1e6e9ad8687b85438fdb75923f7a9215c64a1"; ...
"20190727palIntegrated.csv" "815be83d3bb93b82aa28024ee0c7e98943d0029a900ff0d83b952d7c9460a6c0"; ...
"20190727ExternalLimitsFlows.csv" "31468e3078f6fd83df07ebd98f4daca2f51ffa0b70aeba0d15aff5b0882d6e06"; ...
"20250729palIntegrated.csv" "596e92ccd9b60d2c5c35da21dbf33b5dbbf3243be6f317fae8061ed58b9557c8"; ...
"20250729ExternalLimitsFlows.csv" "ed4d1b490d6013d340b14e2cc0cc7528878ad9bf89995212c1b593a54ade21ae"; ...
"20250122palIntegrated.csv" "87f2f95d41cc5eb7c609170d98c533318d33988d58b7e6afb50f971aec67b281"; ...
"20250122ExternalLimitsFlows.csv" "c57d47f1c3999ca43148359683b345857ddfcac4b3a20952e84298b04523b640"; ...
"20250420palIntegrated.csv" "4b84fbfe0983de06956c6160c0fcad0e163ac6916ea0571d53417b6f893cf745"; ...
"20250420ExternalLimitsFlows.csv" "245ec16502ff7c6f0449d2c59f7c4f5e85f5c15a0a30d855c2072d5cd69a73a7"; ...
"20250717palIntegrated.csv" "3f61295f256114edef9158e9db1aa7f267ccef6cb9172397981540d4a26bf888"; ...
"20250717ExternalLimitsFlows.csv" "e1753d0b2b02650a87cc6079b595524431b101bd7806b46139b5f1b2d1be5e44"; ...
"20250727palIntegrated.csv" "851ae7e1c326ca1bf57e64a80927bfafc17c74238be13778e10d6c11400eecf9"; ...
"20250727ExternalLimitsFlows.csv" "256ecb5215442154dfc72a58bbf8ee2d8889640d0de5b7e53e45340e581d2533"];
end
