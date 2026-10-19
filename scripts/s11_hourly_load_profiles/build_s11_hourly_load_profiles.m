function report = build_s11_hourly_load_profiles(output_dir)
%BUILD_S11_HOURLY_LOAD_PROFILES Allocate cached hourly NYISO demand to S11.
%   Uses the immutable saved S11 Pd shares, separately in each NYISO zone.
%   Qd is a signed, baseline-compatible constant-power component, not measured
%   reactive demand. Network shunts, dispatch, and boundary schedules are not
%   changed. The six cached months are separate chronological segments.

root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
if nargin < 1 || isempty(output_dir)
    output_dir = fullfile(root, 'output', 's11_hourly_load_profiles');
end
case_dir = fullfile(root, 'System Matpower Format');
helper_dir = fullfile(case_dir, 'NY_Lite');
addpath(case_dir, helper_dir);
base = attach_nyiso_zone_metadata(npcc_ny_lite_s11_dlr_pf_base);
bus_id = base.bus(:, 1);
assert(numel(bus_id) == 49 && numel(unique(bus_id)) == 49, ...
    'Expected the saved 49-bus S11 case.');
base_pd = base.bus(:, 3);
base_qd = base.bus(:, 4);
assert(all(isfinite(base_pd)) && all(base_pd >= 0));
assert(all(isfinite(base_qd)) && all(base_qd(base_pd == 0) == 0), ...
    'A zero-P/nonzero-Q bus requires a separate reactive model.');
