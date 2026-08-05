function out = validate_phase0_interfaces(options)
%VALIDATE_PHASE0_INTERFACES Phase 0 before/after on the 2019 interface targets.
%   Rebuilds the S7 direct-PERFORM scenario path exactly as
%   run_s7_seven_interface_perform_tieline_calibration does for its selected
%   candidate (PERF_GL1_PV1_WM1_B1), then scores the six 2019 scaled scenarios
%   twice: with the case as-is, and with apply_ny_core_phase0_corrections
%   applied to the NY core.
%
%   Written as a separate validator rather than by modifying the S7 runner:
%   that runner hardcodes its base case and sweeps a candidate grid, and it is
%   the project's canonical calibration pipeline.
%
%   Reports the fixed-scale all-hour objective (the S7 2019 baseline is
%   0.489612), train/holdout split, per-interface MAE, PF convergence and
%   branch overloads.

if nargin < 1, options = struct(); end
if ~isfield(options, 'write'), options.write = true; end
nylite = fileparts(mfilename('fullpath'));
case_dir = fileparts(nylite);
addpath(case_dir); addpath(nylite);
define_constants;

scen_file  = fullfile(nylite, 'nyiso_public_scenarios.csv');
frozen_file = fullfile(nylite, 's6_nyiso_zonal_net_injection_targets.csv');
ext_file   = fullfile(nylite, 'ny_external_interface_targets.csv');
tgt_file   = fullfile(nylite, 'nyiso_public_interface_targets.csv');
scale_file = fullfile(nylite, 'nyiso_interface_objective_scales.csv');
train = ["S1_2019_SUMMER_PEAK_PUBLIC"; "S2_2019_WINTER_PEAK_PUBLIC"; ...
         "S4_2019_HIGH_NYC_LI_LOAD_PUBLIC"; "S5_2019_HIGH_TOTAL_EAST_PUBLIC"];

