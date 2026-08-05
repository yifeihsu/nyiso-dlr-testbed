function outputs = build_perform_control_preserving_mapping(options)
%BUILD_PERFORM_CONTROL_PRESERVING_MAPPING Map PERFORM controls into S7 proxies.
%   This is a source-backed S10a diagnostic mapping. Plant/GSK rules assign
%   active devices, while a Ward effective-impedance metric assigns
%   reactive-only devices and the one remote regulated-bus relationship.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
workspace_dir = fileparts(case_dir);
options = defaults(options, helper_dir, workspace_dir);
addpath(case_dir); addpath(helper_dir); addpath(options.perform_case_dir);
define_constants;

s7 = attach_nyiso_zone_metadata(loadcase(options.structural_case));
source = nyiso_On_Peak_v23_shunts_as_z_load;
pfopt = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 1);
source_pf = runpf(source, pfopt);
if ~source_pf.success
    error('The PERFORM 2019 source case did not converge with Q limits enforced.');
end

reference_outputs = build_ny_voltage_reference_sets;
controls = reference_outputs.perform_controls;
mapping = readtable(fullfile(options.perform_aux_dir, ...
    'internal_NYISO_MOD2MAP.xlsx'), 'Sheet', 'BUS SUB', ...
    'VariableNamingRule', 'preserve');
cost_meta = readtable(fullfile(options.perform_case_dir, ...
    'GenCostTable4MATPOWERv23_ShuntsNotShown.csv'), ...
    'VariableNamingRule', 'preserve');
unit_meta = readtable(fullfile(options.perform_aux_dir, 'NYGenUCV4.xlsx'), ...
    'VariableNamingRule', 'preserve');

controls.source_plant_name = control_plant_names(controls, cost_meta, unit_meta);
controls.source_fuel = controls.converted_genfuel;
candidates = retained_candidates(s7);

[device_bus, device_method, device_confidence] = ...
    assign_active_device_buses(controls, candidates);
controls.retained_device_bus = device_bus;

query_buses = unique([controls.source_bus; controls.regulated_bus]);
ward = ward_context(source_pf, query_buses);
anchors = anchor_table(controls, candidates);

needs_ward_device = controls.mapped_to_nyiso_zone & ...
    (controls.reactive_only_QS | ~isfinite(controls.retained_device_bus));
for k = find(needs_ward_device(:))'
    [bus_id, distance] = nearest_retained_proxy(controls.source_bus(k), ...
        controls.source_zone(k), anchors, candidates, ward);
    controls.retained_device_bus(k) = bus_id;
    device_method(k) = "Ward effective-impedance match to source control anchors";
    if isfinite(distance)
        device_confidence(k) = "medium";
    else
        device_confidence(k) = "low";
    end
end
device_bus = controls.retained_device_bus;

pilot_bus = controls.retained_device_bus;
pilot_method = repmat("local source regulation aggregated at device proxy", ...
    height(controls), 1);
for k = find(controls.remote_regulation & controls.mapped_to_nyiso_zone)'
    [bus_id, distance] = nearest_retained_proxy(controls.regulated_bus(k), ...
        controls.regulated_zone(k), anchors, candidates, ward);
    pilot_bus(k) = bus_id;
    pilot_method(k) = "remote IREG mapped by Ward effective impedance";
    if ~isfinite(distance)
        device_confidence(k) = "low";
    end
end

reduced_type = reduced_device_types(controls);
reduced_group_id = "BUS_" + string(device_bus) + "__PILOT_" + ...
    string(pilot_bus) + "__" + upper(reduced_type);
reduced_group_id(~isfinite(device_bus) | ~isfinite(pilot_bus)) = "UNMAPPED";
q_participation = q_participation_factors(controls, reduced_group_id);
mapping_method = device_method + "; " + pilot_method;

