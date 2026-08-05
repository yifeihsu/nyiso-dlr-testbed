function [mpc, branch_map] = split_perform_parallel_corridors(mpc, options)
%SPLIT_PERFORM_PARALLEL_CORRIDORS Restore individual PERFORM circuits.
%   [MPC, BRANCH_MAP] = SPLIT_PERFORM_PARALLEL_CORRIDORS(MPC) replaces the
%   Pleasant Valley--Wood Street and Wood Street--Millwood parallel
%   equivalents with the two physical circuits represented by each row.
%   The single Gilboa--Leeds circuit is retained unchanged.
%
%   The function deliberately finds rows from reduced endpoints and exact
%   aggregate R/X/B/rating values. It does not use the stale full-case
%   branch indices that can remain in USERDATA after the 49-bus reduction.
%   Reapplying the function to an already-split case is idempotent.
%
%   Every branch is classified as one of:
%       physical_circuit
%       aggregate_equivalent
%       transformer_or_boundary_equivalent
%   Only the five exact PERFORM rows receive stable physical circuit IDs.
%
%   Options:
%       write_map          write BRANCH_MAP as CSV (default false)
%       map_file           output path (default s11_physical_circuit_map.csv)
%       boundary_bus_ids   buses whose incident non-physical branches are
%                          boundary equivalents (default [])
%       match_tolerance    absolute parameter-match tolerance (default 1e-10)

if nargin < 1 || isempty(mpc)
    structural = loadcase( ...
        'npcc_ny_lite_s7_seven_interface_perform_direct_candidate');
    [mpc, ~] = build_ny_only_equivalent_case(structural);
elseif ischar(mpc) || isstring(mpc)
    mpc = loadcase(char(mpc));
end
if nargin < 2, options = struct(); end

helper_dir = fileparts(mfilename('fullpath'));
options = defaults(options, helper_dir);
define_constants;

specs = perform_circuit_specs();
validate_parallel_equivalents(specs, options.match_tolerance);
initial_branch_count = size(mpc.branch, 1);

gl = specs(strcmp({specs.corridor_name}, 'GILBOA_LEEDS'));
gl_rows = find_matching_rows(mpc.branch, gl, options.match_tolerance);
if numel(gl_rows) ~= 1
    error('split_perform_parallel_corridors:GilboaLeedsMismatch', ...
        ['Expected exactly one direct PERFORM Gilboa--Leeds circuit, ' ...
        'but found %d.'], numel(gl_rows));
end

[pv_state, pv_aggregate_row] = corridor_state(mpc.branch, specs, ...
    'PLEASANT_VALLEY_WOOD_STREET', options.match_tolerance);
[wm_state, wm_aggregate_row] = corridor_state(mpc.branch, specs, ...
    'WOOD_STREET_MILLWOOD', options.match_tolerance);

first_application = pv_state == "aggregate" && wm_state == "aggregate";
already_split = pv_state == "split" && wm_state == "split";
if ~(first_application || already_split)
    error('split_perform_parallel_corridors:PartialSplit', ...
        ['The two parallel corridors are in inconsistent states ' ...
        '(Pleasant-Wood=%s, Wood-Millwood=%s). Refusing a partial split.'], ...
        pv_state, wm_state);
end

if first_application
    pv_specs = specs(strcmp({specs.corridor_name}, ...
        'PLEASANT_VALLEY_WOOD_STREET'));
    wm_specs = specs(strcmp({specs.corridor_name}, ...
        'WOOD_STREET_MILLWOOD'));

    pv_second = mpc.branch(pv_aggregate_row, :);
    wm_second = mpc.branch(wm_aggregate_row, :);
    mpc.branch(pv_aggregate_row, :) = apply_circuit_values( ...
        mpc.branch(pv_aggregate_row, :), pv_specs(1));
    mpc.branch(wm_aggregate_row, :) = apply_circuit_values( ...
        mpc.branch(wm_aggregate_row, :), wm_specs(1));
    pv_second = apply_circuit_values(pv_second, pv_specs(2));
    wm_second = apply_circuit_values(wm_second, wm_specs(2));
    mpc.branch = [mpc.branch; pv_second; wm_second];

    if size(mpc.branch, 1) ~= initial_branch_count + 2
        error('split_perform_parallel_corridors:BranchCount', ...
            'First application must add exactly two branch rows.');
    end
