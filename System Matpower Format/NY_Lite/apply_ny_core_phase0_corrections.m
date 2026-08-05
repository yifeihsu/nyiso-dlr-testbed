function [mpc, report] = apply_ny_core_phase0_corrections(mpc, options)
%APPLY_NY_CORE_PHASE0_CORRECTIONS Phase 0 corrections for the NPCC NY core.
%   [MPC, REPORT] = APPLY_NY_CORE_PHASE0_CORRECTIONS(MPC) rewrites the NY
%   zone-boundary equivalent branches of an NPCC-derived NY-Lite case so their
%   thermal ratings and equivalent reactances are traceable to the PERFORM
%   2019 source instead of round-number placeholders.
%
%   Adds no buses and no branches. Topology/zone-map driven rather than
%   branch-index driven, so it applies unchanged to both hierarchy roles:
%   the 143-bus full S7 structural parent and the 49-bus S11 diagnostic core.
%   Applying this function to S11 does not promote the reduced model.
%
%   (0.5) Reactance. OFF BY DEFAULT - opt in with options.fit_reactance.
%
%         One multiplier per zone-boundary group, fitted so the core's cut
%         PTDFs match PERFORM's over canonical zonal transfers, regularised
%         toward m = 1.
%
%         It is off by default because it was measured against the project's
%         own acceptance metric and it loses. On the six 2019 scaled
%         scenarios the fixed-scale all-hour interface objective goes
%         0.489612 -> 0.561823, a 14.7% REGRESSION. It helps exactly the two
%         corridors diagnosed as too stiff - Dysinger East MAE 133.5 -> 113.3
%         and West Central 215.6 -> 192.6 - and hurts everything east of
%         them: Central East 110.1 -> 148.7, Total East 361.9 -> 388.5,
%         Dunwoodie South 276.6 -> 308.2.
%
%         The remaining mismatch is structurally confounded rather than
%         resolvable by a scalar tuning claim. The core has no E-G
%         corridor at all (PERFORM has 7 circuits, 3054 MVA, Coopers
%         Corners-Rock Tavern), so every eastbound MW is forced through E-F.
%         Matching PERFORM's E-F PTDF then requires making E-F stiffer, which
%         reduces its flow - and the S7 dispatch already underflows every
%         eastern target. Phase 1 therefore tests E-G and other missing paths
%         on the full S7 parent before any further reactance calibration.
%
%         Ratings, by contrast, are free: RATE_A does not enter the power
%         flow, so with fit_reactance = false the impedances are bit-identical
%         and the interface objective is exactly unchanged at 0.489612.
%
%         Two other targets were tried and rejected, both recorded here
%         because the rejection is informative:
%
%         - Parallel combination of the crossing circuits. Dominated by
%           whichever crossing has the smallest reactance; for D-E that is
%           short 115 kV taps inside the Massena area carrying no boundary
%           transfer, giving a meaningless 0.00036 pu target.
%         - Boundary Thevenin reactance X_th. Confounded by intra-zone
%           spread, which is large in PERFORM's fine-grained zones and tiny
%           in the coarse core. Fitting it inflated G-H by 13x, H-I by 17x
%           and I-K by 20x, and made the independent cut-PTDF check WORSE
%           (0.187 -> 0.283).
%
%         The regularisation is not cosmetic. Unregularised, the PTDF fit
%         pushes multipliers onto their bounds because it is trying to correct
%         a topology difference - zone I is one bus in the core and a six-bus
%         mesh in PERFORM - with corridor impedance. Reactance is the wrong
%         knob for that; splitting zone I is Phase 1 work.
%
%         The honest ceiling is modest: ~27% of the cut-PTDF residual
%         unregularised, ~22% at the default regularisation, and widening the
%         bounds from [0.25 4] to [0.1 10] changes nothing. The remainder is
%         structural, and is left visible rather than hidden in a distorted
%         reactance.
%
%         BR_R is scaled with BR_X to hold X/R constant; without it a
%         shortened equivalent acquires an absurd X/R and manufactures losses.
%         BR_B is NOT scaled by default - see options.scale_b.
%
%   (0.1/0.3/0.4) Ratings. Each group's PERFORM aggregate RATE_A is allocated
%         across the core branches forming it in proportion to 1/x on the
%         fitted reactances, so each equivalent branch is rated for the share
%         of the corridor it carries. Groups with no PERFORM zone-pair
%         counterpart are rated from ny_core_corridor_reference.csv.
%
%   SCOPE LIMIT - intra-zone branches are NOT re-rated. Only zone-boundary
%   branches have an unambiguous PERFORM counterpart (the set of circuits
%   crossing that boundary). An intra-zone equivalent generally represents no
%   identifiable circuit: of the 47 intra-zone branches in the 49-bus core,
%   only 10 have endpoints that both match a PERFORM substation name, and
%   NIAGARA W - HUNTLEY is not among them because the core splits Niagara into
%   NIAGARA W / NIAGARA E while PERFORM has a single NIAGARA.
%
%   That branch matters: the chronic "Niagara West-Huntley" overload reported
%   across the S7/S11 scenarios sits on an intra-zone-A branch carrying a 790
%   MVA placeholder, so this function does not touch it. The A-B boundary
%   branch NIAGARA W - ROCHESTER, which shares the placeholder, IS re-rated
%   (790 -> share of 5581 MVA) and does clear. Rating the intra-zone
%   equivalents needs substation aliasing and is Phase 1 work.
%
%   After this function, in the 49-bus core: all 36 zone-boundary branches are
%   source-backed (33 re-rated here, 3 already PERFORM-direct and protected),
%   and 47 intra-zone branches still carry placeholders.
%
%   Options:
%     .reference_dir  where the ny_core_*_reference.csv files live
%     .fit_reactance  default true
%     .apply_ratings  default true
%     .scale_r        scale BR_R with BR_X (default true)
%     .scale_b        scale BR_B with BR_X (default FALSE). Charging on a
%                     reduced equivalent branch is not physically tied to its
%                     equivalent reactance, and the case already carries a
%                     large reactive surplus against a PERFORM source whose
%                     reactive load is ~0 MVAr, so inflating charging is never
%                     the right default.
%     .m_bounds       [lo hi] multiplier bounds (default [0.05 20])
%
%   See also BUILD_NY_CORE_CUTSET_REFERENCE.

