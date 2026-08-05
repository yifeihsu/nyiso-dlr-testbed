function report = compute_branch_currents_kA(results, branch_map, options)
%COMPUTE_BRANCH_CURRENTS_KA Report solved branch powers and currents.
%   REPORT = COMPUTE_BRANCH_CURRENTS_KA(RESULTS, BRANCH_MAP) accepts a
%   solved MATPOWER results struct and the table returned by
%   SPLIT_PERFORM_PARALLEL_CORRIDORS. If BRANCH_MAP is empty, the function
%   recovers it from RESULTS.userdata.s11_dlr when available.
%
%   Terminal currents use line-line RMS terminal voltage:
%       If = hypot(PF,QF) / (sqrt(3) * VMf * BASE_KVf)
%       It = hypot(PT,QT) / (sqrt(3) * VMt * BASE_KVt)
%   where MW/kV gives kA.
%
%   The series-element current follows the MATPOWER branch pi model:
%       tap = TAP * exp(j*SHIFT), with TAP=1 when the stored value is zero
%       Iseries_pu = (Vf/tap - Vt) / (R + jX)
%   It is converted to physical kA on the to-side voltage base using
%   BASEMVA/(sqrt(3)*BASE_KVt). For the mapped DLR circuits TAP=1 and both
%   terminals are 345 kV, so the base-side convention is unambiguous.
%
%   Options:
%       output_file                  optional CSV output path (default "")
%       series_impedance_tolerance   zero-impedance threshold (default 1e-12)

if nargin < 1 || isempty(results)
    error('compute_branch_currents_kA:MissingResults', ...
        'A solved MATPOWER results struct is required.');
elseif ischar(results) || isstring(results)
    results = loadcase(char(results));
end
if nargin < 2, branch_map = []; end
if nargin < 3, options = struct(); end
if isstruct(branch_map) && ~istable(branch_map)
    if nargin >= 3 && ~isempty(fieldnames(options))
        error('compute_branch_currents_kA:AmbiguousOptions', ...
            'Options were supplied in both the second and third arguments.');
    end
    options = branch_map;
    branch_map = [];
end
options = defaults(options);

define_constants;
if size(results.branch, 2) < QT
    error('compute_branch_currents_kA:MissingPowerFlowColumns', ...
        'Run an AC power flow before computing branch currents.');
end

nl = size(results.branch, 1);
[found_f, fi] = ismember(results.branch(:, F_BUS), results.bus(:, BUS_I));
[found_t, ti] = ismember(results.branch(:, T_BUS), results.bus(:, BUS_I));
if ~all(found_f & found_t)
    error('compute_branch_currents_kA:UnknownBus', ...
        'One or more branch endpoints are missing from the bus matrix.');
end

vf = results.bus(fi, VM) .* exp(1j * pi/180 * results.bus(fi, VA));
vt = results.bus(ti, VM) .* exp(1j * pi/180 * results.bus(ti, VA));
from_terminal_kv = results.bus(fi, VM) .* results.bus(fi, BASE_KV);
to_terminal_kv = results.bus(ti, VM) .* results.bus(ti, BASE_KV);

from_current = safe_terminal_current(results.branch(:, PF), ...
    results.branch(:, QF), from_terminal_kv);
to_current = safe_terminal_current(results.branch(:, PT), ...
    results.branch(:, QT), to_terminal_kv);

tap_ratio = results.branch(:, TAP);
tap_ratio(tap_ratio == 0) = 1;
complex_tap = tap_ratio .* exp(1j * pi/180 * results.branch(:, SHIFT));
z = results.branch(:, BR_R) + 1j * results.branch(:, BR_X);
series_current_pu = nan(nl, 1);
valid_z = abs(z) > options.series_impedance_tolerance;
series_current_pu(valid_z) = abs((vf(valid_z) ./ complex_tap(valid_z) - ...
    vt(valid_z)) ./ z(valid_z));
series_current_reference_kv = results.bus(ti, BASE_KV);
series_current = series_current_pu .* results.baseMVA ./ ...
    (sqrt(3) * series_current_reference_kv);

offline = results.branch(:, BR_STATUS) <= 0;
from_current(offline) = 0;
to_current(offline) = 0;
series_current(offline) = 0;
series_current_pu(offline) = 0;

metadata = resolve_metadata(results, branch_map);
from_name = branch_bus_names(results, results.branch(:, F_BUS));
to_name = branch_bus_names(results, results.branch(:, T_BUS));
report = table((1:nl)', results.branch(:, F_BUS), results.branch(:, T_BUS), ...
    from_name, to_name, results.branch(:, BR_STATUS), ...
    results.branch(:, PF), results.branch(:, QF), ...
    results.branch(:, PT), results.branch(:, QT), ...
    from_terminal_kv, to_terminal_kv, from_current, to_current, ...
    series_current, series_current_pu, series_current_reference_kv, ...
    tap_ratio, results.branch(:, SHIFT), results.branch(:, BR_R), ...
    results.branch(:, BR_X), results.branch(:, BR_B), ...
    results.branch(:, RATE_A), metadata.branch_classification, ...
    metadata.physical_circuit_id, metadata.corridor_name, ...
    metadata.source_circuit_id, metadata.source_branch_index, ...
    'VariableNames', {'branch_index','from_bus','to_bus','from_bus_name', ...
    'to_bus_name','branch_status','pf_mw','qf_mvar','pt_mw','qt_mvar', ...
    'from_terminal_kv','to_terminal_kv','from_terminal_current_kA', ...
    'to_terminal_current_kA','series_current_kA','series_current_pu', ...
    'series_current_reference_kv','tap_ratio','shift_deg','r_pu','x_pu', ...
    'b_pu','rate_a_mva','branch_classification','physical_circuit_id', ...
    'corridor_name','source_circuit_id','source_branch_index'});