control_map = table(controls.source_bus, controls.generator_id, ...
    controls.source_bus_name, controls.source_zone, controls.source_plant_name, ...
    controls.source_fuel, controls.device_class, controls.regulated_bus, ...
    controls.regulated_bus_name, controls.regulated_zone, ...
    controls.voltage_target_pu, controls.qmin_mvar, controls.qmax_mvar, ...
    controls.pg_mw, controls.qg_mvar, controls.pmin_mw, controls.pmax_mw, ...
    device_bus, pilot_bus, reduced_type, q_participation, controls.status, ...
    controls.converted_status, controls.snapshot_effective_status, ...
    controls.raw_converted_status_mismatch, ...
    controls.remote_regulation, controls.converted_gen_index, ...
    reduced_group_id, mapping_method, device_method, pilot_method, ...
    device_confidence, controls.classification_confidence, ...
    'VariableNames', {'source_bus','source_generator_id','source_bus_name', ...
    'source_zone','source_plant_name','source_fuel','device_class', ...
    'source_regulated_bus','source_regulated_bus_name','regulated_zone', ...
    'source_VS','source_QMIN','source_QMAX','source_PG','source_QG', ...
    'source_PMIN','source_PMAX','retained_device_bus','retained_pilot_bus', ...
    'reduced_device_type','q_participation_factor','status', ...
    'converted_status','snapshot_effective_status','raw_converted_status_mismatch', ...
    'remote_regulation','converted_gen_index','reduced_control_group_id', ...
    'mapping_method','device_mapping_method','pilot_mapping_method', ...
    'mapping_confidence','classification_confidence'});

groups = aggregate_control_groups(control_map, source_pf);
pq_audit = audit_pq_skipped_buses(s7, control_map);
[discrete_summary, discrete_detail] = discrete_control_inventory( ...
    source_pf, control_map, candidates, anchors, ward, mapping, options);
anchor_report = summarize_anchors(anchors, candidates);

writetable(control_map, options.control_mapping_file);
writetable(groups, options.control_group_file);
writetable(pq_audit, options.pq_audit_file);
writetable(discrete_summary, options.discrete_summary_file);
writetable(discrete_detail, options.discrete_detail_file);
writetable(anchor_report, options.anchor_file);

outputs = struct('control_mapping_file', options.control_mapping_file, ...
    'control_group_file', options.control_group_file, ...
    'pq_audit_file', options.pq_audit_file, ...
    'discrete_summary_file', options.discrete_summary_file, ...
    'discrete_detail_file', options.discrete_detail_file, ...
    'anchor_file', options.anchor_file, 'control_mapping', control_map, ...
    'control_groups', groups, 'pq_audit', pq_audit, ...
    'discrete_summary', discrete_summary, 'discrete_detail', discrete_detail, ...
    'anchors', anchor_report, 'source_case', source, 'source_pf', source_pf);
end

function options = defaults(options, helper_dir, workspace_dir)
items = { ...
    'structural_case', 'npcc_ny_lite_s7_seven_interface_perform_direct_candidate'; ...
    'perform_case_dir', fullfile(workspace_dir, 'PERFORM', ...
        'On Peak 2019 v23_Perform_NY', 'On Peak 2019 v23'); ...
    'perform_aux_dir', fullfile(workspace_dir, 'PERFORM', 'Auxilliary_Perform_NY'); ...
    'perform_raw_file', fullfile(workspace_dir, 'PERFORM', ...
        'On Peak 2019 v23_Perform_NY', 'On Peak 2019 v23', ...
        'NYISO_onpeak2019_v23_shuntsRgens.RAW'); ...
    'control_mapping_file', fullfile(helper_dir, 'perform_source_to_reduced_control_mapping.csv'); ...
    'control_group_file', fullfile(helper_dir, 'perform_reduced_control_groups.csv'); ...
    'pq_audit_file', fullfile(helper_dir, 'perform_pq_skipped_reference_audit.csv'); ...
    'discrete_summary_file', fullfile(helper_dir, 'perform_discrete_control_summary.csv'); ...
    'discrete_detail_file', fullfile(helper_dir, 'perform_discrete_control_mapping.csv'); ...
    'anchor_file', fullfile(helper_dir, 'perform_retained_control_anchors.csv')};