scenarios = readtable(scen_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
frozen = readtable(frozen_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');

base_full = loadcase('npcc_ny_lite_s4_cost_calibration_candidate_v2');
[gsk, ~] = build_perform_npcc_generation_shift_keys(base_full);
params = struct('mode', "perform_scaled", 'gilboa_leeds_scale', 1.0, ...
    'pleasant_wood_scale', 1.0, 'wood_millwood_scale', 1.0, ...
    'lower_hudson_b_fraction', 1.0);
[full, ~] = apply_perform_tieline_calibration(base_full, params);
[core0, ~] = build_ny_only_equivalent_case(full);
[core0, ~] = align_npcc_generation_capacity_to_perform_gsk(core0, gsk);
core1 = apply_ny_core_phase0_corrections(core0, struct('verbose', false));

pfopt = mpoption('verbose', 0, 'out.all', 0);
rows = table();
for v = 1:2
    if v == 1, core = core0; tag = "before"; else, core = core1; tag = "after"; end
    for s = 1:height(scenarios)
        sid = string(scenarios.scenario_id(s));
        tz = frozen(string(frozen.scenario_id) == sid, :);
        mpc = core;
        [mpc, ~] = apply_nyiso_zonal_loads(mpc, sid, 1.0, ...
            struct('preserve_total_ny_load', true));
        [mpc, ~] = apply_perform_generation_allocation(mpc, ...
            tz(:, {'zone', 'target_generation_mw'}), gsk);
        [mpc, ext] = apply_nyiso_external_interface_injections(mpc, sid, ...
            struct('target_file', ext_file));
        mpc = set_internal_reference(mpc, ext.added_gen_index, "J");
        res = runpf(mpc, pfopt);
        if ~res.success
            rows = [rows; table(tag, sid, false, NaN, NaN, NaN, NaN, ...
                strings(1,1), NaN, ...
                'VariableNames', {'variant','scenario_id','pf_success', ...
                'objective','max_abs_residual_mw','min_vm','max_vm', ...
                'worst_overload','n_overload'})]; %#ok<AGROW>
            continue;
        end
        targets = read_public_interface_targets(sid, tgt_file);
        flows = ny_lite_interface_flows(res, ny_lite_interface_definitions(res));
        [J, detail] = interface_target_objective_balanced(flows, targets, ...
            struct('scale_file', scale_file, 'min_scale_mw', 500));
        smax = max(hypot(res.branch(:, PF), res.branch(:, QF)), ...
                   hypot(res.branch(:, PT), res.branch(:, QT)));
        rated = res.branch(:, RATE_A) > 0 & res.branch(:, BR_STATUS) > 0;
        ovr = rated & smax > res.branch(:, RATE_A);
        wname = "";
        if any(ovr)
            [~, wi] = max(smax - res.branch(:, RATE_A) .* rated);
            fi = find(res.bus(:, BUS_I) == res.branch(wi, F_BUS));
            ti = find(res.bus(:, BUS_I) == res.branch(wi, T_BUS));
            wname = sprintf('%s-%s %.0f/%.0f', strtrim(res.bus_name{fi}), ...
                strtrim(res.bus_name{ti}), smax(wi), res.branch(wi, RATE_A));
        end
        rows = [rows; table(tag, sid, true, J, max(abs(detail.residual_mw)), ...
            min(res.bus(:, VM)), max(res.bus(:, VM)), string(wname), sum(ovr), ...
            'VariableNames', {'variant','scenario_id','pf_success','objective', ...
            'max_abs_residual_mw','min_vm','max_vm','worst_overload','n_overload'})]; %#ok<AGROW>
        detail.variant = repmat(tag, height(detail), 1);
        detail.scenario_id = repmat(sid, height(detail), 1);
        if ~exist('alldetail', 'var'), alldetail = detail; else, alldetail = [alldetail; detail]; end %#ok<AGROW>
    end
end

fprintf('\n=== Phase 0 validation on the six 2019 scaled scenarios ===\n');
for v = ["before", "after"]
    r = rows(rows.variant == v, :);
    ok = r.pf_success;
    tr = ismember(r.scenario_id, train);
    fprintf('%-6s  PF %d/%d  all-hour J = %.6f  (train %.6f, holdout %.6f)  overloads %d\n', ...
        v, sum(ok), height(r), sum(r.objective(ok)), ...
        sum(r.objective(ok & tr)), sum(r.objective(ok & ~tr)), sum(r.n_overload(ok)));
end
fprintf('S7 published 2019 all-hour reference: 0.489612\n\n');
fprintf('per-interface MAE (MW)\n%-20s %10s %10s\n', 'interface', 'before', 'after');
ifn = unique(alldetail.interface_name, 'stable');
for k = 1:numel(ifn)
    b = alldetail(alldetail.interface_name == ifn(k) & alldetail.variant == "before", :);
    a = alldetail(alldetail.interface_name == ifn(k) & alldetail.variant == "after", :);
    fprintf('%-20s %10.1f %10.1f\n', ifn(k), mean(abs(b.residual_mw), 'omitnan'), ...
        mean(abs(a.residual_mw), 'omitnan'));
end

if options.write
    writetable(rows, fullfile(nylite, 'phase0_validation_summary.csv'));
    writetable(alldetail, fullfile(nylite, 'phase0_validation_residuals.csv'));
end
out = struct('summary', rows, 'residuals', alldetail);
end

function mpc = set_internal_reference(mpc, external_idx, zone_name)
% Replicated from run_s7_seven_interface_perform_tieline_calibration so the
% scenario build path is identical.
define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
[mapped, bi] = ismember(mpc.gen(:, GEN_BUS), mpc.bus(:, BUS_I));
zones = strings(size(mpc.gen, 1), 1);
zones(mapped) = string(mpc.userdata.nyiso_physical_zone(bi(mapped)));
mask = mpc.gen(:, GEN_STATUS) > 0 & zones == zone_name;
mask(external_idx) = false;
idx = find(mask);
if isempty(idx), error('No reference generator is available in zone %s.', zone_name); end
q_range = mpc.gen(idx, QMAX) - mpc.gen(idx, QMIN);
if any(q_range > 1e-6), idx = idx(q_range > 1e-6); end
[~, k] = max(mpc.gen(idx, PMAX) - mpc.gen(idx, PG));
mpc = set_scenario_reference_bus(mpc, idx(k), struct('require_external', false));
end
