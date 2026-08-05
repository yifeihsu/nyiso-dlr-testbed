function targets = build_perform_zonal_q_capability_targets(mpc, options)
%BUILD_PERFORM_ZONAL_Q_CAPABILITY_TARGETS Scale PERFORM native Q envelopes.
%   Aggregates online native PERFORM generators by NYISO zone, excludes
%   import/reference records, and scales each QMIN/QMAX envelope by the ratio
%   of retained-model zonal PMAX to PERFORM zonal PMAX.

if nargin < 1 || isempty(mpc)
    mpc = loadcase('npcc_ny_lite_s7_seven_interface_perform_direct_candidate');
elseif ischar(mpc) || isstring(mpc)
    mpc = loadcase(char(mpc));
end
if nargin < 2, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
workspace_dir = fileparts(fileparts(helper_dir));
if ~isfield(options, 'perform_case_dir')
    options.perform_case_dir = fullfile(workspace_dir, 'PERFORM', ...
        'On Peak 2019 v23_Perform_NY', 'On Peak 2019 v23');
end
if ~isfield(options, 'perform_aux_dir')
    options.perform_aux_dir = fullfile(workspace_dir, 'PERFORM', ...
        'Auxilliary_Perform_NY');
end

define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
addpath(options.perform_case_dir);
perform = nyiso_On_Peak_v23_shunts_as_z_load;
perform_bus_zone = perform_nyiso_zone_letters(perform, perform.bus(:, BUS_I));
[gen_mapped, gen_bus_idx] = ismember(perform.gen(:, GEN_BUS), ...
    perform.bus(:, BUS_I));
perform_gen_zone = strings(size(perform.gen, 1), 1);
perform_gen_zone(gen_mapped) = perform_bus_zone(gen_bus_idx(gen_mapped));
fuel = lower(strtrim(string(perform.genfuel(:))));
perform_native = perform.gen(:, GEN_STATUS) > 0 & ...
    ~ismember(fuel, ["import", "reference"]) & perform_gen_zone ~= "";

[model_mapped, model_bus_idx] = ismember(mpc.gen(:, GEN_BUS), mpc.bus(:, BUS_I));
model_gen_zone = strings(size(mpc.gen, 1), 1);
model_gen_zone(model_mapped) = string( ...
    mpc.userdata.nyiso_physical_zone(model_bus_idx(model_mapped)));
model_online = mpc.gen(:, GEN_STATUS) > 0 & model_gen_zone ~= "";

zones = string(('A':'K')');
targets = table();
for z = 1:numel(zones)
    pi = perform_native & perform_gen_zone == zones(z);
    mi = model_online & model_gen_zone == zones(z);
    perform_pmax = sum(perform.gen(pi, PMAX));
    perform_qmin = sum(perform.gen(pi, QMIN));
    perform_qmax = sum(perform.gen(pi, QMAX));
    model_pmax = sum(mpc.gen(mi, PMAX));
    model_qmin = sum(mpc.gen(mi, QMIN));
    model_qmax = sum(mpc.gen(mi, QMAX));
    if perform_pmax > 0
        scale = model_pmax / perform_pmax;
        target_qmin = perform_qmin * scale;
        target_qmax = perform_qmax * scale;
    else
        scale = NaN;
        target_qmin = 0;
        target_qmax = 0;
    end
    row = table(zones(z), sum(pi), perform_pmax, perform_qmin, perform_qmax, ...
        perform_qmax - perform_qmin, ...
        (perform_qmax - perform_qmin) / max(perform_pmax, eps), ...
        sum(pi & perform.gen(:, QMAX) >= 900), model_pmax, model_qmin, ...
        model_qmax, scale, target_qmin, target_qmax, ...
        "PERFORM_2019_on_peak_native_generators_scaled_by_zonal_PMAX", ...
        'VariableNames', {'zone','perform_online_native_gen_count', ...
        'perform_pmax_mw','perform_qmin_mvar','perform_qmax_mvar', ...
        'perform_q_range_mvar','perform_q_range_per_pmax', ...
        'perform_qmax_ge_900_count','model_pmax_mw','model_current_qmin_mvar', ...
        'model_current_qmax_mvar','pmax_scale_factor', ...
        'target_qmin_mvar','target_qmax_mvar','source'});
    targets = append_table(targets, row);
end
end

function out = append_table(out, row)
if isempty(out), out = row; else, out = [out; row]; end
end
