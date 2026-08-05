function [mpc, report] = apply_perform_tieline_alignment(mpc, mode)
%APPLY_PERFORM_TIELINE_ALIGNMENT Align direct NY-lite corridors to PERFORM.
%   mode = current      : no parameter changes
%          perform_rx   : PERFORM parallel R/X and ratings, retain B = 0
%          perform_rxb  : PERFORM parallel R/X/B and ratings

if nargin < 2 || isempty(mode), mode = 'perform_rx'; end
mode = lower(string(mode));
if ~ismember(mode, ["current", "perform_rx", "perform_rxb"])
    error('Unknown PERFORM tie alignment mode %s.', mode);
end
define_constants;
report = table();

specs = struct( ...
    'name', {'GILBOA_LEEDS', 'PLEASANT_VLY_WOOD_STREET', ...
    'WOOD_STREET_MILLWOOD'}, ...
    'r', {0.00131, 0.000405, 0.000185}, ...
    'x', {0.01997, 0.006185, 0.002815}, ...
    'b', {0.51614, 0.63943, 0.29107}, ...
    'rate_a', {1216, 2432, 2432}, ...
    'rate_b', {2454, 4908, 4908}, ...
    'rate_c', {1804, 3608, 3608}, ...
    'source', {'PERFORM direct circuit', ...
    'PERFORM two-circuit parallel equivalent', ...
    'PERFORM two-circuit parallel equivalent'});

for k = 1:numel(specs)
    idx = find_added_branch(mpc, specs(k).name);
    if isempty(idx)
        error('Added NY-lite branch %s is not present.', specs(k).name);
    end
    old = mpc.branch(idx, [BR_R BR_X BR_B RATE_A RATE_B RATE_C]);
    if mode ~= "current"
        b = 0;
        if mode == "perform_rxb" || strcmp(specs(k).name, 'GILBOA_LEEDS')
            b = specs(k).b;
        end
        mpc.branch(idx, [BR_R BR_X BR_B RATE_A RATE_B RATE_C]) = ...
            [specs(k).r specs(k).x b specs(k).rate_a specs(k).rate_b specs(k).rate_c];
    end
    new = mpc.branch(idx, [BR_R BR_X BR_B RATE_A RATE_B RATE_C]);
    row = table(mode, string(specs(k).name), idx, old(1), old(2), old(3), ...
        old(4), new(1), new(2), new(3), new(4), string(specs(k).source), ...
        'VariableNames', {'mode','branch_name','branch_index','old_r_pu', ...
        'old_x_pu','old_b_pu','old_rate_a_mva','new_r_pu','new_x_pu', ...
        'new_b_pu','new_rate_a_mva','parameter_source'});
    if isempty(report), report = row; else, report = [report; row]; end %#ok<AGROW>
end
if ~isfield(mpc, 'userdata'), mpc.userdata = struct(); end
if ~isfield(mpc.userdata, 'ny_lite'), mpc.userdata.ny_lite = struct(); end
mpc.userdata.ny_lite.perform_tieline_alignment_mode = char(mode);
mpc.userdata.ny_lite.perform_tieline_alignment_report = report;
end

function idx = find_added_branch(mpc, name)
idx = [];
if ~isfield(mpc, 'userdata') || ~isfield(mpc.userdata, 'ny_lite') || ...
        ~isfield(mpc.userdata.ny_lite, 'added_tielines')
    return;
end
added = mpc.userdata.ny_lite.added_tielines;
for k = 1:numel(added)
    if isfield(added(k), 'name') && strcmp(added(k).name, name) && ...
            isfield(added(k), 'branch_index')
        idx = added(k).branch_index;
        return;
    end
end
end