elseif size(mpc.branch, 1) ~= initial_branch_count
    error('split_perform_parallel_corridors:Idempotence', ...
        'An idempotent application unexpectedly changed the branch count.');
end

branch_map = build_branch_map(mpc, specs, options);
physical = branch_map.branch_classification == "physical_circuit";
if nnz(physical) ~= 5 || numel(unique( ...
        branch_map.physical_circuit_id(physical))) ~= 5
    error('split_perform_parallel_corridors:PhysicalCircuitCount', ...
        'Expected five uniquely identified direct PERFORM physical circuits.');
end

if ~isfield(mpc, 'userdata'), mpc.userdata = struct(); end
s11_dlr = struct();
s11_dlr.branch_classification = cellstr(branch_map.branch_classification);
s11_dlr.physical_circuit_id = cellstr(branch_map.physical_circuit_id);
s11_dlr.source_branch_index = branch_map.source_branch_index;
s11_dlr.source_circuit_id = cellstr(branch_map.source_circuit_id);
s11_dlr.physical_circuit_map = branch_map;
s11_dlr.aggregate_case_branch_count = size(mpc.branch, 1) - 2;
s11_dlr.final_branch_count = size(mpc.branch, 1);
s11_dlr.split_branch_count_delta = 2;
s11_dlr.status = 'individual_PERFORM_circuits_restored';
mpc.userdata.s11_dlr = s11_dlr;

if options.write_map
    out_dir = fileparts(options.map_file);
    if ~isempty(out_dir) && ~isfolder(out_dir)
        error('split_perform_parallel_corridors:MissingOutputDirectory', ...
            'Map output directory does not exist: %s', out_dir);
    end
    writetable(branch_map, options.map_file);
end
end

function options = defaults(options, helper_dir)
if ~isfield(options, 'write_map'), options.write_map = false; end
if ~isfield(options, 'map_file')
    options.map_file = fullfile(helper_dir, 's11_physical_circuit_map.csv');
end
if ~isfield(options, 'boundary_bus_ids'), options.boundary_bus_ids = []; end
if ~isfield(options, 'match_tolerance'), options.match_tolerance = 1e-10; end
validateattributes(options.write_map, {'logical','numeric'}, {'scalar'});
if ~isempty(options.boundary_bus_ids)
    validateattributes(options.boundary_bus_ids, {'numeric'}, ...
        {'vector','finite'});
end
validateattributes(options.match_tolerance, {'numeric'}, ...
    {'scalar','positive','finite'});
options.write_map = logical(options.write_map);
options.boundary_bus_ids = options.boundary_bus_ids(:);
end

function specs = perform_circuit_specs()
fields = {'physical_circuit_id','corridor_name','source_circuit_id', ...
    'source_branch_index','source_from_bus','source_to_bus', ...
    'source_from_name','source_to_name','reduced_from_bus', ...
    'reduced_to_bus','source_from_reduced_bus','source_to_reduced_bus', ...
    'r','x','b','rate_a','rate_b','rate_c'};
rows = { ...
    'PERFORM_818_1227_CKT_1','GILBOA_LEEDS','1',1635,818,1227, ...
        'LEEDS','GILBOA',38,39,39,38,0.00131,0.01997,0.51614,1216,2454,1804; ...
    'PERFORM_651_902_CKT_1','PLEASANT_VALLEY_WOOD_STREET','1',1391,651,902, ...
        'PLEASANT VALLEY','WOOD STREET',73,9002,73,9002,0.00081,0.01237,0.31971,1216,2454,1804; ...
    'PERFORM_651_902_CKT_2','PLEASANT_VALLEY_WOOD_STREET','2',1392,651,902, ...
        'PLEASANT VALLEY','WOOD STREET',73,9002,73,9002,0.00081,0.01237,0.31972,1216,2454,1804; ...
    'PERFORM_902_897_CKT_1','WOOD_STREET_MILLWOOD','1',1734,902,897, ...
        'WOOD STREET','MILLWOOD',9002,74,9002,74,0.00037,0.00563,0.14565,1216,2454,1804; ...
    'PERFORM_902_897_CKT_2','WOOD_STREET_MILLWOOD','2',1735,902,897, ...
        'WOOD STREET','MILLWOOD',9002,74,9002,74,0.00037,0.00563,0.14542,1216,2454,1804};