if nargin < 2, options = struct(); end
nylite = fileparts(mfilename('fullpath'));
if ~isfield(options, 'reference_dir'), options.reference_dir = nylite; end
if ~isfield(options, 'fit_reactance'), options.fit_reactance = false; end
if ~isfield(options, 'apply_ratings'), options.apply_ratings = true; end
if ~isfield(options, 'scale_r'), options.scale_r = true; end
if ~isfield(options, 'scale_b'), options.scale_b = false; end
if ~isfield(options, 'm_bounds'), options.m_bounds = [0.25 4]; end
if ~isfield(options, 'reg_weight'), options.reg_weight = 0.30; end
if ~isfield(options, 'protect_pairs')
    % [from to] bus pairs carrying PERFORM-direct parameters.
    options.protect_pairs = [38 39; 73 9002; 9002 74];
end
if ~isfield(options, 'protect_branch_rows'), options.protect_branch_rows = []; end
if ~isfield(options, 'verbose'), options.verbose = true; end
define_constants;

refdir = options.reference_dir;
cutref = readtable(fullfile(refdir, 'ny_core_cutset_reference.csv'), 'TextType', 'string', 'VariableNamingRule', 'preserve');
corref = readtable(fullfile(refdir, 'ny_core_corridor_reference.csv'), 'TextType', 'string', 'VariableNamingRule', 'preserve');
ptdfref = readtable(fullfile(refdir, 'ny_core_ptdf_reference.csv'), 'TextType', 'string', 'VariableNamingRule', 'preserve');

mpc = attach_nyiso_zone_metadata(mpc);
zone = mpc.userdata.nyiso_physical_zone;
nb = size(mpc.bus, 1); nl = size(mpc.branch, 1);
row = containers.Map(num2cell(mpc.bus(:, BUS_I)), num2cell(1:nb));
fr = cellfun(@(b) row(b), num2cell(mpc.branch(:, F_BUS)));
to = cellfun(@(b) row(b), num2cell(mpc.branch(:, T_BUS)));

