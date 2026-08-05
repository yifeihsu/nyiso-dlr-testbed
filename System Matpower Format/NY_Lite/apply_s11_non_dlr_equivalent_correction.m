function [mpc, report] = apply_s11_non_dlr_equivalent_correction( ...
        mpc, branch_map, correction)
%APPLY_S11_NON_DLR_EQUIVALENT_CORRECTION Apply a fitted S11 correction.
%   [MPC, REPORT] = APPLY_S11_NON_DLR_EQUIVALENT_CORRECTION(MPC,
%   BRANCH_MAP, CORRECTION) changes only explicitly selected non-DLR branch
%   R/X/B values, supported tap/shift overrides, and retained-bus GS/BS.
%   The five direct physical DLR rows are checked before and after and must
%   remain exactly unchanged.
%
%   CORRECTION may be a struct or a MAT-file containing a variable named
%   correction. Its public schema is:
%       scaled_branch_indices       selected non-DLR rows
%       selected_r_scale            common R multiplier
%       selected_x_scale            common X multiplier
%       selected_b_scale            common B multiplier
%       branch_overrides            optional table, absolute multipliers
%       bus_shunt_corrections       optional table of delta GS/BS

if nargin < 3
    error('apply_s11_non_dlr_equivalent_correction:MissingInput', ...
        'MPC, BRANCH_MAP, and CORRECTION are required.');
end
if ischar(mpc) || isstring(mpc), mpc = loadcase(char(mpc)); end
if isfield(mpc, 'userdata') && isfield(mpc.userdata, 's11') && ...
        isfield(mpc.userdata.s11, 'non_dlr_equivalent_correction')
    error('apply_s11_non_dlr_equivalent_correction:AlreadyApplied', ...
        'The S11 non-DLR correction is already present on this case.');
end
if ~istable(branch_map)
    error('apply_s11_non_dlr_equivalent_correction:BranchMap', ...
        'branch_map must be the table returned by split_perform_parallel_corridors.');
end
correction = load_correction(correction);
define_constants;

required_map = {'branch_index','branch_classification','physical_circuit_id'};
if height(branch_map) ~= size(mpc.branch, 1) || ...
        ~all(ismember(required_map, branch_map.Properties.VariableNames))
    error('apply_s11_non_dlr_equivalent_correction:BranchMapAlignment', ...
        'branch_map is not aligned with the supplied branch matrix.');
end
physical = branch_map.branch_classification == "physical_circuit";
physical_idx = branch_map.branch_index(physical);
if numel(physical_idx) ~= 5
    error('apply_s11_non_dlr_equivalent_correction:PhysicalCircuitCount', ...
        'Exactly five physical DLR branch rows must be frozen.');
end
frozen_columns = [F_BUS T_BUS BR_R BR_X BR_B RATE_A RATE_B RATE_C ...
    TAP SHIFT BR_STATUS ANGMIN ANGMAX];
physical_before = mpc.branch(physical_idx, frozen_columns);

scaled_idx = double(correction.scaled_branch_indices(:));
validate_branch_indices(scaled_idx, size(mpc.branch, 1), ...
    'scaled_branch_indices');
if any(ismember(scaled_idx, physical_idx))
    error('apply_s11_non_dlr_equivalent_correction:DLRScaleAttempt', ...
        'A selected scaling row is a frozen physical DLR circuit.');
end

r_scale = scalar_field(correction, 'selected_r_scale', 1);
x_scale = scalar_field(correction, 'selected_x_scale', 1);
b_scale = scalar_field(correction, 'selected_b_scale', 1);
validateattributes(r_scale, {'numeric'}, {'scalar','finite','>=',0.05,'<=',5});
validateattributes(x_scale, {'numeric'}, {'scalar','finite','>=',0.05,'<=',5});
validateattributes(b_scale, {'numeric'}, {'scalar','finite','>=',0,'<=',5});

branch_before = mpc.branch;
mpc.branch(scaled_idx, BR_R) = branch_before(scaled_idx, BR_R) * r_scale;
mpc.branch(scaled_idx, BR_X) = branch_before(scaled_idx, BR_X) * x_scale;
mpc.branch(scaled_idx, BR_B) = branch_before(scaled_idx, BR_B) * b_scale;

