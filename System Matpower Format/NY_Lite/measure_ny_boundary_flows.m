function rows = measure_ny_boundary_flows(mpc, scenario_id, options)
%MEASURE_NY_BOUNDARY_FLOWS Measure flows crossing NY to non-NY buses.
%   Positive p_import_mw/q_import_mvar means injection into the NY subsystem.

if nargin < 1 || isempty(mpc)
    mpc = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
elseif ischar(mpc) || isstring(mpc)
    mpc = loadcase(char(mpc));
end
if nargin < 2 || isempty(scenario_id), scenario_id = "S1_MEASURED_BOUNDARY"; end
if nargin < 3, options = struct(); end
if ~isfield(options, 'run_pf_if_needed'), options.run_pf_if_needed = true; end

helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);

define_constants;
if size(mpc.branch, 2) < QT
    if ~options.run_pf_if_needed
        error('measure_ny_boundary_flows:MissingFlowColumns', ...
            'Branch flow columns are missing. Run PF/OPF first.');
    end
    mpopt = mpoption('verbose', 0, 'out.all', 0);
    mpc = runpf(mpc, mpopt);
    if ~mpc.success
        error('measure_ny_boundary_flows:PowerFlowFailed', ...
            'Could not solve PF before measuring boundary flows.');
    end
end

mpc = attach_nyiso_zone_metadata(mpc);
ny_mask = mpc.userdata.nyiso_zone_id > 0;
rows = table();
for b = 1:size(mpc.branch, 1)
    if mpc.branch(b, BR_STATUS) <= 0, continue; end
    fb = mpc.branch(b, F_BUS);
    tb = mpc.branch(b, T_BUS);
    fi = find(mpc.bus(:, BUS_I) == fb, 1);
    ti = find(mpc.bus(:, BUS_I) == tb, 1);
    if isempty(fi) || isempty(ti) || ~xor(ny_mask(fi), ny_mask(ti))
        continue;
    end

    if ny_mask(fi)
        ny_idx = fi;
        external_idx = ti;
        ny_side = "from";
        p_import = -mpc.branch(b, PF);
        q_import = -mpc.branch(b, QF);
    else
        ny_idx = ti;
        external_idx = fi;
        ny_side = "to";
        p_import = -mpc.branch(b, PT);
        q_import = -mpc.branch(b, QT);
    end

    row = table(string(scenario_id), b, mpc.bus(ny_idx, BUS_I), ...
        string(bus_name(mpc, ny_idx)), string(mpc.userdata.nyiso_zone{ny_idx}), ...
        string(mpc.userdata.nyiso_zone_name{ny_idx}), ...
        mpc.bus(external_idx, BUS_I), string(bus_name(mpc, external_idx)), ...
        ny_side, p_import, q_import, mpc.bus(ny_idx, VM), ...
        mpc.branch(b, RATE_A), ...
        'VariableNames', {'scenario_id','source_branch','ny_boundary_bus', ...
            'ny_boundary_bus_name','nyiso_zone_letter','nyiso_zone_name', ...
            'external_bus','external_bus_name','ny_side','p_import_mw', ...
            'q_import_mvar','ny_vm_pu','source_branch_rate_a_mva'});
    rows = [rows; row]; %#ok<AGROW>
end
end

function name = bus_name(mpc, idx)
if isfield(mpc, 'bus_name') && numel(mpc.bus_name) >= idx
    name = strtrim(mpc.bus_name{idx});
else
    name = sprintf('BUS_%d', mpc.bus(idx, 1));
end
end
