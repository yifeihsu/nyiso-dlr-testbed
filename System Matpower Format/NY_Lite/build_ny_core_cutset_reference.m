function out = build_ny_core_cutset_reference(options)
%BUILD_NY_CORE_CUTSET_REFERENCE PERFORM-derived reference for the NPCC NY core.
%   Phase 0 reference data generator. Derives, from the PERFORM 2019 On-Peak
%   source snapshot, the per-NYISO-zone-pair quantities the NPCC-derived
%   49/143-bus core needs in order to stop using placeholder ratings and
%   uncalibrated equivalent reactances:
%
%     1. cut aggregates   - circuit count, sum RATE_A, and solved-snapshot MW
%                           for every zone-pair boundary crossing;
%     2. official share   - solved-snapshot MW of the NYISO monitored-circuit
%                           subset divided by the full-cut MW, so a reduced
%                           model that can only represent the cut can still be
%                           compared against a published interface target;
%     3. PTDF targets     - DC sensitivity of each cut to canonical zonal
%                           transfers, used to fit the core's equivalent
%                           reactances.
%
%   Zone D correction: the PERFORM area field codes the entire Massena/Moses
%   complex (St. Lawrence-FDR hydro, the HQ interconnections, and the
%   Massena-Marcy 765 kV line) as area 69 = NYISO Zone E. NYISO places it in
%   Zone D (NORTH). The NPCC core's ny_bus_zone_map.csv already has this
%   right, so the PERFORM side is corrected here by substation name before any
%   cut or PTDF is computed. Without this the D-E reference is meaningless.
%
%   Outputs (written to this directory):
%     ny_core_cutset_reference.csv   - one row per zone-pair boundary
%     ny_core_ptdf_reference.csv     - one row per (transfer, cut) pair
%
%   Usage:
%     out = build_ny_core_cutset_reference();

if nargin < 1, options = struct(); end
if ~isfield(options, 'transfer_mw'), options.transfer_mw = 1000; end
if ~isfield(options, 'write'), options.write = true; end

nylite = fileparts(mfilename('fullpath'));
root = fileparts(fileparts(nylite));
perform_dir = fullfile(root, 'PERFORM', 'On Peak 2019 v23_Perform_NY', 'On Peak 2019 v23');
addpath(root, fullfile(root, 'System Matpower Format'), nylite, perform_dir);
define_constants;

mpc = loadcase('nyiso_On_Peak_v23_shunts_as_z_load');
nb = size(mpc.bus, 1);
id2row = containers.Map(num2cell(mpc.bus(:, BUS_I)), num2cell(1:nb));

% ---- NYISO zone letter per bus, with the Zone D correction -------------
area_codes  = [65 66 67 68 69 70 71 72 73 74 75];
area_letters = {'A','B','C','D','E','F','G','I','H','J','K'};
zone = cell(nb, 1);
for k = 1:nb
    zone{k} = area_letters{area_codes == mpc.bus(k, BUS_AREA)};
end
north_names = {'MASSENA', 'MOSES', 'WILLIS', 'PLATTSBURGH'};
north_prefix = {'ALCOA MASSENA'};
n_moved = 0;
for k = 1:nb
    nmk = strtrim(mpc.bus_name{k});
    hit = any(strcmp(nmk, north_names));
    for p = 1:numel(north_prefix)
        hit = hit || strncmp(nmk, north_prefix{p}, numel(north_prefix{p}));
    end
    if hit && ~strcmp(zone{k}, 'D')
        zone{k} = 'D';
        n_moved = n_moved + 1;
    end
end
fprintf('Zone D correction: %d PERFORM buses reassigned from E to D.\n', n_moved);

zone_letters = {'A','B','C','D','E','F','G','H','I','J','K'};
zidx = containers.Map(zone_letters, num2cell(1:numel(zone_letters)));
zvec = cellfun(@(c) zidx(c), zone);

% ---- solved-snapshot branch flows --------------------------------------
PFmw = snapshot_branch_pf(mpc);
on = mpc.branch(:, BR_STATUS) > 0;

fb = cellfun(@(b) id2row(b), num2cell(mpc.branch(:, F_BUS)));
tb = cellfun(@(b) id2row(b), num2cell(mpc.branch(:, T_BUS)));
zf = zvec(fb); zt = zvec(tb);