zone = string(base.userdata.nyiso_load_allocation_group);
zones = string(('A':'K')');
zone_names = ["WEST"; "GENESE"; "CENTRL"; "NORTH"; "MHK VL"; ...
    "CAPITL"; "HUD VL"; "MILLWD"; "DUNWOD"; "N.Y.C."; "LONGIL"];
ptids = [61752;61753;61754;61755;61756;61757;61758;61759;61760;61761;61762];
assert(all(ismember(zone, zones)), 'Every bus must have a load allocation zone.');
weights = zeros(49, 1);
for z = 1:11
    idx = zone == zones(z);
    assert(sum(base_pd(idx)) > 0, 'Every zone must have positive baseline demand.');
    weights(idx) = base_pd(idx) / sum(base_pd(idx));
end
q_over_p = zeros(49, 1);
q_over_p(base_pd > 0) = base_qd(base_pd > 0) ./ base_pd(base_pd > 0);

months = ["201901"; "201904"; "201907"; "202501"; "202504"; "202507"];
all_utc = NaT(0, 1, 'TimeZone', 'UTC');
all_local = strings(0, 1);
all_tags = strings(0, 1);
zonal_pd = zeros(0, 11);
source_manifest = table();
coverage = table();
source_options = delimitedTextImportOptions('NumVariables',5);
source_options.VariableNamingRule = 'preserve';
source_options.Delimiter = ',';
source_options.DataLines = [2, Inf];
source_options.VariableNames = {'Time Stamp','Time Zone','Name','PTID','Integrated Load'};
source_options.VariableTypes = {'string','string','string','double','double'};
source_options.ExtraColumnsRule = 'error';
source_options.EmptyLineRule = 'error';
for m = 1:numel(months)
    month_id = months(m);
    month_start = datetime(month_id, 'InputFormat', 'yyyyMM');
    days_in_month = eomday(year(month_start), month(month_start));
    expected_hours = 24 * days_in_month;
    segment_start = size(zonal_pd, 1) + 1;
    for d = 1:days_in_month
        day = month_start + days(d - 1);
        day.Format = 'yyyyMMdd';
        relative = fullfile('System Matpower Format', 'NY_Lite', ...
            'nyiso_public_cache', char(month_id + "_palIntegrated"), ...
            char(string(day) + "palIntegrated.csv"));
        filename = fullfile(root, relative);
        assert(isfile(filename), 'Missing source file: %s', filename);
        raw = readtable(filename, source_options);
        assert(height(raw) == 24 * 11, 'Expected 24 hours x 11 zones: %s', relative);
        wall = datetime(raw.("Time Stamp"), 'InputFormat', 'MM/dd/yyyy HH:mm:ss');
        assert(all(dateshift(wall, 'start', 'day') == day));
        assert(all(minute(wall) == 0 & second(wall) == 0));
        tags = string(raw.("Time Zone"));
        assert(all(ismember(tags, ["EST", "EDT"])));
        utc = wall + hours(4 + double(tags == "EST"));
        utc.TimeZone = 'UTC';
        civil = utc;
        civil.TimeZone = 'America/New_York';
        assert(all(isdst(civil) == (tags == "EDT")), 'Timezone tag mismatch.');
        [known, zi] = ismember(raw.Name, zone_names);
        assert(all(known) && all(raw.PTID == ptids(zi)), 'Unknown zone or PTID.');
        values = raw.("Integrated Load");
        assert(all(isfinite(values)) && all(values >= 0), 'Invalid source MW.');
        [times, ~, ti] = unique(utc);
        assert(numel(times) == 24 && all(seconds(diff(times)) == 3600));
        counts = accumarray([ti, zi], 1, [24, 11]);
        assert(all(counts(:) == 1), 'Duplicate or missing source zone-hour.');
        day_pd = accumarray([ti, zi], values, [24, 11]);
        [~, first] = ismember(times, utc);
        local_labels = wall(first);
        local_labels.Format = 'yyyy-MM-dd''T''HH:mm:ss';
        offsets = repmat("-04:00", 24, 1);
        offsets(tags(first) == "EST") = "-05:00";
        all_utc = [all_utc; times]; %#ok<AGROW>
        all_local = [all_local; string(local_labels) + offsets]; %#ok<AGROW>
        all_tags = [all_tags; tags(first)]; %#ok<AGROW>
        zonal_pd = [zonal_pd; day_pd]; %#ok<AGROW>
        row = table(string(strrep(relative, '\', '/')), height(raw), ...
            numel(times), string(day), unique(tags), ...
            'VariableNames', {'source_file','zone_hour_rows','hours', ...
            'local_date','source_time_zone'});
        source_manifest = [source_manifest; row]; %#ok<AGROW>
    end
    segment = segment_start:size(zonal_pd, 1);
    assert(numel(segment) == expected_hours && ...
        all(seconds(diff(all_utc(segment))) == 3600), 'Incomplete month.');
    total = sum(zonal_pd(segment, :), 2);
    row = table(month_id, numel(segment), all_local(segment(1)), ...
        all_local(segment(end)), min(total), max(total), ...
        'VariableNames', {'month','hours','first_local_timestamp', ...
        'last_local_timestamp','minimum_total_pd_mw','maximum_total_pd_mw'});
    coverage = [coverage; row]; %#ok<AGROW>
end
assert(numel(all_utc) == 4416 && numel(unique(all_utc)) == 4416);
assert(all(seconds(diff(all_utc)) > 0), 'Hour order must be strictly increasing.');

pd = zeros(49, numel(all_utc));
zone_error = zeros(11, 1);
for z = 1:11
    idx = zone == zones(z);
    pd(idx, :) = weights(idx) * zonal_pd(:, z)';
    zone_error(z) = max(abs(sum(pd(idx, :), 1)' - zonal_pd(:, z)));
end
qd = pd .* q_over_p;
assert(all(isfinite(pd(:))) && all(pd(:) >= 0) && all(isfinite(qd(:))));
assert(max(zone_error) < 1e-8, 'Zonal active demand was not conserved.');
assert(all(pd(base_pd == 0, :) == 0, 'all'), 'Zero-load buses gained demand.');
total_error = max(abs(sum(pd, 1)' - sum(zonal_pd, 2)));
assert(total_error < 1e-8, 'Statewide demand was not conserved.');
all_utc.Format = 'yyyy-MM-dd''T''HH:mm:ss''Z''';
timestamp_utc = string(all_utc);
baseline_error = max(abs(pd - base_pd), [], 1);
[baseline_max_error, baseline_hour] = min(baseline_error);
assert(baseline_max_error < 1e-4, 'Cached peak should reproduce saved S11 Pd.');

profile = struct();
profile.bus_id = bus_id;
profile.zone = cellstr(zone);
profile.allocation_weight = weights;
profile.base_pd_mw = base_pd;
profile.base_qd_mvar = base_qd;
profile.q_over_p = q_over_p;
profile.base_gs_mw = base.bus(:, 5);
profile.base_bs_mvar = base.bus(:, 6);
profile.pd_mw = pd;
profile.qd_mvar = qd;
profile.timestamp_utc = cellstr(timestamp_utc);
profile.timestamp_local = cellstr(all_local);
profile.source_time_zone = cellstr(all_tags);
profile.zonal_pd_mw = zonal_pd';
profile.zone_order = cellstr(zones);
profile.months = cellstr(months);
profile.array_orientation = 'bus_by_hour';
profile.q_model = 'saved_S11_signed_constant_Q_to_P_ratio';
profile.time_label_convention = 'published_NYISO_hourly_label; interval_start_or_end_not_asserted';
profile.base_case = 'System Matpower Format/npcc_ny_lite_s11_dlr_pf_base.m';
profile.power_flow_validated_all_hours = false;

report = struct('bus_count',49, 'hours',numel(all_utc), ...
    'bus_hour_pairs',numel(pd), 'positive_load_buses',sum(base_pd > 0), ...
    'zero_load_bus_ids',bus_id(base_pd == 0)', 'source_daily_files',height(source_manifest), ...
    'source_zone_hour_rows',sum(source_manifest.zone_hour_rows), ...
    'maximum_zonal_reconciliation_error_mw',max(zone_error), ...
    'maximum_statewide_reconciliation_error_mw',total_error, ...
    'minimum_total_pd_mw',min(sum(pd,1)), 'maximum_total_pd_mw',max(sum(pd,1)), ...
    'baseline_replay_hour_index',baseline_hour, ...
    'baseline_replay_timestamp_utc',char(timestamp_utc(baseline_hour)), ...
    'baseline_replay_maximum_bus_pd_error_mw',baseline_max_error, ...
    'baseline_replay_maximum_bus_qd_error_mvar',max(abs(qd(:,baseline_hour)-base_qd)), ...
    'source_and_allocation_checks_passed',true, ...
    'csv_and_mat_reload_checks_passed',false, ...
    'all_hours_power_flow_validated',false, ...
    'coverage_is_full_year',false);

if ~isfolder(output_dir), mkdir(output_dir); end
time_table = table(timestamp_utc, all_local, all_tags, ...
    'VariableNames', {'timestamp_utc','timestamp_local','source_time_zone'});
bus_columns = cellstr("bus_" + string(bus_id));
writetable([time_table, array2table(pd', 'VariableNames', bus_columns)], ...
    fullfile(output_dir,'pd_mw.csv'));
writetable([time_table, array2table(qd', 'VariableNames', bus_columns)], ...
    fullfile(output_dir,'qd_mvar.csv'));
writetable([time_table, array2table(zonal_pd, 'VariableNames', ...
    cellstr("zone_" + zones))], fullfile(output_dir,'zonal_pd_mw.csv'));
geography = readtable(fullfile(helper_dir,'s11_bus_geography.csv'), 'TextType','string');
[found, loc] = ismember(bus_id, geography.bus_id);
assert(all(found) && numel(unique(geography.bus_id)) == height(geography));
bus_name = geography.bus_name(loc);
allocation = table(bus_id,bus_name,zone,weights,base_pd,base_qd,q_over_p, ...
    base.bus(:,5),base.bus(:,6), ...
    'VariableNames',{'bus_id','bus_name','zone','allocation_weight', ...
    'base_pd_mw','base_qd_mvar','q_over_p','fixed_gs_mw','fixed_bs_mvar'});
writetable(allocation, fullfile(output_dir,'bus_allocation.csv'));
writetable(coverage, fullfile(output_dir,'coverage.csv'));
writetable(source_manifest, fullfile(output_dir,'source_manifest.csv'));
save(fullfile(output_dir,'s11_hourly_load_profiles.mat'), 'profile', '-v7');
loaded = load(fullfile(output_dir,'s11_hourly_load_profiles.mat'), 'profile');
assert(isequaln(loaded.profile, profile), 'MAT round trip changed profile.');
for field = ["pd_mw", "qd_mvar"]
    csv_file = fullfile(output_dir,field + ".csv");
    import_options = detectImportOptions(csv_file, 'TextType','string');
    import_options = setvartype(import_options, 1:3, 'string');
    back = readtable(csv_file, import_options);
    assert(isequal(string(back.timestamp_utc), timestamp_utc));
    assert(isequal(string(back.timestamp_local), all_local));
    assert(isequal(string(back.source_time_zone), all_tags));
    assert(isequal(back.Properties.VariableNames(4:end), bus_columns'));
    values = profile.(field)';
    assert(max(abs(back{:,4:end}-values),[],'all') < 1e-8, 'CSV round-trip error.');
end
report.csv_and_mat_reload_checks_passed = true;
write_text(fullfile(output_dir,'validation.json'), jsonencode(report, PrettyPrint=true));
write_readme(output_dir, report);
disp(jsonencode(report, PrettyPrint=true));
end

function write_text(filename, contents)
fid = fopen(filename, 'w', 'n', 'UTF-8');
assert(fid >= 0, 'Cannot write %s', filename);
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', contents);
end

function write_readme(output_dir, r)
lines = [
"# S11 hourly bus load profiles"
""
"49 buses x 4,416 source hours (216,384 bus-hour pairs). Coverage is January, April, and July of 2019 and 2025. The six monthly segments are complete individually; intervening months and years are not filled or interpolated."
""
"## Files"
""
"- `pd_mw.csv`: hourly constant-power active demand, MW; one column per bus."
"- `qd_mvar.csv`: modeled signed constant-power reactive component, MVAr; one column per bus."
"- `s11_hourly_load_profiles.mat`: `profile` struct; `pd_mw` and `qd_mvar` are 49 x 4416, with rows keyed by `bus_id`."
"- `bus_allocation.csv`: bus names, zones, fixed allocation weights, baseline P/Q, and unchanged GS/BS."
"- `zonal_pd_mw.csv`: the 11 raw NYISO zonal hourly inputs."
"- `coverage.csv`: dates, counts, and statewide load range for each month."
"- `source_manifest.csv`: the 184 local source CSVs and their record counts."
"- `validation.json`: source, allocation, baseline-replay, and round-trip checks."
"- `independent_validation.json`: saved results of the independent Python source-to-output check."
"- `peak_pf_validation.json`: produced by the separate retained-peak AC integration check."
""
"## Allocation and interpretation"
""
"For bus i in load-allocation zone z, w_i = saved_S11_Pd_i / sum(saved_S11_Pd in z), and Pd_i(t) = w_i * NYISO_zonal_load_z(t). Weights are frozen before processing any hour. Raw zonal MW are used, with no gamma scaling or normalization to a constant statewide total. All 49 buses are present; the 21 zero-Pd buses retain zero Pd/Qd, including transit buses 9001, 9002, and 9003."
""
"Qd_i(t) = Pd_i(t) * saved_S11_Qd_i / saved_S11_Pd_i for positive-Pd buses. This preserves the saved case's signed constant-Q component. In this case only bus 80 has nonzero Qd, and its ratio is negative. This is not a measured hourly reactive-demand profile or an assumed 0.95/0.97 power factor. The case's GS/BS network-equivalent shunts are unchanged and excluded from the load arrays; their power depends on voltage."
""
"Bus-level profiles are synthetic allocations of observed zonal demand, not independently measured substation loads. Every bus in a zone therefore has the same normalized active-load shape. The nominal case remains the retained 2025 S11 diagnostic benchmark. These data use the saved case directly and do not depend on the stale 2025 versus 2019 scenario IDs in the snapshot target tables."
""
"Timestamps preserve the published NYISO hourly labels. UTC is derived using each source EST/EDT tag; local labels carry explicit -05:00/-04:00 offsets. No claim is made here about whether the provider's label denotes interval beginning or ending. These timestamps should not be silently relabeled when aligning weather, generation, or boundary schedules."
""
"## Validation and operating scope"
""
string(sprintf('Source checks cover all 184 files, 48,576 zone-hour rows, and 4,416 unique hours. Maximum zonal P error is %.3g MW; maximum statewide P error is %.3g MW.', r.maximum_zonal_reconciliation_error_mw,r.maximum_statewide_reconciliation_error_mw))
""
string(sprintf('The source hour %s reproduces saved S11 active loads within %.3g MW per bus (case serialization precision). CSV and MAT files were reloaded and compared.',r.baseline_replay_timestamp_utc,r.baseline_replay_maximum_bus_pd_error_mw))
""
"This delivery validates the demand allocation. It does not establish AC feasibility for all 4,416 hours. Generation dispatch, external interchange schedules, voltage controls, and any shunt operating policy must be chosen consistently before chronological power-flow/OPF studies. The saved summer-peak dispatch must not be assumed suitable for every hour. S11 retains its reduced-model diagnostic role."
""
"## MATLAB use"
""
"Run from the repository root:"
""
"```matlab"
"addpath('System Matpower Format', 'System Matpower Format/NY_Lite');"
"data = load('output/s11_hourly_load_profiles/s11_hourly_load_profiles.mat');"
"k = 1; % choose an entry in data.profile.timestamp_utc"
"mpc = npcc_ny_lite_s11_dlr_pf_base;"
"mpc = apply_s11_hourly_load_profile(mpc, data.profile, k);"
"% Set consistent hourly generation/boundary conditions before runpf/runopf."
"```"
""
"Regenerate from the existing local source cache:"
""
"```matlab"
"addpath('scripts/s11_hourly_load_profiles');"
"build_s11_hourly_load_profiles;"
"test_apply_s11_hourly_load_profile;"
"validate_s11_hourly_load_profile_integration;"
"```"
""
"Independent source-to-output verification: `python scripts/s11_hourly_load_profiles/verify_s11_hourly_load_profiles.py` (NumPy and SciPy required)."
];
write_text(fullfile(output_dir,'README.md'), strjoin(lines,newline));
end
