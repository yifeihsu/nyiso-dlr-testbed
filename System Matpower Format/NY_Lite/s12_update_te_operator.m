% s12_update_te_operator: rebuild the Total East operator as the boundary
% cut {Central East circuits} + Fraser-Gilboa + Coopers Corner-Rock Tavern.
root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
nylite = fullfile(root, 'System Matpower Format', 'NY_Lite');
perform_dir = fullfile(root, 'PERFORM', 'On Peak 2019 v23_Perform_NY', 'On Peak 2019 v23');
addpath(root, fullfile(root, 'System Matpower Format'), nylite, perform_dir);
define_constants;

ws = load(fullfile(nylite, 's12_case.mat'));
s12 = ws.s12;
op = s12.userdata.s12_interface_operators;
red_ws = load(fullfile(nylite, 's12_reduction_workspace.mat'), 'src2red_branch');
src2red = red_ws.src2red_branch;

mpc = loadcase('nyiso_On_Peak_v23_shunts_as_z_load');
areas = s12.userdata.s12_zone_area_codes(:);
letters = string(s12.userdata.s12_zone_letters(:));
area_of_id = containers.Map(mpc.bus(:, BUS_I), mpc.bus(:, BUS_AREA));
letter_of_area = containers.Map(num2cell(areas), cellstr(letters));

ce = op(op.interface_name == "Central_East", :);
te_extra_src = [2136, 1567, 1568];
te = ce;
te.interface_name(:) = "Total_East_proxy";
te.monitored_circuit(:) = "Central East element within Total East composite";
west = "ABCDE";
for k = 1:numel(te_extra_src)
    sr = te_extra_src(k);
    rr = src2red(sr);
    assert(rr > 0, 'TE extra source branch %d not retained', sr);
    fz = string(letter_of_area(area_of_id(mpc.branch(sr, F_BUS))));
    tz = string(letter_of_area(area_of_id(mpc.branch(sr, T_BUS))));
    f_in = contains(west, fz); t_in = contains(west, tz);
    assert(f_in ~= t_in, 'TE extra branch %d does not cross boundary', sr);
    sgn = 1; if t_in, sgn = -1; end
    names = ["Fraser-Gilboa GF5-35", "Coopers Corner-Rock Tavern CKT1", ...
        "Coopers Corner-Rock Tavern CKT2"];
    te = [te; table("Total_East_proxy", sr, rr, fz, tz, sgn, "area_rule", ...
        names(k), "medium", 'VariableNames', op.Properties.VariableNames)]; %#ok<AGROW>
end
op = [op(op.interface_name ~= "Total_East_proxy", :); te];
expected_te_source_rows = sort([935; 1345; 1346; 1567; 1568; 1609; 1612; 2136]);
actual_te_source_rows = sort(te.source_branch);
assert(height(te) == 8 && ...
    numel(unique(te.source_branch)) == 8 && ...
    isequal(actual_te_source_rows, expected_te_source_rows), ...
    ['Total_East_proxy must contain exactly the five Central East rows plus ' ...
    'Fraser-Gilboa and both Coopers Corner-Rock Tavern circuits.']);
s12.userdata.s12_interface_operators = op;

% snapshot sums with new operator
mpopt = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 1);
src = runpf(mpc, mpopt);
rows = op(op.interface_name == "Total_East_proxy", :);
fprintf('new Total East operator: %d circuits, source snapshot sum %.2f MW\n', ...
    height(rows), sum(rows.sign .* src.branch(rows.source_branch, PF)));

ws.s12 = s12;
save(fullfile(nylite, 's12_case.mat'), '-struct', 'ws');
ny_lite_writetable_lf(op, fullfile(nylite, 's12_interface_operators.csv'));
fprintf('updated s12_case.mat and s12_interface_operators.csv\n');