% ---- zone-boundary groups in the core ----------------------------------
keys = strings(nl, 1); sgn = zeros(nl, 1);
onbr = mpc.branch(:, BR_STATUS) > 0;
for k = 1:nl
    if ~onbr(k), continue; end
    zf = zone{fr(k)}; zt = zone{to(k)};
    if isempty(zf) || isempty(zt) || strcmp(zf, zt), continue; end
    if zf < zt, keys(k) = sprintf('%s-%s', zf, zt); sgn(k) = 1;
    else,       keys(k) = sprintf('%s-%s', zt, zf); sgn(k) = -1;
    end
end
gname = unique(keys(keys ~= ""), 'stable');
ng = numel(gname);
gidx = cell(ng, 1);
for g = 1:ng, gidx{g} = find(keys == gname(g)); end

% ---- protected branches -------------------------------------------------
% Branches whose R/X/B and RATE_A already come straight from a PERFORM
% circuit, per ny_tieline_parameter_register.csv and
% s7_perform_tieline_selected_branch_parameters.csv. They are excluded from
% both the reactance multiplier and the rating reallocation: overwriting a
% source-backed parameter with a fitted one is strictly a regression.
%
% This matters. Without it the 1/x split inside the F-G group re-rated
% GILBOA-LEEDS - a real 1216 MVA PERFORM circuit - down to 340 MVA, because
% the parallel NEW SCOTLAND-LEEDS equivalent has ~12x its susceptance.
% Protected ratings are subtracted from the group target and only the
% remainder is spread over the equivalent branches.
prot = false(nl, 1);
for k = 1:nl
    pair = sort([mpc.branch(k, F_BUS), mpc.branch(k, T_BUS)]);
    for pp = options.protect_pairs'
        if isequal(pair, sort(pp(:)')), prot(k) = true; end
    end
end
registered_rows = options.protect_branch_rows(:);
if isfield(mpc, 'userdata') && isfield(mpc.userdata, 'ny_lite') && ...
        isfield(mpc.userdata.ny_lite, 'phase0_protected_branch_rows')
    registered_rows = [registered_rows; ...
        mpc.userdata.ny_lite.phase0_protected_branch_rows(:)]; %#ok<AGROW>
end
registered_rows = unique(registered_rows(isfinite(registered_rows) & ...
    registered_rows >= 1 & registered_rows <= nl));
prot(registered_rows) = true;
n_prot = sum(prot);

% electrical mass weights, same definition as the reference generator
wmass = max(mpc.bus(:, PD), 0);
for k = find(mpc.gen(:, GEN_STATUS) > 0)'
    ri = row(mpc.gen(k, GEN_BUS));
    wmass(ri) = wmass(ri) + max(mpc.gen(k, PMAX), 0);
end
zvec = zeros(nb, 1);
zl = {'A','B','C','D','E','F','G','H','I','J','K'};
for i = 1:nb
    j = find(strcmp(zl, zone{i}), 1);
    if ~isempty(j), zvec(i) = j; end
end

% ---- targets ------------------------------------------------------------
% kind 1 = boundary Thevenin reactance; kind 2 = direct corridor reactance
tgt = nan(ng, 1); kind = zeros(ng, 1); tsrc = strings(ng, 1);
for g = 1:ng
    cr = cutref(cutref.cut == gname(g), :);
    if height(cr) == 1 && isfinite(cr.x_thevenin_pu(1))
        tgt(g) = cr.x_thevenin_pu(1); kind(g) = 1; tsrc(g) = "perform_boundary_xth";
        continue;
    end
    co = corref(corref.core_cut == gname(g), :);
    if height(co) >= 1 && isfinite(co.x_parallel_pu(1))
        tgt(g) = co.x_parallel_pu(1); kind(g) = 2;
        tsrc(g) = "perform_corridor_" + co.corridor(1);
        continue;
    end
    tsrc(g) = "no_reference";
end
fitg = find(kind > 0);

x0 = mpc.branch(:, BR_X);
m = ones(ng, 1);

% cut-PTDF diagnostic, independent of the objective
[dP, tname] = canonical_transfers(mpc, zone, wmass, ptdfref);
Tref = ptdf_target_matrix(ptdfref, gname, tname);
pd_before = ptdf_rms(mpc, x0, gidx, sgn, dP, Tref, row);

% Objective: cut-PTDF match, regularised toward m = 1.
%
% The regularisation is not cosmetic. Unregularised, the fit drives the
% downstate multipliers to 30-50x because it is trying to correct a topology
% difference - zone I is one bus in the core and a six-bus mesh in PERFORM -
% with corridor impedance. Penalising log(m) symmetrically, inside tight
% bounds, keeps the adjustment to something a network equivalent can honestly
% claim, and leaves the residual that remains visible as structural error
% rather than hiding it in a distorted reactance.
resid = @(mm) [ptdf_residual(mm, fitg, ng, gidx, sgn, mpc, x0, dP, Tref, row, prot); ...
               options.reg_weight * log(mm(:))];
r0 = resid(ones(numel(fitg), 1));
if options.fit_reactance && ~isempty(fitg)
    lo = options.m_bounds(1) * ones(numel(fitg), 1);
    hi = options.m_bounds(2) * ones(numel(fitg), 1);
    opt = optimoptions('lsqnonlin', 'Display', 'off', ...
        'MaxFunctionEvaluations', 20000, 'MaxIterations', 2000, ...
        'FunctionTolerance', 1e-12, 'StepTolerance', 1e-12);
    mfit = lsqnonlin(resid, ones(numel(fitg), 1), lo, hi, opt);
    m(fitg) = mfit;
    atb = gname(fitg(mfit <= lo + 1e-6 | mfit >= hi - 1e-6));
else
    mfit = ones(numel(fitg), 1); atb = strings(0, 1);
end
r1 = resid(mfit);

% ---- apply --------------------------------------------------------------
b_before = sum(mpc.branch(:, BR_B));
xth_before = arrayfun(@(g) group_metric(mpc, x0, gidx, g, zvec, wmass, row, kind(g)), (1:ng)');
mvec = ones(nl, 1);
for g = 1:ng
    idx = gidx{g}(~prot(gidx{g}));
    mvec(idx) = m(g);
end
xnew = x0 .* mvec;
mpc.branch(:, BR_X) = xnew;
if options.scale_r, mpc.branch(:, BR_R) = mpc.branch(:, BR_R) .* mvec; end
if options.scale_b, mpc.branch(:, BR_B) = mpc.branch(:, BR_B) .* mvec; end
xth_after = arrayfun(@(g) group_metric(mpc, xnew, gidx, g, zvec, wmass, row, kind(g)), (1:ng)');

% ---- ratings ------------------------------------------------------------
rate_before = mpc.branch(:, RATE_A);
rsrc = strings(ng, 1); rtgt = nan(ng, 1);
for g = 1:ng
    cr = cutref(cutref.cut == gname(g), :);
    if height(cr) == 1
        rtgt(g) = cr.sum_rate_a_mva(1); rsrc(g) = "perform_zone_cut";
    else
        co = corref(corref.core_cut == gname(g), :);
        if height(co) >= 1
            rtgt(g) = sum(co.sum_rate_a_mva); rsrc(g) = "perform_named_corridor";
        else
            rsrc(g) = "no_reference_unchanged";
        end
    end
    if options.apply_ratings && isfinite(rtgt(g))
        idx = gidx{g};
        keepr = idx(prot(idx));            % source-backed, left alone
        freer = idx(~prot(idx));
        remain = rtgt(g) - sum(mpc.branch(keepr, RATE_A));
        if remain < 0
            warning('apply_ny_core_phase0_corrections:ProtectedExceedsTarget', ...
                ['Cut %s: protected ratings (%.0f MVA) already exceed the PERFORM ' ...
                 'target (%.0f MVA); equivalent branches set to zero rating.'], ...
                gname(g), sum(mpc.branch(keepr, RATE_A)), rtgt(g));
            remain = 0;
        end
        if ~isempty(freer)
            sh = 1 ./ max(mpc.branch(freer, BR_X), 1e-9);
            sh = sh / sum(sh);
            mpc.branch(freer, RATE_A) = remain * sh;
            mpc.branch(freer, RATE_B) = mpc.branch(freer, RATE_A);
            mpc.branch(freer, RATE_C) = mpc.branch(freer, RATE_A);
        end
    end
end

pd_after = ptdf_rms(mpc, mpc.branch(:, BR_X), gidx, sgn, dP, Tref, row);

report = struct();
report.groups = table(gname, cellfun(@numel, gidx), tsrc, tgt, ...
    xth_before, xth_after, m, ...
    arrayfun(@(g) sum(rate_before(gidx{g})), (1:ng)'), ...
    arrayfun(@(g) sum(mpc.branch(gidx{g}, RATE_A)), (1:ng)'), rtgt, rsrc, ...
    'VariableNames', {'cut', 'n_branches', 'x_target_source', 'x_target_pu', ...
    'x_before_pu', 'x_after_pu', 'x_multiplier', 'rate_before_mva', ...
    'rate_after_mva', 'rate_target_mva', 'rate_source'});
report.objective_rms_before = sqrt(mean(r0 .^ 2));   % fitted objective (PTDF + reg)
report.objective_rms_after = sqrt(mean(r1 .^ 2));
report.ptdf_rms_before = pd_before;                  % PTDF term alone
report.ptdf_rms_after = pd_after;
k1 = kind == 1 & isfinite(tgt);                      % boundary X_th, reported only
report.xth_rel_rms_before = sqrt(mean(((xth_before(k1) - tgt(k1)) ./ tgt(k1)) .^ 2));
report.xth_rel_rms_after = sqrt(mean(((xth_after(k1) - tgt(k1)) ./ tgt(k1)) .^ 2));
report.at_bound = atb;
report.charging_mvar_before = 100 * b_before;
report.charging_mvar_after = 100 * sum(mpc.branch(:, BR_B));
report.n_branches_rerated = sum(abs(mpc.branch(:, RATE_A) - rate_before) > 1e-6);
report.n_protected = n_prot;

mpc.userdata.ny_lite.phase0 = struct('applied', datestr(now, 'yyyy-mm-dd HH:MM:SS'), ...
    'reference', 'PERFORM 2019 On-Peak v23 via build_ny_core_cutset_reference', ...
    'groups', report.groups, 'options', options);

if options.verbose
    fprintf('\nPhase 0 corrections: %d-bus / %d-branch case, %d boundary groups\n', nb, nl, ng);
    disp(report.groups);
    fprintf('cut-PTDF normalised RMS    : %.4f -> %.4f  (%.1f%% reduction, fitted)\n', ...
        pd_before, pd_after, 100 * (1 - pd_after / pd_before));
    fprintf('boundary X_th relative RMS : %.4f -> %.4f  (reported only, confounded by intra-zone spread)\n', ...
        report.xth_rel_rms_before, report.xth_rel_rms_after);
    fprintf('branches re-rated          : %d of %d\n', report.n_branches_rerated, nl);
    fprintf('line charging              : %.0f -> %.0f MVAr\n', report.charging_mvar_before, report.charging_mvar_after);
    if ~isempty(atb), fprintf('multipliers at bound       : %s\n', strjoin(cellstr(atb), ', ')); end
end
end

% ------------------------------------------------------------------------
function v = group_metric(mpc, x, gidx, g, zvec, wmass, row, kind)
define_constants;
if kind == 2 || kind == 0
    xs = x(gidx{g}); xs = xs(abs(xs) > 1e-12);
    v = NaN; if ~isempty(xs), v = 1 / sum(1 ./ xs); end
    return;
end
zs = unique(zvec(cellfun(@(b) row(b), num2cell(mpc.branch(gidx{g}, F_BUS)))));
zt = unique(zvec(cellfun(@(b) row(b), num2cell(mpc.branch(gidx{g}, T_BUS)))));
za = zs(1); zb = zt(1);
if za == zb
    all_z = unique([zs; zt]); za = all_z(1); zb = all_z(end);
end
v = xth(mpc, x, zvec, za, zb, wmass, row);
end

function res = ptdf_residual(mm, fitg, ng, gidx, sgn, mpc, x0, dP, T, row, prot)
%PTDF_RESIDUAL Normalised cut-flow error over the canonical zonal transfers.
m = ones(ng, 1); m(fitg) = mm;
x = x0;
for g = 1:ng
    idx = gidx{g}(~prot(gidx{g}));
    x(idx) = x0(idx) * m(g);
end
F = dc_flows(mpc, x, dP, row);
res = [];
for g = 1:ng
    if all(isnan(T(g, :))), continue; end
    idx = gidx{g};
    fl = sgn(idx)' * F(idx, :);
    w = max(max(abs(T(g, :))), 50);
    d = (fl - T(g, :)) / w;
    d(isnan(T(g, :))) = 0;
    res = [res, d]; %#ok<AGROW>
end
res = res(:);
end

function F = dc_flows(mpc, x, dP, row)
define_constants;
nb = size(mpc.bus, 1); nl = size(mpc.branch, 1);
f = cellfun(@(b) row(b), num2cell(mpc.branch(:, F_BUS)));
t = cellfun(@(b) row(b), num2cell(mpc.branch(:, T_BUS)));
tap = mpc.branch(:, TAP); tap(tap == 0) = 1;
b = 1 ./ (max(abs(x), 1e-9) .* tap);
b(mpc.branch(:, BR_STATUS) <= 0) = 0;
ii = (1:nl)';
Bf = sparse([ii; ii], [f; t], [b; -b], nl, nb);
Cf = sparse([ii; ii], [f; t], [ones(nl, 1); -ones(nl, 1)], nl, nb);
Bbus = Cf' * Bf;
ref = find(mpc.bus(:, BUS_TYPE) == REF, 1); if isempty(ref), ref = 1; end
keep = true(nb, 1); keep(ref) = false;
th = zeros(nb, size(dP, 2));
th(keep, :) = Bbus(keep, keep) \ (dP(keep, :) / mpc.baseMVA);
F = (Bf * th) * mpc.baseMVA;
end

function res = xth_residual(mm, fitg, ng, gidx, mpc, x0, zvec, wmass, row, tgt, kind)
m = ones(ng, 1); m(fitg) = mm;
x = x0;
for g = 1:ng, x(gidx{g}) = x0(gidx{g}) * m(g); end
res = zeros(numel(fitg), 1);
for i = 1:numel(fitg)
    g = fitg(i);
    v = group_metric(mpc, x, gidx, g, zvec, wmass, row, kind(g));
    res(i) = (v - tgt(g)) / tgt(g);
end
end

function v = xth(mpc, x, zvec, za, zb, wmass, row)
define_constants;
nb = size(mpc.bus, 1);
wa = zeros(nb, 1); wa(zvec == za) = wmass(zvec == za);
wb = zeros(nb, 1); wb(zvec == zb) = wmass(zvec == zb);
if sum(wa) <= 0 || sum(wb) <= 0, v = NaN; return; end
wa = wa / sum(wa); wb = wb / sum(wb);
th = dc_angles(mpc, x, wa - wb, row);
v = wa' * th - wb' * th;
end

function th = dc_angles(mpc, x, dp, row)
define_constants;
nb = size(mpc.bus, 1); nl = size(mpc.branch, 1);
f = cellfun(@(b) row(b), num2cell(mpc.branch(:, F_BUS)));
t = cellfun(@(b) row(b), num2cell(mpc.branch(:, T_BUS)));
tap = mpc.branch(:, TAP); tap(tap == 0) = 1;
b = 1 ./ (max(abs(x), 1e-9) .* tap);
b(mpc.branch(:, BR_STATUS) <= 0) = 0;
ii = (1:nl)';
Bf = sparse([ii; ii], [f; t], [b; -b], nl, nb);
Cf = sparse([ii; ii], [f; t], [ones(nl, 1); -ones(nl, 1)], nl, nb);
Bbus = Cf' * Bf;
ref = find(mpc.bus(:, BUS_TYPE) == REF, 1); if isempty(ref), ref = 1; end
keep = true(nb, 1); keep(ref) = false;
th = zeros(nb, 1);
th(keep) = Bbus(keep, keep) \ dp(keep);
end

function [dP, tname] = canonical_transfers(mpc, zone, wmass, ptdfref)
define_constants;
nb = size(mpc.bus, 1);
gcap = zeros(nb, 1);
row = containers.Map(num2cell(mpc.bus(:, BUS_I)), num2cell(1:nb));
for k = find(mpc.gen(:, GEN_STATUS) > 0)'
    ri = row(mpc.gen(k, GEN_BUS));
    gcap(ri) = gcap(ri) + max(mpc.gen(k, PMAX), 0);
end
% Sink is the rest of NY by load, matching build_ny_core_cutset_reference.
% A single-zone sink is not usable here: zone J carries zero load in the
% 143-bus S7 case, where the downstate load sits on the zone-I CE UG bus.
inny = ~cellfun(@isempty, zone);
tr = unique(ptdfref.transfer, 'stable');
dP = []; tname = strings(0, 1);
for i = 1:numel(tr)
    r = find(ptdfref.transfer == tr(i), 1);
    src = char(ptdfref.source_zone(r)); mw = ptdfref.transfer_mw(r);
    sel = cellfun(@(c) strcmp(c, src), zone);
    w = zeros(nb, 1); w(sel) = gcap(sel);
    if sum(w) <= 0, continue; end
    rest = inny & ~sel;
    ws = zeros(nb, 1); ws(rest) = max(mpc.bus(rest, PD), 0);
    if sum(ws) <= 0, continue; end
    dP(:, end+1) = mw * (w / sum(w) - ws / sum(ws)); %#ok<AGROW>
    tname(end+1, 1) = tr(i); %#ok<AGROW>
end
end

function T = ptdf_target_matrix(ptdfref, gname, tname)
T = nan(numel(gname), numel(tname));
for g = 1:numel(gname)
    for t = 1:numel(tname)
        r = ptdfref(ptdfref.transfer == tname(t) & ptdfref.cut == gname(g), :);
        if height(r) == 1, T(g, t) = r.cut_flow_mw(1); end
    end
end
end

function v = ptdf_rms(mpc, x, gidx, sgn, dP, T, row)
define_constants;
nb = size(mpc.bus, 1); nl = size(mpc.branch, 1);
f = cellfun(@(b) row(b), num2cell(mpc.branch(:, F_BUS)));
t = cellfun(@(b) row(b), num2cell(mpc.branch(:, T_BUS)));
tap = mpc.branch(:, TAP); tap(tap == 0) = 1;
b = 1 ./ (max(abs(x), 1e-9) .* tap);
b(mpc.branch(:, BR_STATUS) <= 0) = 0;
ii = (1:nl)';
Bf = sparse([ii; ii], [f; t], [b; -b], nl, nb);
Cf = sparse([ii; ii], [f; t], [ones(nl, 1); -ones(nl, 1)], nl, nb);
Bbus = Cf' * Bf;
ref = find(mpc.bus(:, BUS_TYPE) == REF, 1); if isempty(ref), ref = 1; end
keep = true(nb, 1); keep(ref) = false;
th = zeros(nb, size(dP, 2));
th(keep, :) = Bbus(keep, keep) \ (dP(keep, :) / mpc.baseMVA);
F = (Bf * th) * mpc.baseMVA;
res = [];
for g = 1:numel(gidx)
    if all(isnan(T(g, :))), continue; end
    idx = gidx{g};
    fl = sgn(idx)' * F(idx, :);
    w = max(max(abs(T(g, :))), 50);
    d = (fl - T(g, :)) / w;
    d(isnan(T(g, :))) = 0;
    res = [res, d]; %#ok<AGROW>
end
v = sqrt(mean(res(:) .^ 2));
end
