function [mpc, report] = apply_s11_external_schedules(mpc, scenario_id, options)
%APPLY_S11_EXTERNAL_SCHEDULES Add fixed-P, constrained-Q public boundaries.

if nargin < 2 || isempty(scenario_id)
    scenario_id = "S1_2025_SUMMER_PEAK_PUBLIC";
end
if nargin < 3, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'ny_external_interface_targets.csv');
end
if ~isfield(options, 'use_raw_public_scale'), options.use_raw_public_scale = true; end
if ~isfield(options, 'p_tolerance_mw'), options.p_tolerance_mw = 1e-3; end
if ~isfield(options, 'q_mode'), options.q_mode = "fixed_zero"; end
if ~isfield(options, 'q_band_mvar'), options.q_band_mvar = 0; end
define_constants;

targets = readtable(options.target_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
targets = targets(string(targets.scenario_id) == string(scenario_id), :);
if isempty(targets)
    error('apply_s11_external_schedules:ScenarioRows', ...
        'No public external schedules found for %s.', string(scenario_id));
end
mpc = ensure_generator_metadata(mpc);
rows = table();
for k = 1:height(targets)
    bus_id = double(targets.ny_boundary_bus(k));
    bi = find(mpc.bus(:, BUS_I) == bus_id, 1);
    if isempty(bi)
        error('apply_s11_external_schedules:BoundaryBus', ...
            'Boundary bus %.0f is absent from the 49-bus core.', bus_id);
    end
    gamma = double(targets.scale_factor_gamma(k));
    p = double(targets.target_flow_mw(k));
    if options.use_raw_public_scale
        if ~isfinite(gamma) || abs(gamma) < eps
            error('apply_s11_external_schedules:Scale', ...
                'Invalid public scaling factor for row %d.', k);
        end
        p = p / gamma;
    end
    q = 0;
    if lower(string(options.q_mode)) == "narrow_heuristic"
        q = double(targets.target_q_mvar(k));
        if options.use_raw_public_scale, q = q / gamma; end
    elseif lower(string(options.q_mode)) ~= "fixed_zero"
        error('apply_s11_external_schedules:QMode', ...
            'q_mode must be fixed_zero or narrow_heuristic.');
    end
    qmin = q - options.q_band_mvar;
    qmax = q + options.q_band_mvar;
    vg = double(targets.v_setpoint(k));
    new = zeros(1, size(mpc.gen,2));
    new(GEN_BUS) = bus_id; new(PG) = p; new(QG) = q;
    new(QMAX) = qmax; new(QMIN) = qmin; new(VG) = vg;
    new(MBASE) = mpc.baseMVA; new(GEN_STATUS) = 1;
    new(PMAX) = p + options.p_tolerance_mw;
    new(PMIN) = p - options.p_tolerance_mw;
    mpc.gen = [mpc.gen; new];
    mpc.gencost = [mpc.gencost; default_cost(size(mpc.gencost,2))];
    mpc.genfuel{end+1,1} = 'external_schedule';
    mpc.gentype{end+1,1} = 'EX';
    added_index = size(mpc.gen,1);
    row = table(string(scenario_id), string(targets.external_interface_name(k)), ...
        bus_id, p, q, qmin, qmax, added_index, ...
        string(options.q_mode), logical(options.use_raw_public_scale), ...
        string(targets.note(k)), ...
        'VariableNames', {'scenario_id','external_interface_name','ny_boundary_bus', ...
        'scheduled_p_mw','scheduled_q_mvar','qmin_mvar','qmax_mvar', ...
        'added_gen_index','q_mode','raw_public_scale','source_note'});
    rows = append_table(rows, row);
end
if ~isfield(mpc, 'userdata'), mpc.userdata = struct(); end
if ~isfield(mpc.userdata, 'ny_only_equivalent')
    mpc.userdata.ny_only_equivalent = struct();
end
mpc.userdata.ny_only_equivalent.external_equivalent_generators = rows;
if ~isfield(mpc.userdata, 's11'), mpc.userdata.s11 = struct(); end
mpc.userdata.s11.external_schedule = struct('rows', rows, ...
    'q_policy', char(options.q_mode), ...
    'q_band_mvar', options.q_band_mvar, ...
    'public_scale', ternary(options.use_raw_public_scale, 'raw', 's7_similarity'));
report = rows;
end

function mpc = ensure_generator_metadata(mpc)
ncol = max(21, size(mpc.gen,2));
if size(mpc.gen,2) < ncol, mpc.gen(:,end+1:ncol) = 0; end
if ~isfield(mpc,'gencost') || isempty(mpc.gencost)
    mpc.gencost = repmat(default_cost(7), size(mpc.gen,1), 1);
elseif size(mpc.gencost,1) ~= size(mpc.gen,1)
    error('apply_s11_external_schedules:GenCostAlignment', ...
        'gencost is not aligned with gen.');
end
if ~isfield(mpc,'genfuel'), mpc.genfuel = repmat({'unknown'},size(mpc.gen,1),1); end
if ~isfield(mpc,'gentype'), mpc.gentype = repmat({'UN'},size(mpc.gen,1),1); end
mpc.genfuel = cellstr(string(mpc.genfuel(:)));
mpc.gentype = cellstr(string(mpc.gentype(:)));
end

function row = default_cost(width)
width = max(width,7);
row = zeros(1,width);
row(1:7) = [2 0 0 2 0 0 0];
end

function out = append_table(out, row)
if isempty(out), out = row; else, out = [out; row]; end
end

function value = ternary(condition, yes, no)
if condition, value = yes; else, value = no; end
end
