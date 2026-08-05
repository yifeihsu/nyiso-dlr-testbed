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
if ~isfield(options, 'sink_zone'), options.sink_zone = 'J'; end
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

% ---- DC PTDF targets ----------------------------------------------------
% Canonical transfers: 1000 MW from each source zone into the sink zone,
% injection distributed by online generator capability, withdrawal by load.
H = makePTDF(mpc.baseMVA, mpc.bus, mpc.branch, find(mpc.bus(:, BUS_TYPE) == REF, 1));
sinkz = zidx(options.sink_zone);
wsink = zeros(nb, 1);
wsink(zvec == sinkz) = max(mpc.bus(zvec == sinkz, PD), 0);
wsink = wsink / sum(wsink);

gcap = zeros(nb, 1);
gon = mpc.gen(:, GEN_STATUS) > 0;
for k = find(gon)'
    ri = id2row(mpc.gen(k, GEN_BUS));
    gcap(ri) = gcap(ri) + max(mpc.gen(k, PMAX), 0);
end

ptdf_rows = {};
for s = 1:numel(zone_letters)
    if s == sinkz, continue; end
    wsrc = zeros(nb, 1);
    wsrc(zvec == s) = gcap(zvec == s);
    if sum(wsrc) <= 0, continue; end
    wsrc = wsrc / sum(wsrc);
    dP = options.transfer_mw * (wsrc - wsink);
    fbr = H * dP;
    for c = 1:height(cut)
        a = zidx(cut.zone_from{c}); b = zidx(cut.zone_to{c});
        sel = on & ((zf == a & zt == b) | (zf == b & zt == a));
        idx = find(sel);
        sgn = ones(numel(idx), 1); sgn(zf(idx) == b) = -1;
        ptdf_rows(end+1, :) = {sprintf('%s_to_%s', zone_letters{s}, ...
            options.sink_zone), zone_letters{s}, options.sink_zone, ...
            cut.cut{c}, options.transfer_mw, sum(sgn .* fbr(idx))}; %#ok<AGROW>
    end
end
ptdf = cell2table(ptdf_rows, 'VariableNames', {'transfer', 'source_zone', ...
    'sink_zone', 'cut', 'transfer_mw', 'cut_flow_mw'});

if options.write
    writetable(cut, fullfile(nylite, 'ny_core_cutset_reference.csv'));
    writetable(official, fullfile(nylite, 'ny_core_official_share_reference.csv'));
    writetable(ptdf, fullfile(nylite, 'ny_core_ptdf_reference.csv'));
    fprintf('wrote ny_core_cutset_reference.csv (%d cuts)\n', height(cut));
    fprintf('wrote ny_core_official_share_reference.csv (%d interfaces)\n', height(official));
    fprintf('wrote ny_core_ptdf_reference.csv (%d rows)\n', height(ptdf));
end

out = struct('cut', cut, 'official', official, 'ptdf', ptdf, ...
    'zone', {zone}, 'n_zone_d_moved', n_moved);
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
