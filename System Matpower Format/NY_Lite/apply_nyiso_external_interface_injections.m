function [mpc, report] = apply_nyiso_external_interface_injections(mpc, scenario_id, options)
%APPLY_NYISO_EXTERNAL_INTERFACE_INJECTIONS Add boundary equivalent generators.
%   target_flow_mw > 0 means import into the NY subsystem.

if nargin < 2 || isempty(scenario_id), scenario_id = "S1_MEASURED_BOUNDARY"; end
if nargin < 3, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'ny_external_interface_targets.csv');
end
if ~isfield(options, 'p_tolerance_mw'), options.p_tolerance_mw = 1e-3; end
if ~isfield(options, 'q_tolerance_mvar'), options.q_tolerance_mvar = 1e-3; end
if ~isfield(options, 'default_q_abs_limit_mvar'), options.default_q_abs_limit_mvar = 500; end

if exist(options.target_file, 'file') ~= 2
    build_ny_external_interface_targets();
end
targets = readtable(options.target_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
targets = targets(strcmp(string(targets.scenario_id), string(scenario_id)), :);
if height(targets) == 0
    error('apply_nyiso_external_interface_injections:MissingScenario', ...
        'No external interface targets found for scenario %s.', string(scenario_id));
end

define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
added = table();
for k = 1:height(targets)
    bus_id = numeric_value(targets.ny_boundary_bus(k));
    bus_idx = find(mpc.bus(:, BUS_I) == bus_id, 1);
    if isempty(bus_idx)
        error('apply_nyiso_external_interface_injections:MissingBoundaryBus', ...
            'Boundary bus %.0f is not present in the NY-only case.', bus_id);
    end

    p_target = numeric_value(targets.target_flow_mw(k));
    q_target = table_value_or_default(targets, k, 'target_q_mvar', 0);
    qmin = table_value_or_default(targets, k, 'qmin_mvar', -options.default_q_abs_limit_mvar);
    qmax = table_value_or_default(targets, k, 'qmax_mvar', options.default_q_abs_limit_mvar);
    vg = table_value_or_default(targets, k, 'v_setpoint', mpc.bus(bus_idx, VM));
    q_mode = "limited_q_support";
    if ismember('q_mode', targets.Properties.VariableNames)
        q_mode = lower(string(targets.q_mode(k)));
    end

    if strcmp(q_mode, "fixed_q")
        qmin = q_target - options.q_tolerance_mvar;
        qmax = q_target + options.q_tolerance_mvar;
    elseif strcmp(q_mode, "no_q_support")
        q_target = 0;
        qmin = 0;
        qmax = 0;
    end

    ncol = max(21, size(mpc.gen, 2));
    new_gen = zeros(1, ncol);
    new_gen(GEN_BUS) = bus_id;
    new_gen(PG) = p_target;
    new_gen(QG) = q_target;
    new_gen(QMAX) = qmax;
    new_gen(QMIN) = qmin;
    new_gen(VG) = vg;
    new_gen(MBASE) = mpc.baseMVA;
    new_gen(GEN_STATUS) = 1;
    new_gen(PMAX) = p_target + options.p_tolerance_mw;
    new_gen(PMIN) = p_target - options.p_tolerance_mw;
    mpc.gen = [mpc.gen; new_gen];

    if isfield(mpc, 'gencost') && ~isempty(mpc.gencost)
        cost = zeros(1, size(mpc.gencost, 2));
        cost(1:min(end, 7)) = [2, 0, 0, 2, 0, 0, 0];
        mpc.gencost = [mpc.gencost; cost];
    end

    row = targets(k, :);
    row.added_gen_index = size(mpc.gen, 1);
    if height(added) == 0
        added = row;
    else
        added = [added; row]; %#ok<AGROW>
    end
end

mpc.userdata.ny_only_equivalent.external_equivalent_generators = added;
report = added;
end

function value = table_value_or_default(tbl, row, name, default_value)
if ismember(name, tbl.Properties.VariableNames)
    value = numeric_value(tbl.(name)(row));
    if isfinite(value), return; end
end
value = default_value;
end

function value = numeric_value(value)
if iscell(value), value = value{1}; end
if isstring(value) || ischar(value)
    value = str2double(value);
end
value = double(value);
end