for k = 1:size(items, 1)
    if ~isfield(options, items{k, 1}), options.(items{k, 1}) = items{k, 2}; end
end
end

function names = control_plant_names(controls, cost_meta, unit_meta)
names = repmat("", height(controls), 1);
cost_codes = double(cost_meta.EIAPlantCode);
unit_codes = double(unit_meta.PlantCode);
unit_names = string(unit_meta.PlantName);
for k = 1:height(controls)
    gi = controls.converted_gen_index(k);
    if ~isfinite(gi), continue; end
    code = cost_codes(gi);
    idx = find(unit_codes == code, 1);
    if isempty(idx)
        names(k) = "UNMAPPED_" + string(code);
    else
        names(k) = strtrim(unit_names(idx));
    end
end
end

function candidates = retained_candidates(s7)
define_constants;
bus_ids = [37;38;39;41;42;43;44;47;48;50;51;53;54;55;56;57;60;61; ...
    65;68;71;72;73;75;76;78;79;80;81;82;9003];
rows = table();
for k = 1:numel(bus_ids)
    bi = find(s7.bus(:, BUS_I) == bus_ids(k), 1);
    if isempty(bi), continue; end
    gi = s7.gen(:, GEN_STATUS) > 0 & s7.gen(:, GEN_BUS) == bus_ids(k);
    pmax = sum(s7.gen(gi, PMAX));
    if pmax <= 0, pmax = 100; end
    row = table(bus_ids(k), string(strtrim(s7.bus_name{bi})), ...
        string(s7.userdata.nyiso_physical_zone{bi}), s7.bus(bi, BUS_TYPE), ...
        pmax, 'VariableNames', {'retained_bus','retained_bus_name','zone', ...
        's7_bus_type','s7_pmax_mw'});
    rows = append_table(rows, row);
end
candidates = rows;
end

function [device_bus, method, confidence] = ...
        assign_active_device_buses(controls, candidates)
n = height(controls);
device_bus = nan(n, 1);
method = repmat("unmapped pending electrical assignment", n, 1);
confidence = repmat("low", n, 1);
assigned = zeros(height(candidates), 1);
priority = controls.snapshot_effective_status * 1e9 + max(controls.pmax_mw, 0);
[~, order] = sort(priority, 'descend');
for ii = 1:numel(order)
    k = order(ii);
    if controls.reactive_only_QS(k), continue; end
    [ids, rule, conf] = proxy_candidates(controls.source_zone(k), ...
        controls.source_plant_name(k), controls.device_class(k));
    ids = ids(ismember(ids, candidates.retained_bus));
    if isempty(ids), continue; end
    ci = find(ismember(candidates.retained_bus, ids));
    score = assigned(ci) ./ max(candidates.s7_pmax_mw(ci), 1);
    [~, pick] = min(score);
    selected = ci(pick);
    device_bus(k) = candidates.retained_bus(selected);
    method(k) = rule;
    confidence(k) = conf;
    if controls.snapshot_effective_status(k) > 0
        assigned(selected) = assigned(selected) + ...
            max([controls.pmax_mw(k), abs(controls.pg_mw(k)), 1]);
    end
end
end

function [ids, rule, confidence] = proxy_candidates(zone, plant, device_class)
zone = string(zone); plant = lower(string(plant));
rule = "same-zone PERFORM plant/GSK proxy"; confidence = "medium";
if device_class == "fixed_import_or_boundary_equivalent"
    switch zone
        case "A", ids = 56;
        case "E", ids = 43;
        case "F", ids = 37;
        case "G", ids = 76;
        case "J", ids = 81;
        case "K", ids = 9003;
        otherwise, ids = zone_default_candidates(zone);
    end
    rule = "boundary/import record kept separate at same-zone proxy";
    confidence = "medium";
    return;
