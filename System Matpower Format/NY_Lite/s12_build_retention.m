% s12_build_retention: define the S12 retention set from PERFORM.
root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
perform_dir = fullfile(root, 'PERFORM', 'On Peak 2019 v23_Perform_NY', 'On Peak 2019 v23');
nylite = fullfile(root, 'System Matpower Format', 'NY_Lite');
addpath(root, fullfile(root, 'System Matpower Format'), nylite, perform_dir);
define_constants;

mpc = loadcase('nyiso_On_Peak_v23_shunts_as_z_load');
nb = size(mpc.bus, 1);
bus_ids = mpc.bus(:, BUS_I);
id2row = sparse(bus_ids, 1, 1:nb);

% --- R1: monitored-circuit endpoints (interface map source rows + Gilboa-Leeds row 1635)
map = readtable(fullfile(nylite, 'nyiso_interface_branch_map.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
mon_rows = [];
for k = 1:height(map)
    toks = split(map.source_branch_rows(k), ';');
    for t = 1:numel(toks)
        v = str2double(toks(t));
        if isfinite(v), mon_rows(end+1) = v; end %#ok<SAGROW>
    end
end
mon_rows = unique([mon_rows, 1635]);   % 1635 = Leeds-Gilboa DLR circuit
r1 = unique([mpc.branch(mon_rows, F_BUS); mpc.branch(mon_rows, T_BUS)]);

% --- R2: switched-shunt buses from RAW
raw_file = fullfile(perform_dir, 'NYISO_onpeak2019_v23_shuntsRgens.RAW');
lines = readlines(raw_file);
ss_b = find(contains(lines, 'BEGIN SWITCHED SHUNT'), 1);
ss_e = find(contains(lines, 'END OF SWITCHED SHUNT'), 1);
r2 = [];
for L = (ss_b+1):(ss_e-1)
    toks = split(lines(L), ',');
    r2(end+1) = str2double(toks(1)); %#ok<SAGROW>
end
r2 = unique(r2(:));

% --- R3: buses hosting online generators or boundary import equivalents
ctrl = readtable(fullfile(nylite, 'perform_source_to_reduced_control_mapping.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
online_gen_bus = unique(mpc.gen(mpc.gen(:, GEN_STATUS) > 0, GEN_BUS));
boundary_bus = unique(ctrl.source_bus(ctrl.device_class == "boundary_import_equivalent"));
r3 = unique([online_gen_bus; boundary_bus]);

% --- R4: high-voltage backbone
kv = mpc.bus(:, BASE_KV);
fprintf('bus count by kV class: 765:%d 345:%d 230:%d 115-138:%d <115:%d\n', ...
    sum(kv >= 700), sum(kv >= 300 & kv < 700), sum(kv >= 200 & kv < 300), ...
    sum(kv >= 100 & kv < 200), sum(kv < 100));
r4 = bus_ids(kv >= 200);

retained = unique([r1; r2; r3; r4]);

% --- R5: zone coverage for load hosting
areas = mpc.bus(:, BUS_AREA);
fprintf('\nzone coverage before R5:\n');
extra = [];
for a = unique(areas)'
    zmask = areas == a;
    zbus = bus_ids(zmask);
    zload = mpc.bus(zmask, PD);
    ret_mask = ismember(zbus, retained);
    fprintf('area %d: buses=%d retained=%d zone_load=%.1f retained_load=%.1f\n', ...
        a, sum(zmask), sum(ret_mask), sum(zload), sum(zload(ret_mask)));
    % ensure at least 5 load-hosting retained buses per zone
    if sum(ret_mask & zload > 0) < 5
        [~, order] = sort(zload, 'descend');
        need = zbus(order(1:min(5, numel(order))));
        extra = [extra; need(~ismember(need, retained))]; %#ok<AGROW>
    end
end
retained = unique([retained; extra]);

ret_rows = full(id2row(retained));
fprintf('\nTotal retained buses: %d of %d\n', numel(retained), nb);
fprintf('retained load: %.1f of %.1f MW (%.1f%%)\n', ...
    sum(mpc.bus(ret_rows, PD)), sum(mpc.bus(:, PD)), ...
    100 * sum(mpc.bus(ret_rows, PD)) / sum(mpc.bus(:, PD)));

% zero-injection eliminated buses (exact Kron candidates)
has_load = mpc.bus(:, PD) ~= 0 | mpc.bus(:, QD) ~= 0;
gen_bus_all = unique(mpc.gen(:, GEN_BUS));
has_gen = ismember(bus_ids, gen_bus_all);
elim = ~ismember(bus_ids, retained);
fprintf('eliminated buses: %d (zero-injection: %d, load-carrying: %d, gen-carrying: %d)\n', ...
    sum(elim), sum(elim & ~has_load & ~has_gen), sum(elim & has_load), sum(elim & has_gen));

% write retention CSV with reasons
reason = strings(numel(retained), 1);
for i = 1:numel(retained)
    b = retained(i); r = "";
    if ismember(b, r1), r = r + "monitored_circuit;"; end
    if ismember(b, r2), r = r + "switched_shunt;"; end
    if ismember(b, r3), r = r + "generator_or_boundary;"; end
    if ismember(b, r4), r = r + "hv_backbone;"; end
    if r == "", r = "zone_load_coverage;"; end
    reason(i) = r;
end
rows = full(id2row(retained));
tbl = table(retained, string(mpc.bus_name(rows)), mpc.bus(rows, BASE_KV), ...
    mpc.bus(rows, BUS_AREA), mpc.bus(rows, PD), reason, ...
    'VariableNames', {'source_bus', 'bus_name', 'base_kv', 'area', 'pd_mw', 'retention_reason'});
writetable(tbl, fullfile(nylite, 's12_retention_set.csv'));
fprintf('wrote s12_retention_set.csv (%d rows)\n', height(tbl));