% ---- zone-pair cuts -----------------------------------------------------
cut_rows = {};
for a = 1:numel(zone_letters)
    for b = (a+1):numel(zone_letters)
        sel = on & ((zf == a & zt == b) | (zf == b & zt == a));
        if ~any(sel), continue; end
        idx = find(sel);
        % positive direction: zone a -> zone b
        sgn = ones(numel(idx), 1);
        sgn(zf(idx) == b) = -1;
        flow = sum(sgn .* PFmw(idx));
        xs = mpc.branch(idx, BR_X);
        xs = xs(abs(xs) > 1e-9);
        xpar = NaN; if ~isempty(xs), xpar = 1 / sum(1 ./ xs); end
        cut_rows(end+1, :) = { ...
            sprintf('%s-%s', zone_letters{a}, zone_letters{b}), ...
            zone_letters{a}, zone_letters{b}, numel(idx), ...
            sum(mpc.branch(idx, RATE_A)), ...
            sum(mpc.branch(idx(mpc.bus(fb(idx), BASE_KV) >= 230 | ...
                              mpc.bus(tb(idx), BASE_KV) >= 230), RATE_A)), ...
            flow, xpar}; %#ok<AGROW>
    end
end
cut = cell2table(cut_rows, 'VariableNames', {'cut', 'zone_from', 'zone_to', ...
    'n_circuits', 'sum_rate_a_mva', 'sum_rate_a_hv_mva', ...
    'snapshot_flow_mw', 'x_parallel_pu'});