end
switch zone
    case "A"
        if contains_any(plant, ["robert moses niagara","lewiston niagara"])
            ids = [54 55]; rule = "direct Niagara plant cluster"; confidence = "high";
        else
            ids = [56 57 60 61]; rule = "residual Zone-A Huntley/Dunkirk proxies";
        end
    case "B", ids = 53; rule = "Zone-B Rochester proxy";
    case "C"
        if contains_any(plant, ["nine mile","fitzpatrick","independence","oswego"])
            ids = [50 51]; rule = "direct Clay generation cluster"; confidence = "high";
        elseif contains(plant, "greenidge")
            ids = 65; rule = "direct Greenidge proxy"; confidence = "high";
        elseif contains(plant, "binghamton")
            ids = 71; rule = "direct Binghamton proxy"; confidence = "high";
        else
            ids = [68 72]; rule = "residual Zone-C Hillside/Lapeer proxies";
        end
    case "D", ids = [47 48]; rule = "Zone-D Moses proxies"; confidence = "low";
    case "E"
        if contains(plant, "robert moses power dam")
            % The converted PERFORM source assigns bus 1230 MOSES to numeric
            % zone 69 (NYISO E). Preserve that authoritative zonal injection;
            % the station name alone is not enough to move it across Moses
            % South into the reduced Zone-D proxy.
            ids = [43 44];
            rule = "source Zone-E Edic/Porter hydro proxies";
            confidence = "low";
        else
            ids = [43 44]; rule = "Zone-E Edic/Porter proxies"; confidence = "low";
        end
    case "F"
        if contains(plant, "blenheim gilboa")
            ids = 38; rule = "direct Gilboa plant proxy"; confidence = "high";
        elseif contains_any(plant, ["bethlehem energy","empire generating"])
            ids = 42; rule = "Capital-region Albany cluster";
        elseif contains(plant, "selkirk")
            ids = 41; rule = "Selkirk Rotterdam proxy";
        else
            ids = 37; rule = "residual Zone-F New Scotland proxy";
        end
    case "G"
        if contains_any(plant, ["athens","south cairo","west coxsackie"])
            ids = 39; rule = "Leeds-area plant cluster";
        elseif contains_any(plant, ["roseton","cpv valley"])
            ids = 73; rule = "Pleasant-Valley plant cluster";
        else
            ids = 76; rule = "residual Zone-G Ramapo proxy";
        end
    case "H", ids = 75; rule = "Zone-H Millwood control proxy"; confidence = "low";
    case "I", ids = 78; rule = "Zone-I CE UG interface/control proxy"; confidence = "low";
    case "J"
        if contains_any(plant, ["ravenswood","astoria","500mw cc"])
            ids = 79; rule = "Queens/Ravenswood-Astoria cluster"; confidence = "high";
        elseif contains_any(plant, ["arthur kill","narrows"])
            ids = 82; rule = "Arthur-Kill/Narrows cluster"; confidence = "high";
        else
            ids = 81; rule = "residual Zone-J Goethals/Gowanus proxy";
        end
    case "K"
        if contains(plant, "northport")
            ids = 80; rule = "direct Northport proxy"; confidence = "high";
        else
            ids = 9003; rule = "residual Zone-K East-Garden-City proxy";
        end
    otherwise, ids = [];
end
end

function ids = zone_default_candidates(zone)
switch string(zone)
    case "A", ids = [54 55 56 57 60 61];
    case "B", ids = 53;
    case "C", ids = [50 51 65 68 71 72];
    case "D", ids = [47 48];
    case "E", ids = [43 44];
    case "F", ids = [37 38 41 42];
    case "G", ids = [39 73 76];
    case "H", ids = 75;
    case "I", ids = 78;
    case "J", ids = [79 81 82];
    case "K", ids = [80 9003];
    otherwise, ids = [];