if strlength(options.output_file) > 0
    out_dir = fileparts(options.output_file);
    if ~isempty(out_dir) && ~isfolder(out_dir)
        error('compute_branch_currents_kA:MissingOutputDirectory', ...
            'Current-report output directory does not exist: %s', out_dir);
    end
    writetable(report, options.output_file);
end
end

function options = defaults(options)
if ~isfield(options, 'output_file'), options.output_file = ""; end
if ~isfield(options, 'series_impedance_tolerance')
    options.series_impedance_tolerance = 1e-12;
end
options.output_file = string(options.output_file);
validateattributes(options.output_file, {'string'}, {'scalar'});
validateattributes(options.series_impedance_tolerance, {'numeric'}, ...
    {'scalar','nonnegative','finite'});
end

function current = safe_terminal_current(p, q, terminal_kv)
current = nan(size(p));
valid = isfinite(terminal_kv) & terminal_kv > 0;
current(valid) = hypot(p(valid), q(valid)) ./ ...
    (sqrt(3) * terminal_kv(valid));
end

function metadata = resolve_metadata(results, branch_map)
[~, ~, ~, ~, ~, ~, ~, ~, TAP, SHIFT] = idx_brch;
nl = size(results.branch, 1);
metadata = struct( ...
    'branch_classification', repmat("aggregate_equivalent", nl, 1), ...
    'physical_circuit_id', strings(nl, 1), ...
    'corridor_name', strings(nl, 1), ...
    'source_circuit_id', strings(nl, 1), ...
    'source_branch_index', nan(nl, 1));
transformer = results.branch(:, TAP) ~= 0 | results.branch(:, SHIFT) ~= 0;
metadata.branch_classification(transformer) = ...
    "transformer_or_boundary_equivalent";

if isempty(branch_map) && isfield(results, 'userdata') && ...
        isfield(results.userdata, 's11_dlr')
    saved = results.userdata.s11_dlr;
    if isfield(saved, 'physical_circuit_map') && ...
            istable(saved.physical_circuit_map)
        branch_map = saved.physical_circuit_map;
    elseif isfield(saved, 'branch_classification') && ...
            numel(saved.branch_classification) == nl
        metadata.branch_classification = string(saved.branch_classification(:));
        if isfield(saved, 'physical_circuit_id') && ...
                numel(saved.physical_circuit_id) == nl
            metadata.physical_circuit_id = string(saved.physical_circuit_id(:));
        end
        if isfield(saved, 'source_circuit_id') && ...
                numel(saved.source_circuit_id) == nl
            metadata.source_circuit_id = string(saved.source_circuit_id(:));
        end
        if isfield(saved, 'source_branch_index') && ...
                numel(saved.source_branch_index) == nl
            metadata.source_branch_index = saved.source_branch_index(:);
        end
        return;
    end
end

if isempty(branch_map), return; end
if ischar(branch_map) || isstring(branch_map)
    branch_map = readtable(char(branch_map), 'TextType', 'string', ...
        'VariableNamingRule', 'preserve');
end
if ~istable(branch_map) || ~ismember('branch_index', ...
        branch_map.Properties.VariableNames)
    error('compute_branch_currents_kA:InvalidMap', ...
        'BRANCH_MAP must be a table with a branch_index column.');
end

idx = double(branch_map.branch_index);
if any(~isfinite(idx) | idx < 1 | idx > nl | idx ~= fix(idx)) || ...
        numel(unique(idx)) ~= numel(idx)
    error('compute_branch_currents_kA:InvalidMapIndex', ...
        'BRANCH_MAP contains invalid or duplicate branch indices.');
end
copy_string('branch_classification');
copy_string('physical_circuit_id');
copy_string('corridor_name');
copy_string('source_circuit_id');
if ismember('source_branch_index', branch_map.Properties.VariableNames)
    metadata.source_branch_index(idx) = double(branch_map.source_branch_index);
end

    function copy_string(name)
        if ismember(name, branch_map.Properties.VariableNames)
            metadata.(name)(idx) = string(branch_map.(name));
        end
    end
end

function names = branch_bus_names(mpc, bus_ids)
names = "BUS_" + string(bus_ids);
if ~isfield(mpc, 'bus_name'), return; end
[found, idx] = ismember(bus_ids, mpc.bus(:, 1));
names(found) = strtrim(string(mpc.bus_name(idx(found))));
end