override_idx = zeros(0, 1);
if isfield(correction, 'branch_overrides') && ...
        ~isempty(correction.branch_overrides)
    overrides = correction.branch_overrides;
    if ~istable(overrides) || ...
            ~ismember('branch_index', overrides.Properties.VariableNames)
        error('apply_s11_non_dlr_equivalent_correction:OverrideSchema', ...
            'branch_overrides must be a table containing branch_index.');
    end
    override_idx = double(overrides.branch_index(:));
    validate_branch_indices(override_idx, size(mpc.branch, 1), ...
        'branch_overrides.branch_index');
    if any(ismember(override_idx, physical_idx))
        error('apply_s11_non_dlr_equivalent_correction:DLROverrideAttempt', ...
            'A branch override targets a frozen physical DLR circuit.');
    end
    for k = 1:height(overrides)
        br = override_idx(k);
        mpc = apply_branch_override(mpc, branch_before, overrides, k, br);
    end
end

shunt_bus_idx = zeros(0, 1);
bus_before = mpc.bus;
if isfield(correction, 'bus_shunt_corrections') && ...
        ~isempty(correction.bus_shunt_corrections)
    shunts = correction.bus_shunt_corrections;
    required = {'bus_id','delta_gs_mw','delta_bs_mvar'};
    if ~istable(shunts) || ...
            ~all(ismember(required, shunts.Properties.VariableNames))
        error('apply_s11_non_dlr_equivalent_correction:ShuntSchema', ...
            'bus_shunt_corrections must contain bus_id and delta GS/BS.');
    end
    [found, shunt_bus_idx] = ismember(double(shunts.bus_id), ...
        mpc.bus(:, BUS_I));
    if any(~found) || numel(unique(shunt_bus_idx)) ~= numel(shunt_bus_idx)
        error('apply_s11_non_dlr_equivalent_correction:ShuntBus', ...
            'A shunt-correction bus is missing or duplicated.');
    end
    delta_gs = double(shunts.delta_gs_mw);
    delta_bs = double(shunts.delta_bs_mvar);
    if any(~isfinite(delta_gs) | ~isfinite(delta_bs))
        error('apply_s11_non_dlr_equivalent_correction:ShuntValue', ...
            'All shunt corrections must be finite.');
    end
    mpc.bus(shunt_bus_idx, GS) = mpc.bus(shunt_bus_idx, GS) + delta_gs;
    mpc.bus(shunt_bus_idx, BS) = mpc.bus(shunt_bus_idx, BS) + delta_bs;
end

modified_idx = unique([scaled_idx; override_idx], 'stable');
if any(mpc.branch(modified_idx, BR_R) < 0) || ...
        any(mpc.branch(modified_idx, BR_X) <= 0) || ...
        any(~isfinite(mpc.branch(modified_idx, BR_R))) || ...
        any(~isfinite(mpc.branch(modified_idx, BR_X))) || ...
        any(~isfinite(mpc.branch(modified_idx, BR_B)))
    error('apply_s11_non_dlr_equivalent_correction:BranchPhysics', ...
        'Corrected branches must retain finite R>=0 and X>0.');
end
if any(mpc.bus(shunt_bus_idx, GS) < -1e-9)
    error('apply_s11_non_dlr_equivalent_correction:NegativeConductance', ...
        'A Ward diagonal correction produced negative retained-bus GS.');
end

physical_after = mpc.branch(physical_idx, frozen_columns);
dlr_frozen_exact = isequaln(physical_before, physical_after);
if ~dlr_frozen_exact
    error('apply_s11_non_dlr_equivalent_correction:DLRFreezeFailure', ...
        'A direct physical DLR branch parameter changed.');
end

if size(mpc.branch, 2) >= QT && ~isempty(modified_idx)
    mpc.branch(modified_idx, PF:QT) = 0;
end

branch_changes = branch_change_table(branch_before, mpc.branch, branch_map, ...
    modified_idx);
bus_changes = bus_change_table(bus_before, mpc.bus, shunt_bus_idx);
report = struct();
report.status = 'non_DLR_equivalent_correction_applied';
report.dlr_physical_branch_indices = physical_idx;
report.dlr_frozen_exact = dlr_frozen_exact;
report.selected_branch_count = numel(scaled_idx);
report.override_branch_count = numel(setdiff(override_idx, scaled_idx));
report.changed_branch_count = numel(modified_idx);
report.changed_bus_shunt_count = numel(shunt_bus_idx);
report.branch_changes = branch_changes;
report.bus_shunt_changes = bus_changes;
report.correction = correction;

