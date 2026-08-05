% s12_reduce_perform: retention-set-driven Ward/Kron reduction of the
% PERFORM 2019 NY case. Exact at the snapshot by construction:
%  - all generator buses retained (generation stays native);
%  - all monitored circuits and DLR corridors copied verbatim;
%  - eliminated buses (load-only) Kron-eliminated with their constant-current
%    load injections Ward-mapped to retained buses, zone-labeled.
root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
perform_dir = fullfile(root, 'PERFORM', 'On Peak 2019 v23_Perform_NY', 'On Peak 2019 v23');
nylite = fullfile(root, 'System Matpower Format', 'NY_Lite');
case_dir = fullfile(root, 'System Matpower Format');
addpath(root, case_dir, nylite, perform_dir);
define_constants;

mpc = loadcase('nyiso_On_Peak_v23_shunts_as_z_load');
nb = size(mpc.bus, 1);
bus_ids = mpc.bus(:, BUS_I);
id2row = containers.Map(bus_ids, 1:nb);

% ---- retention set: CSV + all gen buses (incl. offline)
ret_tbl = readtable(fullfile(nylite, 's12_retention_set.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
retained_ids = unique([ret_tbl.source_bus; mpc.gen(:, GEN_BUS)]);
ret_rows = cellfun(@(b) id2row(b), num2cell(retained_ids));
nR = numel(retained_ids);
elim_mask = true(nb, 1); elim_mask(ret_rows) = false;
elim_rows = find(elim_mask);
nE = numel(elim_rows);
fprintf('retained %d, eliminated %d\n', nR, nE);
assert(~any(ismember(mpc.gen(:, GEN_BUS), bus_ids(elim_rows))), ...
    'eliminated bus hosts a generator');

% ---- zone letters by area from control map
ctrl = readtable(fullfile(nylite, 'perform_source_to_reduced_control_mapping.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
areas = unique(mpc.bus(:, BUS_AREA));
area_letter = strings(numel(areas), 1);
for a = 1:numel(areas)
    zbus = bus_ids(mpc.bus(:, BUS_AREA) == areas(a));
    zl = ctrl.source_zone(ismember(ctrl.source_bus, zbus));
    zl = zl(strlength(zl) == 1);
    assert(~isempty(zl), 'no zone letter found for area %d', areas(a));
    area_letter(a) = mode(categorical(zl));
end
fprintf('area->zone: ');
for a = 1:numel(areas), fprintf('%d=%s ', areas(a), area_letter(a)); end
fprintf('\n');

% ---- source reference solution
mpopt = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 1);
src = runpf(mpc, mpopt);
assert(src.success == 1, 'source Q-limit PF failed');
V0 = src.bus(:, VM) .* exp(1j * src.bus(:, VA) * pi / 180);

% ---- Ybus partition and Schur complement
[Ybus, ~, ~] = makeYbus(mpc.baseMVA, mpc.bus, mpc.branch);
Yrr = Ybus(ret_rows, ret_rows);
Yre = Ybus(ret_rows, elim_rows);
Yer = Ybus(elim_rows, ret_rows);
Yee = Ybus(elim_rows, elim_rows);
X = Yee \ Yer;              % nE x nR
Yred = Yrr - Yre * X;
W = -(Yee.' \ Yre.').';     % nR x nE  (maps eliminated injections to retained)

% ---- eliminated load currents at snapshot, zone-labeled mapping
S_load_E = (mpc.bus(elim_rows, PD) + 1j * mpc.bus(elim_rows, QD)) / mpc.baseMVA;
I_E = conj(-S_load_E ./ V0(elim_rows));  % nodal injection current of loads
elim_area = mpc.bus(elim_rows, BUS_AREA);
nZ = numel(areas);
P_jz = zeros(nR, nZ); Q_jz = zeros(nR, nZ);
for z = 1:nZ
    ecols = elim_area == areas(z);
    if ~any(ecols), continue; end
    Imap = W(:, ecols) * I_E(ecols);
    Smap = V0(ret_rows) .* conj(Imap);        % injection at retained buses
    P_jz(:, z) = -real(Smap) * mpc.baseMVA;   % load = minus injection
    Q_jz(:, z) = -imag(Smap) * mpc.baseMVA;
end
fprintf('mapped eliminated load: %.1f MW (source eliminated PD %.1f MW)\n', ...
    sum(P_jz(:)), sum(mpc.bus(elim_rows, PD)));

% ---- identity check: Yred * V0_R == I_R + W*I_E
S_inj_R = (src.gen(:, PG) * 0); % placeholder
Sbus_R = -(mpc.bus(ret_rows, PD) + 1j * mpc.bus(ret_rows, QD)) / mpc.baseMVA;
for g = 1:size(src.gen, 1)
    r = find(retained_ids == src.gen(g, GEN_BUS), 1);
    if src.gen(g, GEN_STATUS) > 0
        Sbus_R(r) = Sbus_R(r) + (src.gen(g, PG) + 1j * src.gen(g, QG)) / mpc.baseMVA;
    end
end
I_R = conj(Sbus_R ./ V0(ret_rows));
resid = Yred * V0(ret_rows) - (I_R + W * I_E);
fprintf('Ward identity max residual: %.3e pu current\n', full(max(abs(resid))));

% ---- reduced case assembly
red = struct();
red.version = '2';
red.baseMVA = mpc.baseMVA;
red.bus = mpc.bus(ret_rows, :);
red.bus_name = mpc.bus_name(ret_rows);
red.gen = mpc.gen;
red.gencost = [];
if isfield(mpc, 'gencost'), red.gencost = mpc.gencost; end
if isfield(mpc, 'genfuel'), red.genfuel = mpc.genfuel; end

% total bus load = own + mapped
red.bus(:, PD) = red.bus(:, PD) + sum(P_jz, 2);
red.bus(:, QD) = red.bus(:, QD) + sum(Q_jz, 2);
% start voltages at snapshot
red.bus(:, VM) = abs(V0(ret_rows));
red.bus(:, VA) = angle(V0(ret_rows)) * 180 / pi;

% renumber buses consecutively 1..nR (source ids kept in userdata/CSV)
old2new = sparse(retained_ids, 1, 1:nR);
red.bus(:, BUS_I) = 1:nR;
red.gen(:, GEN_BUS) = full(old2new(red.gen(:, GEN_BUS)));

% retained branches copied verbatim
keep_mask = ismember(mpc.branch(:, F_BUS), retained_ids) & ...
            ismember(mpc.branch(:, T_BUS), retained_ids);
keep_rows = find(keep_mask);
red.branch = mpc.branch(keep_rows, :);
red.branch(:, F_BUS) = full(old2new(red.branch(:, F_BUS)));
red.branch(:, T_BUS) = full(old2new(red.branch(:, T_BUS)));
fprintf('retained branches: %d\n', numel(keep_rows));

% equivalent network = Yred minus what the kept skeleton provides
Ykeep = makeYbus(red.baseMVA, red.bus, red.branch);
Yeq = Yred - Ykeep;
Yeq_offdiag = Yeq - spdiags(diag(Yeq), 0, nR, nR);
[ii, jj, vv] = find(tril(Yeq_offdiag, -1));
tol_y = 1e-5;
big = abs(vv) > tol_y;
fprintf('equivalent couplings: %d total, %d above tol %.0e\n', numel(vv), sum(big), tol_y);
eq_i = ii(big); eq_j = jj(big); eq_y = -vv(big);   % series admittance
neq = numel(eq_y);
eqb = zeros(neq, size(red.branch, 2));
eqb(:, F_BUS) = eq_i;
eqb(:, T_BUS) = eq_j;
z = 1 ./ eq_y;
eqb(:, BR_R) = real(z);
eqb(:, BR_X) = imag(z);
eqb(:, BR_STATUS) = 1;
eqb(:, RATE_A) = 0;
eqb(:, ANGMIN) = -360; eqb(:, ANGMAX) = 360;
red.branch = [red.branch; eqb];

% diagonal remainder -> equivalent bus shunts (exact diagonal)
diag_from_eq = accumarray(eq_i, eq_y, [nR 1]) + accumarray(eq_j, eq_y, [nR 1]);
% asymmetry check
asym = max(max(abs(Yeq_offdiag - Yeq_offdiag.')));
fprintf('Yeq asymmetry: %.3e\n', full(asym));
d_rem = diag(Yeq) - diag_from_eq + ...
    (accumarray(eq_i, -eq_y, [nR 1]) + accumarray(eq_j, -eq_y, [nR 1])) * 0; % clarity
% dropped off-diagonals: keep their diagonal effect (already in diag(Yeq));
% subtracting only the kept equivalent branches' series terms:
d_rem = diag(Yeq) - diag_from_eq;
red.bus(:, GS) = red.bus(:, GS) + real(d_rem) * red.baseMVA;
red.bus(:, BS) = red.bus(:, BS) + imag(d_rem) * red.baseMVA;

% ---- verify reduced Ybus equals Yred (up to dropped couplings)
Ychk = makeYbus(red.baseMVA, red.bus, red.branch);
err_full = max(max(abs(Ychk - Yred)));
fprintf('reduced-Ybus reconstruction max error: %.3e (dropped couplings only)\n', full(err_full));

% ---- snapshot PF validation
val = red;
for g = 1:size(val.gen, 1)
    if val.gen(g, GEN_STATUS) > 0
        val.gen(g, PG) = src.gen(g, PG);
        val.gen(g, QG) = src.gen(g, QG);
        r = val.gen(g, GEN_BUS);   % internal numbering equals retained row index
        val.gen(g, VG) = abs(V0(ret_rows(r)));
    end
end
res = runpf(val, mpoption('verbose', 0, 'out.all', 0));
assert(res.success == 1, 'reduced snapshot PF failed');
vm_err = res.bus(:, VM) - abs(V0(ret_rows));
va_err = res.bus(:, VA) - angle(V0(ret_rows)) * 180 / pi;
fprintf('snapshot voltage error: RMSE %.6f pu, max %.6f pu, max angle %.4f deg\n', ...
    sqrt(mean(vm_err.^2)), max(abs(vm_err)), max(abs(va_err)));

% monitored circuit flow comparison
map = readtable(fullfile(nylite, 'nyiso_interface_branch_map.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
mon_rows_src = [];
for k = 1:height(map)
    toks = split(map.source_branch_rows(k), ';');
    for t = 1:numel(toks)
        v = str2double(toks(t));
        if isfinite(v), mon_rows_src(end+1) = v; end %#ok<SAGROW>
    end
end
mon_rows_src = unique([mon_rows_src, 1635]);
src2red_branch = zeros(size(mpc.branch, 1), 1);
src2red_branch(keep_rows) = 1:numel(keep_rows);
flow_err = zeros(numel(mon_rows_src), 1);
for k = 1:numel(mon_rows_src)
    sr = mon_rows_src(k);
    rr = src2red_branch(sr);
    assert(rr > 0, 'monitored source branch %d not retained', sr);
    flow_err(k) = res.branch(rr, PF) - src.branch(sr, PF);
end
fprintf('monitored-circuit PF flow error: max %.4f MW, RMSE %.4f MW over %d circuits\n', ...
    max(abs(flow_err)), sqrt(mean(flow_err.^2)), numel(mon_rows_src));

% ---- persist
red.userdata = struct();
red.userdata.s12_zone_area_codes = areas(:)';
red.userdata.s12_zone_letters = cellstr(area_letter)';
red.userdata.s12_retained_source_bus = retained_ids(:)';
save(fullfile(nylite, 's12_reduction_workspace.mat'), 'red', 'P_jz', 'Q_jz', ...
    'retained_ids', 'keep_rows', 'src2red_branch', 'areas', 'area_letter', ...
    'mon_rows_src', '-v7.3');
fprintf('saved s12_reduction_workspace.mat\n');
