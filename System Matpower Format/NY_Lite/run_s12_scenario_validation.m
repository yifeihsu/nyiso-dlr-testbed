function out = run_s12_scenario_validation(options)
%RUN_S12_SCENARIO_VALIDATION Six 2019 scaled scenarios on the S12 oracle.
%   Builds each scenario on the PERFORM retention-core case with fuel-mix
%   seasonal priors and 2019 P-32 external schedules, balances with the
%   Marcy reference, and optionally applies a bounded zonal DC-inverse
%   closure against the seven S12 interface operators. Forward (prior-only)
%   and closed residuals are both reported; the closed objective uses the
%   fixed 2019 interface scales for comparability with the S7 baseline.
%
%   Outputs: s12_scenario_summary.csv, s12_scenario_interface_validation.csv,
%   s12_zonal_closure_movement.csv.

if nargin < 1, options = struct(); end
if ~isfield(options, 'write_outputs'), options.write_outputs = true; end
if ~isfield(options, 'do_closure'), options.do_closure = true; end
if ~isfield(options, 'trust_mw'), options.trust_mw = 1090; end
if ~isfield(options, 'reg_weight'), options.reg_weight = 0.05; end
if ~isfield(options, 'reg_scale_mw'), options.reg_scale_mw = 1000; end
if ~isfield(options, 'closure_iterations'), options.closure_iterations = 2; end

nylite = fileparts(mfilename('fullpath'));
addpath(nylite); addpath(fileparts(nylite));
define_constants;

ws = load(fullfile(nylite, 's12_case.mat'));
s12 = ws.s12;
nRb = size(s12.bus, 1); ngen = size(s12.gen, 1);
areas = s12.userdata.s12_zone_area_codes(:);
letters = string(s12.userdata.s12_zone_letters(:));
PB = s12.userdata.s12_zone_base_load_p;
QB = s12.userdata.s12_zone_base_load_q;
op = s12.userdata.s12_interface_operators;
ext = s12.userdata.s12_external_groups;
ifc_names = unique(op.interface_name, 'stable');

scen = readtable(fullfile(nylite, 'nyiso_public_scenarios.csv'), 'TextType', 'string', 'VariableNamingRule', 'preserve');
ltab = readtable(fullfile(nylite, 'ny_zonal_load_targets.csv'), 'TextType', 'string', 'VariableNamingRule', 'preserve');
itab = readtable(fullfile(nylite, 'nyiso_public_interface_targets.csv'), 'TextType', 'string', 'VariableNamingRule', 'preserve');
priors = readtable(fullfile(nylite, 's12_unit_dispatch_priors.csv'), 'TextType', 'string', 'VariableNamingRule', 'preserve');
scales = readtable(fullfile(nylite, 'nyiso_interface_objective_scales.csv'), 'TextType', 'string', 'VariableNamingRule', 'preserve');
cache = fullfile(nylite, 'nyiso_public_cache');

is_boundary = false(ngen, 1); is_boundary(ext.gen_index) = true;
ref_gen = find(string(s12.genfuel) == "reference", 1);
slack_bus = s12.gen(ref_gen, GEN_BUS);
gen_area = s12.bus(s12.gen(:, GEN_BUS), BUS_AREA);
[~, gen_zone_idx] = ismember(gen_area, areas);
mpopt0 = mpoption('verbose', 0, 'out.all', 0);
mpoptq = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 1);