specs = cell2struct(rows, fields, 2);
end

function validate_parallel_equivalents(specs, tol)
checks = { ...
    'PLEASANT_VALLEY_WOOD_STREET', 0.000405, 0.006185, 0.63943, 2432, 4908, 3608; ...
    'WOOD_STREET_MILLWOOD', 0.000185, 0.002815, 0.29107, 2432, 4908, 3608};
for k = 1:size(checks, 1)
    rows = specs(strcmp({specs.corridor_name}, checks{k, 1}));
    z_eq = 1 / sum(1 ./ ([rows.r] + 1j * [rows.x]));
    actual = [real(z_eq), imag(z_eq), sum([rows.b]), ...
        sum([rows.rate_a]), sum([rows.rate_b]), sum([rows.rate_c])];
    expected = cell2mat(checks(k, 2:end));
    if any(abs(actual - expected) > tol)
        error('split_perform_parallel_corridors:SourceData', ...
            'Circuit data do not reproduce the documented %s aggregate.', ...
            checks{k, 1});
    end
end
end

function [state, aggregate_row] = corridor_state(branch, specs, name, tol)
rows = specs(strcmp({specs.corridor_name}, name));
switch name
    case 'PLEASANT_VALLEY_WOOD_STREET'
        aggregate = aggregate_spec(73, 9002, 0.000405, 0.006185, ...
            0.63943, 2432, 4908, 3608);
    case 'WOOD_STREET_MILLWOOD'
        aggregate = aggregate_spec(9002, 74, 0.000185, 0.002815, ...
            0.29107, 2432, 4908, 3608);
    otherwise
        error('split_perform_parallel_corridors:UnknownCorridor', ...
            'Unknown parallel corridor %s.', name);
end
aggregate_matches = find_matching_rows(branch, aggregate, tol);
circuit_1 = find_matching_rows(branch, rows(1), tol);
circuit_2 = find_matching_rows(branch, rows(2), tol);
if isscalar(aggregate_matches) && isempty(circuit_1) && isempty(circuit_2)
    state = "aggregate";
    aggregate_row = aggregate_matches(1);
elseif isempty(aggregate_matches) && isscalar(circuit_1) && ...
        isscalar(circuit_2) && circuit_1 ~= circuit_2
    state = "split";
    aggregate_row = NaN;
else
    state = "invalid";
    aggregate_row = NaN;
end
end

function spec = aggregate_spec(fbus, tbus, r, x, b, rate_a, rate_b, rate_c)
spec = struct('reduced_from_bus', fbus, 'reduced_to_bus', tbus, ...
    'r', r, 'x', x, 'b', b, 'rate_a', rate_a, ...
    'rate_b', rate_b, 'rate_c', rate_c);
end

function rows = find_matching_rows(branch, spec, tol)
define_constants;
endpoints = (branch(:, F_BUS) == spec.reduced_from_bus & ...
    branch(:, T_BUS) == spec.reduced_to_bus) | ...
    (branch(:, F_BUS) == spec.reduced_to_bus & ...
    branch(:, T_BUS) == spec.reduced_from_bus);
values = abs(branch(:, BR_R) - spec.r) <= tol & ...
    abs(branch(:, BR_X) - spec.x) <= tol & ...
    abs(branch(:, BR_B) - spec.b) <= tol & ...
    abs(branch(:, RATE_A) - spec.rate_a) <= tol & ...
    abs(branch(:, RATE_B) - spec.rate_b) <= tol & ...
    abs(branch(:, RATE_C) - spec.rate_c) <= tol;
rows = find(endpoints & values);
end

function row = apply_circuit_values(row, spec)
define_constants;
row([BR_R BR_X BR_B RATE_A RATE_B RATE_C]) = ...
    [spec.r spec.x spec.b spec.rate_a spec.rate_b spec.rate_c];
% A split invalidates any solved flow or OPF multiplier columns inherited
% from an input results struct. Preserve only the MATPOWER input columns.
if numel(row) >= PF
    row(PF:min(numel(row), MU_ANGMAX)) = 0;
