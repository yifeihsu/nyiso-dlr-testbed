function out = validate_s13_phase1a_smoke(options)
%VALIDATE_S13_PHASE1A_SMOKE Basic AC smoke test on the inherited S7 snapshot.
%   This is not a 2019 same-snapshot, dispatch-closure, or promotion test.

if nargin < 1, options = struct(); end
if ~isfield(options, 'write_outputs'), options.write_outputs = true; end

helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
define_constants;

base = loadcase('npcc_ny_lite_s7_seven_interface_perform_direct_candidate');
base = apply_ny_core_phase0_corrections(base, struct( ...
    'fit_reactance', false, 'verbose', false));
checkpoint = build_s13_phase1a_candidate(struct( ...
    'write_outputs', false, 'verbose', false));
candidate = checkpoint.candidate;

cases = {base, candidate};
case_id = ["s7_phase0_parent"; "s13_phase1a_candidate"];
model_role = ["structural_parent"; "unpromoted_s13_candidate"];
summary = table();
pfopt = mpoption('verbose', 0, 'out.all', 0);
qopt = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 1);

for k = 1:2
    res = runpf(cases{k}, pfopt);
    resq = runpf(cases{k}, qopt);
    online = res.gen(:, GEN_STATUS) > 0;
    q_above = max(res.gen(:, QG) - res.gen(:, QMAX), 0);
    q_below = max(res.gen(:, QMIN) - res.gen(:, QG), 0);
    q_violation = max(q_above, q_below);
    q_violation(~online) = 0;
    q_violation_count = nnz(q_violation > 1e-6);
    max_q_violation_mvar = max(q_violation, [], 'omitnan');
    definitions = ny_lite_interface_definitions(res, struct('force_legacy', true));
    flows = ny_lite_interface_flows(res, definitions);
    central_east_mw = get_flow(flows, "Central_East");
    total_east_legacy_mw = get_flow(flows, "Total_East_proxy");
    eg_coopers_rt_e_to_g_mw = NaN;
    if k == 2
        rows = cases{k}.userdata.npcc_perform_overlay.physical_branch_rows;
        % Source orientation is Rock Tavern (G) -> Coopers Corner (E), so
        % eastbound E -> G is the negative from-end sum.
        eg_coopers_rt_e_to_g_mw = -sum(res.branch(rows(5:6), PF));
    end
    active_loss_mw = sum(res.branch(:, PF) + res.branch(:, PT));
    row = table(case_id(k), model_role(k), ...
        "inherited_s7_snapshot_smoke_not_2019", size(res.bus, 1), ...
        size(res.branch, 1), size(res.gen, 1), logical(res.success), ...
        logical(resq.success), q_violation_count, max_q_violation_mvar, ...
        min(res.bus(:, VM)), max(res.bus(:, VM)), ...
        active_loss_mw, central_east_mw, total_east_legacy_mw, ...
        eg_coopers_rt_e_to_g_mw, ...
        "No promotion claim; re-derived 2019 dispatch and paired S12 tests pending", ...
        'VariableNames', {'case_id','model_role','snapshot_scope','bus_count', ...
        'branch_count','generator_count','standard_pf_success', ...
        'q_limit_pf_success','standard_pf_q_limit_violation_count', ...
        'max_standard_pf_q_limit_violation_mvar','min_vm_pu','max_vm_pu', ...
        'active_loss_mw', ...
        'central_east_legacy_flow_mw','total_east_legacy_flow_mw', ...
        'eg_coopers_rt_e_to_g_mw','interpretation'});
    summary = [summary; row]; %#ok<AGROW>
end

if options.write_outputs
    ny_lite_writetable_lf(summary, ...
        fullfile(helper_dir, 's13_phase1a_smoke_validation.csv'));
end
out = struct('summary', summary, ...
    'standard_pf_both_pass', all(summary.standard_pf_success), ...
    'q_limit_pf_both_pass', all(summary.q_limit_pf_success), ...
    'promotion_eligible', false);
end

function value = get_flow(flows, name)
idx = find(string({flows.interface_name})' == name & ...
    string({flows.result_type})' == "subpath", 1);
if isempty(idx), value = NaN; else, value = flows(idx).flow_mw; end
end