results = table(); ifc_rows = table(); move_rows = table();
J_fwd = 0; J_closed = 0;
for s = 1:height(scen)
    sid = scen.scenario_id(s);
    gamma = scen.scale_factor_gamma(s);
    ts = datetime(scen.timestamp(s), 'InputFormat', 'yyyy-MM-dd HH:mm');
    mpc = s12;

    % zonal loads from scaled public targets via zone-labeled components
    PDv = zeros(nRb, 1); QDv = zeros(nRb, 1);
    for z = 1:numel(areas)
        lt = ltab.target_load_mw(ltab.scenario_id == sid & ltab.nyiso_zone_letter == letters(z));
        sz = lt(1) / sum(PB(:, z));
        PDv = PDv + sz * PB(:, z);
        QDv = QDv + sz * QB(:, z);
    end
    mpc.bus(:, PD) = PDv; mpc.bus(:, QD) = QDv;

    % external schedules from cached 2019 P-32
    p32 = readtable(fullfile(cache, [datestr(ts, 'yyyymm') '_ExternalLimitsFlows'], ...
        [datestr(ts, 'yyyymmdd') 'ExternalLimitsFlows.csv']), ...
        'TextType', 'string', 'VariableNamingRule', 'preserve');
    pts = datetime(p32.Timestamp, 'InputFormat', 'MM/dd/yyyy HH:mm');
    ut = unique(pts); [~, ci] = min(abs(ut - ts)); selr = pts == ut(ci);
    sched = containers.Map('KeyType', 'char', 'ValueType', 'double');
    for r = find(selr)'
        sched(char(p32.("Interface Name")(r))) = p32.("Flow (MWH)")(r);
    end
    hq_extra = 0;
    if isKey(sched, 'SCH - HQ_CEDARS'), hq_extra = sched('SCH - HQ_CEDARS'); end
    ext_total = 0;
    for gname = unique(ext.p32_interface_name, 'stable')'
        rows = ext(ext.p32_interface_name == gname, :);
        target = sched(char(gname));
        if gname == "SCH - HQ - NY", target = target + hq_extra; end
        target = gamma * target;
        wgt = abs(rows.snapshot_pg_mw); wgt = wgt / sum(wgt);
        for k = 1:height(rows)
            gi = rows.gen_index(k);
            mpc.gen(gi, PG) = target * wgt(k);
            mpc.gen(gi, PMIN) = mpc.gen(gi, PG) - 0.001;
            mpc.gen(gi, PMAX) = mpc.gen(gi, PG) + 0.001;
            mpc.gen(gi, GEN_STATUS) = 1;
            mpc.gen(gi, QG) = gamma * rows.snapshot_qg_mvar(k);
            mpc.gen(gi, QMIN) = mpc.gen(gi, QG); mpc.gen(gi, QMAX) = mpc.gen(gi, QG);
        end
        ext_total = ext_total + target;
    end

    % internal dispatch and commitment from seasonal prior
    pri = priors(priors.scenario_id == sid, :);
    pg = zeros(ngen, 1);
    pg(pri.gen_index) = pri.prior_mw_scaled;
    internal = ~is_boundary; internal(ref_gen) = false;
    mpc.gen(internal, GEN_STATUS) = double(pg(internal) > 0.001);
    mpc.gen(internal, PG) = pg(internal);
    mpc.gen(ref_gen, GEN_STATUS) = 1; mpc.gen(ref_gen, PG) = 0;
    mpc.gen(ref_gen, [PMIN PMAX QMIN QMAX]) = [-9999 9999 -9999 9999];
    on = mpc.gen(:, GEN_STATUS) > 0;
    mpc.gen(on, VG) = s12.bus(mpc.gen(on, GEN_BUS), VM);
    mpc.bus(:, BUS_TYPE) = 1;
    mpc.bus(unique(mpc.gen(on & ~is_boundary, GEN_BUS)), BUS_TYPE) = 2;
    mpc.bus(slack_bus, BUS_TYPE) = 3;

    [mpc, res, pickup] = balance_with_reference(mpc, ref_gen, internal, mpopt0);
    fwd = interface_flows(res, op, ifc_names);
    targ = zeros(numel(ifc_names), 1);
    scl = zeros(numel(ifc_names), 1);
    for m = 1:numel(ifc_names)
        tt = itab.target_flow_mw(itab.scenario_id == sid & itab.interface_name == ifc_names(m));
        targ(m) = tt(1);
        sc = scales.fixed_scale_mw(scales.interface_name == ifc_names(m));
        scl(m) = sc(1);
    end
    J_fwd = J_fwd + sum(((fwd - targ) ./ scl).^2);

    % bounded zonal DC-inverse closure
    dz_total = zeros(numel(areas), 1);
    if options.do_closure
        for it = 1:options.closure_iterations
            r0 = interface_flows(res, op, ifc_names) - targ;
            zw = cell(numel(areas), 1);
            zprior = zeros(numel(areas), 1);
            for z = 1:numel(areas)
                zg = find(internal & mpc.gen(:, GEN_STATUS) > 0 & gen_zone_idx == z);
                w = mpc.gen(zg, PG);
                if sum(w) > 0, w = w / sum(w); end
                zw{z} = [zg w];
                zprior(z) = sum(mpc.gen(zg, PG));
            end
            H = makePTDF(mpc.baseMVA, mpc.bus, mpc.branch, slack_bus);
            S = zeros(numel(ifc_names), numel(areas));
            for m = 1:numel(ifc_names)
                orows = op(op.interface_name == ifc_names(m), :);
                for z = 1:numel(areas)
                    if isempty(zw{z}) || size(zw{z}, 1) == 0, continue; end
                    gb = mpc.gen(zw{z}(:, 1), GEN_BUS);
                    S(m, z) = sum(orows.sign .* (H(orows.reduced_branch, gb) * zw{z}(:, 2)));
                end
            end
            C = [S ./ scl; sqrt(options.reg_weight) * eye(numel(areas)) / options.reg_scale_mw];
            dvec = [r0 ./ scl; zeros(numel(areas), 1)];
            lb = max(-options.trust_mw, -zprior);
            ub = options.trust_mw * ones(numel(areas), 1);
            lb(zprior == 0) = 0; ub(zprior == 0) = 0;
            dz = lsqlin(C, -dvec, [], [], ones(1, numel(areas)), 0, lb, ub, [], ...
                optimoptions('lsqlin', 'Display', 'off'));
            for z = 1:numel(areas)
                if isempty(zw{z}) || dz(z) == 0, continue; end
                gi = zw{z}(:, 1);
                mpc.gen(gi, PG) = max(mpc.gen(gi, PG) + dz(z) * zw{z}(:, 2), 0);
            end
            dz_total = dz_total + dz;
            [mpc, res, pickup] = balance_with_reference(mpc, ref_gen, internal, mpopt0);
        end
    end
    resq = runpf(mpc, mpoptq);
    q_ok = resq.success;
    use = res; if q_ok, use = resq; end
    fin = interface_flows(use, op, ifc_names);
    J_closed = J_closed + sum(((fin - targ) ./ scl).^2);

    for m = 1:numel(ifc_names)
        ifc_rows = [ifc_rows; table(sid, ifc_names(m), targ(m), fwd(m), ...
            fwd(m) - targ(m), fin(m), fin(m) - targ(m), scl(m), ...
            'VariableNames', {'scenario_id', 'interface_name', 'target_flow_mw', ...
            'forward_flow_mw', 'forward_residual_mw', 'closed_flow_mw', ...
            'closed_residual_mw', 'objective_scale_mw'})]; %#ok<AGROW>
    end
    vm = use.bus(:, VM);
    results = [results; table(sid, res.success, q_ok, sum(mpc.bus(:, PD)), ...
        ext_total, sum(use.gen(use.gen(:, GEN_STATUS) > 0, PG)), pickup, ...
        sum(abs(dz_total)), 100 * sum(abs(dz_total)) / sum(mpc.bus(:, PD)), ...
        min(vm), max(vm), ...
        'VariableNames', {'scenario_id', 'pf_success', 'q_limit_pf_success', ...
        'load_mw', 'external_mw', 'generation_mw', 'final_ref_pickup_mw', ...
        'closure_movement_mw', 'closure_movement_pct_of_load', ...
        'min_vm_pu', 'max_vm_pu'})]; %#ok<AGROW>
    mrow = table(repmat(sid, numel(areas), 1), letters, dz_total, ...
        'VariableNames', {'scenario_id', 'zone', 'closure_delta_mw'});
    move_rows = [move_rows; mrow]; %#ok<AGROW>
    fprintf('%s: PF=%d QPF=%d closure |dz|=%.0f MW pickup=%.2f\n', ...
        sid, res.success, q_ok, sum(abs(dz_total)), pickup);