if ~isfield(mpc, 'userdata'), mpc.userdata = struct(); end
if ~isfield(mpc.userdata, 's11'), mpc.userdata.s11 = struct(); end
mpc.userdata.s11.non_dlr_equivalent_correction = report;
end

function correction = load_correction(input)
if ischar(input) || isstring(input)
    data = load(char(input));
    if ~isfield(data, 'correction')
        error('apply_s11_non_dlr_equivalent_correction:CorrectionFile', ...
            'The MAT-file must contain a variable named correction.');
    end
    correction = data.correction;
else
    correction = input;
end
if ~isstruct(correction) || ...
        ~isfield(correction, 'scaled_branch_indices')
    error('apply_s11_non_dlr_equivalent_correction:CorrectionSchema', ...
        'correction must be a struct containing scaled_branch_indices.');
end
end

function value = scalar_field(s, name, fallback)
if isfield(s, name), value = double(s.(name)); else, value = fallback; end
end

function validate_branch_indices(idx, count, label)
if any(~isfinite(idx) | idx < 1 | idx > count | idx ~= round(idx)) || ...
        numel(unique(idx)) ~= numel(idx)
    error('apply_s11_non_dlr_equivalent_correction:BranchIndex', ...
        '%s contains an invalid or duplicate branch index.', label);
end
end

function mpc = apply_branch_override(mpc, original, overrides, row, br)
define_constants;
fields = {'r_scale','x_scale','b_scale'};
columns = [BR_R BR_X BR_B];
for j = 1:numel(fields)
    if ismember(fields{j}, overrides.Properties.VariableNames)
        value = double(overrides.(fields{j})(row));
        if isfinite(value)
            if value < 0 || (j < 3 && value < 0.05) || value > 5
                error('apply_s11_non_dlr_equivalent_correction:OverrideScale', ...
                    'Invalid %s on branch %d.', fields{j}, br);
            end
            mpc.branch(br, columns(j)) = original(br, columns(j)) * value;
        end
    end
end
if ismember('tap_ratio', overrides.Properties.VariableNames)
    value = double(overrides.tap_ratio(row));
    if isfinite(value)
        if value <= 0 || value < 0.8 || value > 1.2
            error('apply_s11_non_dlr_equivalent_correction:TapBound', ...
                'Tap override on branch %d must be in [0.8, 1.2].', br);
        end
        mpc.branch(br, TAP) = value;
    end
end
if ismember('shift_deg', overrides.Properties.VariableNames)
    value = double(overrides.shift_deg(row));
    if isfinite(value)
        if abs(value) > 30
            error('apply_s11_non_dlr_equivalent_correction:ShiftBound', ...
                'Phase-shift override on branch %d exceeds +/-30 degrees.', br);
        end
        mpc.branch(br, SHIFT) = value;
    end
end
end

function rows = branch_change_table(before, after, map, idx)
define_constants;
rows = table(idx, map.reduced_from_bus(idx), map.reduced_to_bus(idx), ...
    map.branch_classification(idx), before(idx, BR_R), after(idx, BR_R), ...
    before(idx, BR_X), after(idx, BR_X), before(idx, BR_B), ...
    after(idx, BR_B), before(idx, TAP), after(idx, TAP), ...
    before(idx, SHIFT), after(idx, SHIFT), ...
    'VariableNames', {'branch_index','from_bus','to_bus', ...
    'branch_classification','r_before_pu','r_after_pu','x_before_pu', ...
    'x_after_pu','b_before_pu','b_after_pu','tap_before', ...
    'tap_after','shift_before_deg','shift_after_deg'});
end

function rows = bus_change_table(before, after, idx)
define_constants;
rows = table(after(idx, BUS_I), before(idx, GS), after(idx, GS), ...
    before(idx, BS), after(idx, BS), ...
    'VariableNames', {'bus_id','gs_before_mw','gs_after_mw', ...
    'bs_before_mvar','bs_after_mvar'});
end