end
end

function branch_map = build_branch_map(mpc, specs, options)
define_constants;
nl = size(mpc.branch, 1);
classification = repmat("aggregate_equivalent", nl, 1);
transformer = abs(mpc.branch(:, TAP)) > options.match_tolerance | ...
    abs(mpc.branch(:, SHIFT)) > options.match_tolerance;
if ~isempty(options.boundary_bus_ids)
    transformer = transformer | ...
        ismember(mpc.branch(:, F_BUS), options.boundary_bus_ids) | ...
        ismember(mpc.branch(:, T_BUS), options.boundary_bus_ids);
end
classification(transformer) = "transformer_or_boundary_equivalent";

physical_id = strings(nl, 1);
corridor = strings(nl, 1);
source_circuit_id = strings(nl, 1);
source_branch_index = nan(nl, 1);
source_from_bus = nan(nl, 1);
source_to_bus = nan(nl, 1);
source_from_name = strings(nl, 1);
source_to_name = strings(nl, 1);
orientation_sign = nan(nl, 1);
mapping_confidence = repmat("unmapped", nl, 1);
parameter_source = repmat("reduced-network aggregate or equivalent", nl, 1);

for k = 1:numel(specs)
    idx = find_matching_rows(mpc.branch, specs(k), options.match_tolerance);
    if numel(idx) ~= 1
        error('split_perform_parallel_corridors:CircuitResolution', ...
            'Physical circuit %s resolved to %d branch rows.', ...
            specs(k).physical_circuit_id, numel(idx));
    end
    b = idx(1);
    classification(b) = "physical_circuit";
    physical_id(b) = string(specs(k).physical_circuit_id);
    corridor(b) = string(specs(k).corridor_name);
    source_circuit_id(b) = string(specs(k).source_circuit_id);
    source_branch_index(b) = specs(k).source_branch_index;
    source_from_bus(b) = specs(k).source_from_bus;
    source_to_bus(b) = specs(k).source_to_bus;
    source_from_name(b) = string(specs(k).source_from_name);
    source_to_name(b) = string(specs(k).source_to_name);
    if mpc.branch(b, F_BUS) == specs(k).source_from_reduced_bus && ...
            mpc.branch(b, T_BUS) == specs(k).source_to_reduced_bus
        orientation_sign(b) = 1;
    else
        orientation_sign(b) = -1;
    end
    mapping_confidence(b) = "high";
    parameter_source(b) = "PERFORM NYISO On Peak 2019 v23 RAW";
end

from_name = branch_bus_names(mpc, mpc.branch(:, F_BUS));
to_name = branch_bus_names(mpc, mpc.branch(:, T_BUS));
branch_map = table((1:nl)', mpc.branch(:, F_BUS), mpc.branch(:, T_BUS), ...
    from_name, to_name, classification, physical_id, corridor, ...
    source_circuit_id, source_branch_index, source_from_bus, source_to_bus, ...
    source_from_name, source_to_name, orientation_sign, ...
    mpc.branch(:, BR_R), mpc.branch(:, BR_X), mpc.branch(:, BR_B), ...
    mpc.branch(:, RATE_A), mpc.branch(:, RATE_B), mpc.branch(:, RATE_C), ...
    mapping_confidence, parameter_source, ...
    'VariableNames', {'branch_index','reduced_from_bus','reduced_to_bus', ...
    'reduced_from_name','reduced_to_name','branch_classification', ...
    'physical_circuit_id','corridor_name','source_circuit_id', ...
    'source_branch_index','source_from_bus','source_to_bus', ...
    'source_from_name','source_to_name','source_to_reduced_flow_sign', ...
    'r_pu','x_pu','b_pu','rate_a_mva','rate_b_mva','rate_c_mva', ...
    'mapping_confidence','parameter_source'});
end

function names = branch_bus_names(mpc, bus_ids)
names = "BUS_" + string(bus_ids);
if ~isfield(mpc, 'bus_name'), return; end
[found, idx] = ismember(bus_ids, mpc.bus(:, 1));
names(found) = strtrim(string(mpc.bus_name(idx(found))));
end
