% s12_persist_case: attach interface operators, external boundary groups,
% zone-labeled load components, and device metadata to the S12 reduced case;
% write authoritative .mat plus network .m and CSV sidecars.
root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
perform_dir = fullfile(root, 'PERFORM', 'On Peak 2019 v23_Perform_NY', 'On Peak 2019 v23');
nylite = fullfile(root, 'System Matpower Format', 'NY_Lite');
case_dir = fullfile(root, 'System Matpower Format');
addpath(root, case_dir, nylite, perform_dir);
define_constants;

ws = load(fullfile(nylite, 's12_reduction_workspace.mat'));
red = ws.red; retained_ids = ws.retained_ids; src2red = ws.src2red_branch;
areas = ws.areas; area_letter = ws.area_letter;
nR = size(red.bus, 1);

mpc = loadcase('nyiso_On_Peak_v23_shunts_as_z_load');
mpopt = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 1);
src = runpf(mpc, mpopt);
area_of_id = containers.Map(mpc.bus(:, BUS_I), mpc.bus(:, BUS_AREA));
letter_of_area = containers.Map(num2cell(areas), cellstr(area_letter));

% ---------- interface operators ----------
map = readtable(fullfile(nylite, 'nyiso_interface_branch_map.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
west = containers.Map( ...
    {'Dysinger_East', 'West_Central', 'Moses_South', 'Central_East', ...
     'Total_East_proxy', 'UPNY_ConEd', 'Dunwoodie_South'}, ...
    {"A", "AB", "D", "ABCDE", "ABCDE", "ABCDEF G", "ABCDEFGHI"});
op = table();
for k = 1:height(map)
    iname = map.interface_name(k);
    toks = split(map.source_branch_rows(k), ';');
    for t = 1:numel(toks)
        sr = str2double(toks(t));
        if ~isfinite(sr), continue; end
        rr = src2red(sr);
        assert(rr > 0);
        fz = string(letter_of_area(area_of_id(mpc.branch(sr, F_BUS))));
        tz = string(letter_of_area(area_of_id(mpc.branch(sr, T_BUS))));
        wset = erase(string(west(char(iname))), " ");
        f_in = contains(wset, fz); t_in = contains(wset, tz);
        if f_in && ~t_in
            sgn = 1; rule = "area_rule";
        elseif t_in && ~f_in
            sgn = -1; rule = "area_rule";
        else
            sgn = sign(src.branch(sr, PF));
            if sgn == 0, sgn = 1; end
            rule = "snapshot_direction_fallback";
        end
        op = [op; table(iname, sr, rr, fz, tz, sgn, rule, ...
            map.source_monitored_circuit(k), map.mapping_confidence(k), ...
            'VariableNames', {'interface_name', 'source_branch', 'reduced_branch', ...
            'from_zone', 'to_zone', 'sign', 'sign_rule', 'monitored_circuit', ...
            'mapping_confidence'})]; %#ok<AGROW>
    end
end
% deduplicate identical (interface, source row) pairs (map lists Moses rows 5x)
[~, iu] = unique(op.interface_name + "|" + string(op.source_branch));
op = op(sort(iu), :);

% snapshot interface sums, source truth vs reduced
fprintf('\nSnapshot interface sums (MW):\n');
val = red;
for g = 1:size(val.gen, 1)
    if val.gen(g, GEN_STATUS) > 0
        val.gen(g, PG) = src.gen(g, PG); val.gen(g, QG) = src.gen(g, QG);
        val.gen(g, VG) = red.bus(val.gen(g, GEN_BUS), VM);
    end
end
resred = runpf(val, mpoption('verbose', 0, 'out.all', 0));
ifc_names = unique(op.interface_name, 'stable');
snap = table();
for k = 1:numel(ifc_names)
    rows = op(op.interface_name == ifc_names(k), :);
    s_src = sum(rows.sign .* src.branch(rows.source_branch, PF));
    s_red = sum(rows.sign .* resred.branch(rows.reduced_branch, PF));
    fprintf('  %-18s source %9.2f  reduced %9.2f  circuits %d\n', ...
        ifc_names(k), s_src, s_red, height(rows));
    snap = [snap; table(ifc_names(k), height(rows), s_src, s_red, ...
        'VariableNames', {'interface_name', 'circuit_count', ...
        'source_snapshot_mw', 'reduced_snapshot_mw'})]; %#ok<AGROW>
end
writetable(op, fullfile(nylite, 's12_interface_operators.csv'));
writetable(snap, fullfile(nylite, 's12_interface_snapshot_sums.csv'));

% ---------- external boundary schedule groups ----------
grp = { ...
 1231, 'SCH - HQ - NY'; 1546, 'SCH - HQ - NY'; ...
 1313, 'SCH - OH - NY'; 1570, 'SCH - OH - NY'; ...
 799,  'SCH - NE - NY'; 651, 'SCH - NE - NY'; ...
 19,   'SCH - NPX_1385'; 1148, 'SCH - NPX_CSC'; ...
 580,  'SCH - PJM_NEPTUNE'; 1136, 'SCH - PJM_HTP'; 1528, 'SCH - PJM_VFT'; ...
 773,  'SCH - PJ - NY'; 756, 'SCH - PJ - NY'; 1132, 'SCH - PJ - NY'; ...
 571,  'SCH - PJ - NY'; 69, 'SCH - PJ - NY'; 1413, 'SCH - PJ - NY'; ...
 1320, 'SCH - PJ - NY'; 1558, 'SCH - PJ - NY'; 81, 'SCH - PJ - NY'};
ext = table();
for k = 1:size(grp, 1)
    sb = grp{k, 1};
    gi = find(mpc.gen(:, GEN_BUS) == sb & mpc.gen(:, PMIN) == mpc.gen(:, PMAX) ...
        | mpc.gen(:, GEN_BUS) == sb, 1);
    gset = find(mpc.gen(:, GEN_BUS) == sb);
    % boundary equivalents: pick the fixed-P record(s) at this bus
    for gi = gset'
        if mpc.gen(gi, PMIN) ~= mpc.gen(gi, PMAX) && numel(gset) > 1
            continue;  % skip native units co-located at the boundary bus
        end
        ext = [ext; table(sb, gi, red.gen(gi, GEN_BUS), string(grp{k, 2}), ...
            src.gen(gi, PG), src.gen(gi, QG), mpc.gen(gi, GEN_STATUS), ...
            'VariableNames', {'source_bus', 'gen_index', 'reduced_bus', ...
            'p32_interface_name', 'snapshot_pg_mw', 'snapshot_qg_mvar', 'status'})]; %#ok<AGROW>
    end
end
writetable(ext, fullfile(nylite, 's12_external_boundary_groups.csv'));
fprintf('\nexternal boundary group snapshot totals:\n');
gs = groupsummary(ext, 'p32_interface_name', 'sum', 'snapshot_pg_mw');
disp(gs);

% ---------- switched shunt metadata ----------
raw_lines = readlines(fullfile(perform_dir, 'NYISO_onpeak2019_v23_shuntsRgens.RAW'));
ss_b = find(contains(raw_lines, 'BEGIN SWITCHED SHUNT'), 1);
ss_e = find(contains(raw_lines, 'END OF SWITCHED SHUNT'), 1);
ss = table();
for L = (ss_b+1):(ss_e-1)
    tk = split(raw_lines(L), ',');
    sb = str2double(tk(1));
    ri = find(retained_ids == sb, 1);
    ss = [ss; table(sb, ri, str2double(tk(2)), str2double(tk(5)), ...
        str2double(tk(6)), str2double(tk(10)), strtrim(raw_lines(L)), ...
        'VariableNames', {'source_bus', 'reduced_bus', 'modsw', 'vswhi', ...
        'vswlo', 'binit_mvar', 'raw_record'})]; %#ok<AGROW>
end
assert(all(isfinite(ss.reduced_bus)), 'switched shunt bus not retained');
writetable(ss, fullfile(nylite, 's12_switched_shunts.csv'));
fprintf('switched shunts preserved at retained buses: %d (BINIT total %.1f MVAr)\n', ...
    height(ss), sum(ss.binit_mvar));

% ---------- zone-labeled base load components ----------
PB = ws.P_jz; QB = ws.Q_jz;
own_area = red.bus(:, BUS_AREA);
for j = 1:nR
    z = find(areas == own_area(j), 1);
    own_pd = red.bus(j, PD) - sum(PB(j, :), 2);
    own_qd = red.bus(j, QD) - sum(QB(j, :), 2);
    PB(j, z) = PB(j, z) + own_pd;
    QB(j, z) = QB(j, z) + own_qd;
end
fprintf('zone base loads (MW): ');
for z = 1:numel(areas), fprintf('%s=%.0f ', area_letter(z), sum(PB(:, z))); end
fprintf('\n  total %.1f (source total %.1f)\n', sum(PB(:)), sum(mpc.bus(:, PD)));

% ---------- persist ----------
s12 = red;
s12.userdata.s12_interface_operators = op;
s12.userdata.s12_external_groups = ext;
s12.userdata.s12_switched_shunts = ss;
s12.userdata.s12_zone_base_load_p = PB;
s12.userdata.s12_zone_base_load_q = QB;
s12.userdata.s12_provenance = ['Retention-set Ward/Kron reduction of PERFORM ' ...
    'nyiso_On_Peak_v23_shunts_as_z_load; exact snapshot reproduction; built 2026-07-20'];
save(fullfile(nylite, 's12_case.mat'), 's12', '-v7.3');
savecase(fullfile(case_dir, 'npcc_ny_lite_s12_perform_retention_core.m'), red);
fprintf('saved s12_case.mat and npcc_ny_lite_s12_perform_retention_core.m\n');