end

if options.write_outputs
    writetable(results, fullfile(nylite, 's12_scenario_summary.csv'));
    writetable(ifc_rows, fullfile(nylite, 's12_scenario_interface_validation.csv'));
    writetable(move_rows, fullfile(nylite, 's12_zonal_closure_movement.csv'));
end

fprintf('\nPer-interface MAE (MW): forward -> closed\n');
for m = 1:numel(ifc_names)
    rr = ifc_rows(ifc_rows.interface_name == ifc_names(m), :);
    fprintf('  %-18s %8.1f -> %8.1f (max %8.1f -> %8.1f)\n', ifc_names(m), ...
        mean(abs(rr.forward_residual_mw)), mean(abs(rr.closed_residual_mw)), ...
        max(abs(rr.forward_residual_mw)), max(abs(rr.closed_residual_mw)));
end
fprintf('all-hour objective (fixed 2019 scales): forward %.6f, closed %.6f\n', J_fwd, J_closed);
fprintf('S7 direct-PERFORM all-hour reference: 0.489612\n');

out = struct('model_role', 'reference_oracle', ...
    'promotion_eligible', false, 'summary', results, ...
    'interfaces', ifc_rows, 'movement', move_rows, ...
    'objective_forward', J_fwd, 'objective_closed', J_closed, ...
    'outputs_written', logical(options.write_outputs));
end

function [mpc, res, pickup] = balance_with_reference(mpc, ref_gen, internal, mpopt)
define_constants;
pickup = nan;
for it = 1:5
    res = runpf(mpc, mpopt);
    if ~res.success, return; end
    pickup = res.gen(ref_gen, PG) - mpc.gen(ref_gen, PG);
    pickup = res.gen(ref_gen, PG);
    if abs(pickup) < 1, return; end
    adj = internal & mpc.gen(:, GEN_STATUS) > 0;
    w = mpc.gen(adj, PG); w = w / sum(w);
    mpc.gen(adj, PG) = max(mpc.gen(adj, PG) + pickup * w, 0);
end
end

function f = interface_flows(res, op, ifc_names)
define_constants;
f = zeros(numel(ifc_names), 1);
for m = 1:numel(ifc_names)
    orows = op(op.interface_name == ifc_names(m), :);
    f(m) = sum(orows.sign .* res.branch(orows.reduced_branch, PF));
end
end