end
end

function yes = contains_any(value, patterns)
yes = false;
for k = 1:numel(patterns), yes = yes || contains(value, patterns(k)); end
end

function anchors = anchor_table(controls, candidates)
valid = controls.snapshot_effective_status > 0 & ~controls.reactive_only_QS & ...
    isfinite(controls.retained_device_bus);
anchors = table();
for bus_id = candidates.retained_bus(:)'
    idx = valid & controls.retained_device_bus == bus_id;
    if ~any(idx), continue; end
    row = table(bus_id, candidates.zone(candidates.retained_bus == bus_id), ...
        {unique(controls.source_bus(idx))'}, ...
        'VariableNames', {'retained_bus','zone','source_anchor_buses'});
    anchors = append_table(anchors, row);
end
end

function ward = ward_context(source, requested_bus_ids)
define_constants;
external_ids = source.bus(:, BUS_I);
[okf, f] = ismember(source.branch(:, F_BUS), external_ids);
[okt, t] = ismember(source.branch(:, T_BUS), external_ids);
[okg, g] = ismember(source.gen(:, GEN_BUS), external_ids);
if ~all(okf & okt) || ~all(okg), error('PERFORM bus indexing is inconsistent.'); end
internal = source;
internal.bus(:, BUS_I) = (1:size(source.bus, 1))';
internal.branch(:, F_BUS) = f; internal.branch(:, T_BUS) = t;
internal.gen(:, GEN_BUS) = g;
[Ybus, ~, ~] = makeYbus(internal.baseMVA, internal.bus, internal.branch);
ref = find(internal.bus(:, BUS_TYPE) == REF, 1);
nonref = setdiff((1:size(internal.bus, 1))', ref);
red_index = zeros(size(internal.bus, 1), 1);
red_index(nonref) = (1:numel(nonref))';

query_ids = unique(requested_bus_ids(isfinite(requested_bus_ids)), 'stable');
[found, query_rows] = ismember(query_ids, external_ids);
query_ids = query_ids(found); query_rows = query_rows(found);
active = query_rows ~= ref;
rhs = sparse(red_index(query_rows(active)), 1:nnz(active), 1, ...
    numel(nonref), nnz(active));
solution = Ybus(nonref, nonref) \ rhs;
Z = complex(zeros(numel(query_ids), numel(query_ids)));
Z(active, active) = solution(red_index(query_rows(active)), :);
ward = struct('bus_ids', query_ids, 'Z', Z, 'reference_bus', external_ids(ref));
end

function [bus_id, distance] = nearest_retained_proxy(source_bus, zone, ...
        anchors, candidates, ward)
eligible = anchors;
if strlength(zone) > 0 && any(anchors.zone == zone)
    eligible = anchors(anchors.zone == zone, :);
end
bus_id = NaN; distance = Inf;
for k = 1:height(eligible)
    d = min_ward_distance(ward, source_bus, eligible.source_anchor_buses{k});
    if d < distance
        distance = d; bus_id = eligible.retained_bus(k);
    end
end
if ~isfinite(bus_id)
    ids = candidates.retained_bus(candidates.zone == zone);
    if isempty(ids), ids = candidates.retained_bus; end
    if ~isempty(ids), bus_id = ids(1); end
end
end

function d = min_ward_distance(ward, source_bus, anchor_buses)
[tf, i] = ismember(source_bus, ward.bus_ids);
[af, a] = ismember(anchor_buses(:), ward.bus_ids);
a = a(af);
if ~tf || isempty(a), d = Inf; return; end
values = abs(ward.Z(i,i) + diag(ward.Z(a,a)) - ward.Z(i,a).' - ward.Z(a,i));
d = min(values);
end

function types = reduced_device_types(controls)
types = repmat("unclassified_control_record", height(controls), 1);
types(controls.native_generator) = "aggregate_pv_generator";
types(controls.reactive_only_QS) = "controllable_q_device";
types(controls.fixed_import_or_boundary_equivalent) = "boundary_import_equivalent";
types(controls.synchronous_condenser) = "synchronous_condenser";
types(controls.storage_or_pumping) = "storage_or_pumping";
types(controls.offline) = "offline_preserved_record";
end

function participation = q_participation_factors(controls, group_id)
participation = zeros(height(controls), 1);
groups = unique(group_id(group_id ~= "UNMAPPED"), 'stable');
for k = 1:numel(groups)
    idx = group_id == groups(k) & controls.snapshot_effective_status > 0;
    qrange = max(controls.qmax_mvar(idx) - controls.qmin_mvar(idx), 0);
    if sum(qrange) <= 0, qrange = ones(sum(idx), 1); end
    participation(idx) = qrange / sum(qrange);
end
end

function groups = aggregate_control_groups(control_map, source_pf)
define_constants;
online = control_map.snapshot_effective_status > 0 & ...
    control_map.reduced_control_group_id ~= "UNMAPPED";
ids = unique(control_map.reduced_control_group_id(online), 'stable');
groups = table();
for k = 1:numel(ids)
    idx = online & control_map.reduced_control_group_id == ids(k);
    qweight = max(control_map.source_QMAX(idx) - control_map.source_QMIN(idx), 0);
    if sum(qweight) <= 0, qweight = ones(sum(idx), 1); end
    qweight = qweight / sum(qweight);
    source_q = control_map.source_QG(idx);
    ci = control_map.converted_gen_index(idx);
    finite_ci = isfinite(ci);
    source_q(finite_ci) = source_pf.gen(ci(finite_ci), QG);
    qs = control_map.device_class(idx) == "reactive_only_QS";
    source_buses = control_map.source_bus(idx);
    [found_bus, source_bi] = ismember(source_buses(qs), source_pf.bus(:, BUS_I));
    qs_q = zeros(sum(qs), 1);
    qs_q(found_bus) = source_pf.bus(source_bi(found_bus), BS) .* ...
        source_pf.bus(source_bi(found_bus), VM).^2;
    source_q(qs) = qs_q;
    confidence = aggregate_confidence(control_map.mapping_confidence(idx));
    row = table(ids(k), control_map.retained_device_bus(find(idx,1)), ...
        control_map.retained_pilot_bus(find(idx,1)), ...
        control_map.reduced_device_type(find(idx,1)), sum(idx), ...
        sum(control_map.source_PG(idx)), sum(source_q), ...
        sum(control_map.source_PMIN(idx)), sum(control_map.source_PMAX(idx)), ...
        sum(control_map.source_QMIN(idx)), sum(control_map.source_QMAX(idx)), ...
        sum(qweight .* control_map.source_VS(idx)), confidence, ...
        join(string(unique(control_map.source_bus(idx)))', '|'), ...
        'VariableNames', {'reduced_control_group_id','retained_device_bus', ...
        'retained_pilot_bus','reduced_device_type','source_record_count', ...
        'source_pg_mw','source_qg_mvar','source_pmin_mw','source_pmax_mw', ...
        'source_qmin_mvar','source_qmax_mvar','source_vs_pu', ...
        'mapping_confidence','source_bus_ids'});
    groups = append_table(groups, row);
end
end

function confidence = aggregate_confidence(values)
if any(values == "low"), confidence = "low";
elseif any(values == "medium"), confidence = "medium";
else, confidence = "high";
end
end

function audit = audit_pq_skipped_buses(s7, control_map)
define_constants;
[mapped, bi] = ismember(s7.gen(:, GEN_BUS), s7.bus(:, BUS_I));
gen_zone = strings(size(s7.gen, 1), 1);
gen_zone(mapped) = string(s7.userdata.nyiso_physical_zone(bi(mapped)));
ny_gen = s7.gen(:, GEN_STATUS) > 0 & mapped & gen_zone ~= "";
ids = unique(s7.gen(ny_gen, GEN_BUS));
pq_ids = ids(arrayfun(@(x) s7.bus(s7.bus(:,BUS_I)==x, BUS_TYPE) == PQ, ids));
audit = table();
for bus_id = pq_ids(:)'
    bi = find(s7.bus(:, BUS_I) == bus_id, 1);
    idx = control_map.snapshot_effective_status > 0 & ...
        (control_map.retained_device_bus == bus_id | ...
        control_map.retained_pilot_bus == bus_id);
    local = idx & control_map.retained_pilot_bus == bus_id;
    source_backed = local & ismember(control_map.reduced_device_type, ...
        ["aggregate_pv_generator","controllable_q_device", ...
        "synchronous_condenser","storage_or_pumping"]);
    qmin = sum(control_map.source_QMIN(source_backed));
    qmax = sum(control_map.source_QMAX(source_backed));
    broad_q = source_backed & (abs(control_map.source_QMIN) > 5000 | ...
        abs(control_map.source_QMAX) > 5000 | ...
        control_map.source_QMAX - control_map.source_QMIN > ...
        4 * max(control_map.source_PMAX, 100));
    low_confidence = source_backed & control_map.mapping_confidence == "low";
    benchmark_pv_enabled = any(source_backed) && qmax - qmin > 1e-3;
    if any(source_backed) && qmax - qmin > 1e-3
        if any(broad_q) || any(low_confidence)
            decision = "PV_candidate_pending_q_envelope_validation";
            reason = "source control exists but Q envelope or mapping is provisional";
        else
            decision = "PV_candidate_source_backed";
            reason = "online mapped regulating device with bounded Q range";
        end
    elseif any(idx & control_map.reduced_device_type == "boundary_import_equivalent")
        decision = "remain_PQ_boundary_or_import_proxy";
        reason = "only boundary/import control evidence";
    else
        decision = "remain_PQ_no_source_control_evidence";
        reason = "no mapped online regulating device with defensible Q range";
    end
    row = table(bus_id, string(strtrim(s7.bus_name{bi})), ...
        string(s7.userdata.nyiso_physical_zone{bi}), sum(idx), sum(source_backed), ...
        sum(idx & control_map.reduced_device_type == "controllable_q_device"), ...
        sum(idx & control_map.reduced_device_type == "boundary_import_equivalent"), ...
        qmin, qmax, qmax - qmin, sum(broad_q), sum(low_confidence), ...
        benchmark_pv_enabled, join(string(unique(control_map.source_bus(idx)))', '|'), ...
        decision, reason, ...
        'VariableNames', {'bus_id','bus_name','zone','online_mapped_control_count', ...
        'source_backed_regulating_count','reactive_only_qs_count', ...
        'boundary_import_count','source_qmin_mvar','source_qmax_mvar', ...
        'source_q_range_mvar','broad_q_limit_record_count', ...
        'low_confidence_mapping_count','s10a_diagnostic_pv_enabled', ...
        'source_bus_ids','recommended_treatment','reason'});
    audit = append_table(audit, row);
end
end

function [summary, detail] = discrete_control_inventory(source, control_map, ...
        candidates, anchors, ward, ~, options)
define_constants;
[records, sections] = psse_read(options.perform_raw_file, 0);
[data, ~] = psse_parse(records, sections, 0, 33);
metrics = ["raw_two_winding_transformers";"converted_nonunity_taps"; ...
    "converted_phase_shifts";"raw_fixed_shunts";"raw_switched_shunts"; ...
    "converted_nonzero_bus_shunts"];
values = [size(data.trans2.num,1); ...
    nnz(source.branch(:,TAP) ~= 0 & abs(source.branch(:,TAP)-1) > 1e-9); ...
    nnz(abs(source.branch(:,SHIFT)) > 1e-9); size(data.shunt.num,1); ...
    size(data.swshunt.num,1); nnz(abs(source.bus(:,GS))+abs(source.bus(:,BS)) > 1e-9)];
summary = table(metrics, values, repmat("records", numel(values), 1), ...
    'VariableNames', {'metric','value','unit'});

map_bus = source.bus(:, BUS_I);
map_zone = perform_nyiso_zone_letters(source, map_bus);
detail = table();
tap_rows = find(source.branch(:,TAP) ~= 0 & abs(source.branch(:,TAP)-1) > 1e-9 | ...
    abs(source.branch(:,SHIFT)) > 1e-9);
for br = tap_rows(:)'
    fb = source.branch(br,F_BUS); tb = source.branch(br,T_BUS);
    fz = source_zone(fb, map_bus, map_zone); tz = source_zone(tb, map_bus, map_zone);
    [rf, ~] = nearest_retained_proxy(fb, fz, anchors, candidates, ward);
    [rt, ~] = nearest_retained_proxy(tb, tz, anchors, candidates, ward);
    row = discrete_row("transformer_tap_or_phase", br, fb, tb, ...
        source.branch(br,TAP), source.branch(br,SHIFT), rf, rt, ...
        "inventory_only; no automatic tap import without branch-equivalence proof");
    detail = append_table(detail, row);
end
shunt_rows = find(abs(source.bus(:,GS))+abs(source.bus(:,BS)) > 1e-9);
for bi = shunt_rows(:)'
    source_bus = source.bus(bi,BUS_I);
    mapped = control_map(control_map.source_bus == source_bus & ...
        control_map.device_class == "reactive_only_QS", :);
    if isempty(mapped)
        zone = source_zone(source_bus, map_bus, map_zone);
        [rb, ~] = nearest_retained_proxy(source_bus, zone, anchors, candidates, ward);
    else
        rb = mapped.retained_pilot_bus(1);
    end
    row = discrete_row("switched_shunt_snapshot", bi, source_bus, NaN, ...
        source.bus(bi,BS), source.bus(bi,GS), rb, NaN, ...
        "represented in S10a as controllable Q initialized from BINIT times VM squared; switching blocks not optimized");
    detail = append_table(detail, row);
end
end

function zone = source_zone(bus_id, map_bus, map_zone)
idx = find(map_bus == bus_id, 1);
if isempty(idx), zone = ""; else, zone = map_zone(idx); end
end

function row = discrete_row(kind, index, from_bus, to_bus, value1, value2, ...
        reduced_from, reduced_to, action)
row = table(string(kind), index, from_bus, to_bus, value1, value2, ...
    reduced_from, reduced_to, string(action), ...
    'VariableNames', {'control_type','source_element_index','source_from_bus', ...
    'source_to_bus','source_value_1','source_value_2','retained_from_bus', ...
    'retained_to_bus','reduced_treatment'});
end

function report = summarize_anchors(anchors, candidates)
report = table();
for k = 1:height(candidates)
    idx = find(anchors.retained_bus == candidates.retained_bus(k), 1);
    if isempty(idx)
        source_ids = ""; count = 0;
    else
        source_ids = join(string(anchors.source_anchor_buses{idx}), '|');
        count = numel(anchors.source_anchor_buses{idx});
    end
    row = table(candidates.retained_bus(k), candidates.retained_bus_name(k), ...
        candidates.zone(k), count, source_ids, candidates.s7_bus_type(k), ...
        candidates.s7_pmax_mw(k), ...
        'VariableNames', {'retained_bus','retained_bus_name','zone', ...
        'source_anchor_count','source_anchor_buses','s7_bus_type','s7_pmax_mw'});
    report = append_table(report, row);
end
end

function out = append_table(out, row)
if isempty(row), return; end
if isempty(out), out = row; else, out = [out; row]; end
end