% ---- official monitored subsets (S12 operators) -------------------------
ops = readtable(fullfile(nylite, 's12_interface_operators.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
% Each interface maps to a zone-pair cut, or to a composite of cuts. Moses
% South is only a well-posed D-E cut once the Zone D correction above is
% applied; Total East is the composite boundary between {A..E} and {F..K}.
ifc_cut = struct( ...
    'Dysinger_East',    {{'A-B'}}, ...
    'West_Central',     {{'B-C'}}, ...
    'Moses_South',      {{'D-E'}}, ...
    'Central_East',     {{'E-F'}}, ...
    'Total_East_proxy', {{'E-F', 'E-G', 'D-F'}}, ...
    'UPNY_ConEd',       {{'G-H'}}, ...
    'Dunwoodie_South',  {{'I-J'}});
names = fieldnames(ifc_cut);
off_rows = {};
for k = 1:numel(names)
    nm = names{k};
    rows = ops(ops.interface_name == string(nm), :);
    si = double(rows.source_branch);
    sg = double(rows.sign);
    off_mw = sum(sg .* PFmw(si));
    off_rate = sum(mpc.branch(si, RATE_A));
    ck = ifc_cut.(nm);
    cut_mw = 0; cut_rate = 0; cut_n = 0;
    for c = 1:numel(ck)
        cr = cut(strcmp(cut.cut, ck{c}), :);
        cut_mw = cut_mw + cr.snapshot_flow_mw(1);
        cut_rate = cut_rate + cr.sum_rate_a_mva(1);
        cut_n = cut_n + cr.n_circuits(1);
    end
    share = off_mw / cut_mw;
    if share > 1.0
        valid = "INVALID_subset_exceeds_cut";
    elseif share < 0
        valid = "INVALID_sign_opposes_cut";
    else
        valid = "ok";
    end
    off_rows(end+1, :) = {nm, strjoin(ck, '+'), numel(si), off_rate, off_mw, ...
        cut_n, cut_rate, cut_mw, share, valid}; %#ok<AGROW>
end
official = cell2table(off_rows, 'VariableNames', {'interface_name', 'cut', ...
    'n_circuits', 'sum_rate_a_mva', 'snapshot_flow_mw', 'cut_n_circuits', ...
    'cut_sum_rate_a_mva', 'cut_snapshot_flow_mw', 'official_share_of_cut', ...
    'validity'});

% ---- boundary Thevenin transfer reactance ------------------------------
% The naive parallel combination of the crossing circuits is a poor
% calibration target: it is dominated by whichever crossing has the smallest
% reactance, which for D-E means short 115 kV taps inside the Massena area
% that carry no boundary transfer at all. X_th instead measures what a zonal
% transfer actually sees: inject 1 pu spread across the source zone, withdraw
% it across the sink zone, and take the weighted-average angle difference.
Xth = nan(height(cut), 1);
wmass = max(mpc.bus(:, PD), 0);
for k = find(mpc.gen(:, GEN_STATUS) > 0)'
    ri = id2row(mpc.gen(k, GEN_BUS));
    wmass(ri) = wmass(ri) + max(mpc.gen(k, PMAX), 0);
end
for c = 1:height(cut)
    Xth(c) = boundary_xth(mpc, zvec, zidx(cut.zone_from{c}), ...
        zidx(cut.zone_to{c}), wmass, id2row);
end
cut.x_thevenin_pu = Xth;

% ---- named corridors ----------------------------------------------------
% Some NPCC-core equivalent branches do not correspond to any PERFORM
% zone-pair boundary and so cannot be rated or calibrated by the cut rule.
% They are mapped instead to the physical corridor they represent.
%
% C-F: the core's GILBOA(F)-BINGHAMTON(C) 345 kV equivalent. PERFORM has no
% C-F crossing at all. The corridor it represents is Fraser-Gilboa GF5-35 -
% Fraser is a Zone E substation with no NPCC node, so the reduction landed
% its southern end on the Binghamton bus. Fraser-Gilboa is a Total East
% element, not a Central East one, and the composite {A..E}|{F..K} Total East
% boundary already contains any C-F branch, so the attribution is harmless
% where it matters. Only the rating and reactance need a source.
corr_defs = struct( ...
    'name',      {'FRASER_GILBOA'}, ...
    'bus_a',     {'FRASER'}, ...
    'bus_b',     {'GILBOA'}, ...
    'core_cut',  {'C-F'});
corr_rows = {};
corr_idx = cell(numel(corr_defs), 1);
for k = 1:numel(corr_defs)
    ia = find(strcmp(strtrim(mpc.bus_name), corr_defs(k).bus_a));
    ib = find(strcmp(strtrim(mpc.bus_name), corr_defs(k).bus_b));
    ida = mpc.bus(ia, BUS_I); idb = mpc.bus(ib, BUS_I);
    sel = find(on & ((ismember(mpc.branch(:, F_BUS), ida) & ismember(mpc.branch(:, T_BUS), idb)) | ...
                     (ismember(mpc.branch(:, F_BUS), idb) & ismember(mpc.branch(:, T_BUS), ida))));
    corr_idx{k} = sel;
    sgn = ones(numel(sel), 1);
    sgn(ismember(mpc.branch(sel, F_BUS), idb)) = -1;   % positive a -> b
    xs = mpc.branch(sel, BR_X); xs = xs(abs(xs) > 1e-9);
    xpar = NaN; if ~isempty(xs), xpar = 1 / sum(1 ./ xs); end
    corr_rows(end+1, :) = {corr_defs(k).name, corr_defs(k).core_cut, ...
        numel(sel), sum(mpc.branch(sel, RATE_A)), sum(sgn .* PFmw(sel)), xpar}; %#ok<AGROW>
end
corridor = cell2table(corr_rows, 'VariableNames', {'corridor', 'core_cut', ...
    'n_circuits', 'sum_rate_a_mva', 'snapshot_flow_mw', 'x_parallel_pu'});

% ---- DC PTDF targets ----------------------------------------------------
% Canonical transfers: 1000 MW injected across one source zone (distributed by
% online generator capability) and withdrawn across the REST of NY
% (distributed by load).
%
% The sink is the rest of NY rather than a single zone because a single-zone
% sink is not robust across the case family: zone J carries zero load in the
% 143-bus S7 case, where the downstate load sits on the zone-I CE UG bus, so
% normalising a J-load sink divides by zero. "Rest of NY by load" is
% well-defined in every variant and is closer to what a real zonal dispatch
% change looks like anyway.
H = makePTDF(mpc.baseMVA, mpc.bus, mpc.branch, find(mpc.bus(:, BUS_TYPE) == REF, 1));
inny = zvec > 0;
gcap = zeros(nb, 1);
gon = mpc.gen(:, GEN_STATUS) > 0;
for k = find(gon)'
    ri = id2row(mpc.gen(k, GEN_BUS));
    gcap(ri) = gcap(ri) + max(mpc.gen(k, PMAX), 0);
end

ptdf_rows = {};
for s = 1:numel(zone_letters)
    wsrc = zeros(nb, 1);
    wsrc(zvec == s) = gcap(zvec == s);
    if sum(wsrc) <= 0, continue; end
    wsrc = wsrc / sum(wsrc);
    wsink = zeros(nb, 1);
    rest = inny & zvec ~= s;
    wsink(rest) = max(mpc.bus(rest, PD), 0);
    if sum(wsink) <= 0, continue; end
    wsink = wsink / sum(wsink);
    dP = options.transfer_mw * (wsrc - wsink);
    fbr = H * dP;
    for c = 1:height(cut)
        a = zidx(cut.zone_from{c}); b = zidx(cut.zone_to{c});
        sel = on & ((zf == a & zt == b) | (zf == b & zt == a));
        idx = find(sel);
        sgn = ones(numel(idx), 1); sgn(zf(idx) == b) = -1;
        ptdf_rows(end+1, :) = {sprintf('%s_to_restNY', zone_letters{s}), ...
            zone_letters{s}, 'restNY', cut.cut{c}, 'zone_cut', ...
            options.transfer_mw, sum(sgn .* fbr(idx))}; %#ok<AGROW>
    end
    for k = 1:numel(corr_defs)
        sel = corr_idx{k};
        ida = mpc.bus(strcmp(strtrim(mpc.bus_name), corr_defs(k).bus_a), BUS_I);
        sgn = ones(numel(sel), 1);
        sgn(~ismember(mpc.branch(sel, F_BUS), ida)) = -1;
        ptdf_rows(end+1, :) = {sprintf('%s_to_restNY', zone_letters{s}), ...
            zone_letters{s}, 'restNY', corr_defs(k).core_cut, ...
            'named_corridor', options.transfer_mw, sum(sgn .* fbr(sel))}; %#ok<AGROW>
    end
end
ptdf = cell2table(ptdf_rows, 'VariableNames', {'transfer', 'source_zone', ...
    'sink_zone', 'cut', 'target_kind', 'transfer_mw', 'cut_flow_mw'});

if options.write
    writetable(cut, fullfile(nylite, 'ny_core_cutset_reference.csv'));
    writetable(official, fullfile(nylite, 'ny_core_official_share_reference.csv'));
    writetable(corridor, fullfile(nylite, 'ny_core_corridor_reference.csv'));
    writetable(ptdf, fullfile(nylite, 'ny_core_ptdf_reference.csv'));
    fprintf('wrote ny_core_cutset_reference.csv (%d cuts)\n', height(cut));
    fprintf('wrote ny_core_official_share_reference.csv (%d interfaces)\n', height(official));
    fprintf('wrote ny_core_corridor_reference.csv (%d corridors)\n', height(corridor));
    fprintf('wrote ny_core_ptdf_reference.csv (%d rows)\n', height(ptdf));
end

out = struct('cut', cut, 'official', official, 'corridor', corridor, ...
    'ptdf', ptdf, 'zone', {zone}, 'n_zone_d_moved', n_moved);
end

function xth = boundary_xth(mpc, zvec, za, zb, wmass, id2row)
%BOUNDARY_XTH Thevenin transfer reactance, in pu on baseMVA, between two
%   zones: the weighted-average angle separation produced by a 1 pu transfer
%   from zone za to zone zb under the DC model.
define_constants;
nb = size(mpc.bus, 1); nl = size(mpc.branch, 1);
wa = zeros(nb, 1); wa(zvec == za) = wmass(zvec == za);
wb = zeros(nb, 1); wb(zvec == zb) = wmass(zvec == zb);
if sum(wa) <= 0 || sum(wb) <= 0, xth = NaN; return; end
wa = wa / sum(wa); wb = wb / sum(wb);
f = cellfun(@(v) id2row(v), num2cell(mpc.branch(:, F_BUS)));
t = cellfun(@(v) id2row(v), num2cell(mpc.branch(:, T_BUS)));
tap = mpc.branch(:, TAP); tap(tap == 0) = 1;
b = 1 ./ (mpc.branch(:, BR_X) .* tap);
b(mpc.branch(:, BR_STATUS) <= 0) = 0;
ii = (1:nl)';
Bf = sparse([ii; ii], [f; t], [b; -b], nl, nb);
Cf = sparse([ii; ii], [f; t], [ones(nl, 1); -ones(nl, 1)], nl, nb);
Bbus = Cf' * Bf;
dp = wa - wb;
ref = find(mpc.bus(:, BUS_TYPE) == REF, 1); if isempty(ref), ref = 1; end
keep = true(nb, 1); keep(ref) = false;
th = zeros(nb, 1);
th(keep) = Bbus(keep, keep) \ dp(keep);
xth = wa' * th - wb' * th;
end

function PFmw = snapshot_branch_pf(mpc)
%SNAPSHOT_BRANCH_PF Active power at the from-end of every branch, MW, from the
%   solved bus voltages carried in the source case.
define_constants;
nb = size(mpc.bus, 1);
id2row = containers.Map(num2cell(mpc.bus(:, BUS_I)), num2cell(1:nb));
V = mpc.bus(:, VM) .* exp(1j * mpc.bus(:, VA) * pi / 180);
r = mpc.branch(:, BR_R); x = mpc.branch(:, BR_X); b = mpc.branch(:, BR_B);
tap = mpc.branch(:, TAP); tap(tap == 0) = 1;
T = tap .* exp(1j * mpc.branch(:, SHIFT) * pi / 180);
ys = 1 ./ (r + 1j * x);
Yff = (ys + 1j * b / 2) ./ (tap .^ 2);
Yft = -ys ./ conj(T);
f = cellfun(@(v) id2row(v), num2cell(mpc.branch(:, F_BUS)));
t = cellfun(@(v) id2row(v), num2cell(mpc.branch(:, T_BUS)));
Sf = V(f) .* conj(Yff .* V(f) + Yft .* V(t)) * mpc.baseMVA;
PFmw = real(Sf);
PFmw(mpc.branch(:, BR_STATUS) <= 0) = 0;
end
