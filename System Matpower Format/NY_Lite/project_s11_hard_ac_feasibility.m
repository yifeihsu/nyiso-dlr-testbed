function projection = project_s11_hard_ac_feasibility(mpc, options, trusted_branch_mask)
%PROJECT_S11_HARD_AC_FEASIBILITY Project an S11 case onto hard AC limits.
%   The projection minimizes normalized squared PG movement. It introduces
%   no restoration, voltage, Q, or branch slack. Generator P/Q bounds, bus
%   voltage bounds, and explicitly trusted RATE_A limits remain hard.

if nargin < 1 || isempty(mpc)
    error('project_s11_hard_ac_feasibility:MissingCase', ...
        'A composed S11 MATPOWER case is required.');
end
if nargin < 2, options = struct(); end
if nargin < 3 || isempty(trusted_branch_mask)
    trusted_branch_mask = false(size(mpc.branch, 1), 1);
end
if ~isfield(options, 'opf_solver'), options.opf_solver = "IPOPT"; end
if ~isfield(options, 'max_iterations'), options.max_iterations = 1000; end
if ~isfield(options, 'target_pg'), options.target_pg = mpc.gen(:, 2); end
validateattributes(trusted_branch_mask, {'logical','numeric'}, ...
    {'vector','numel',size(mpc.branch, 1)});
validateattributes(options.max_iterations, {'numeric'}, ...
    {'scalar','integer','positive'});

define_constants;
projection = struct('attempted', true, 'success', false, ...
    'reason', "ACOPF did not run", 'result', struct(), ...
    'input_case', mpc, 'total_absolute_pg_movement_mw', Inf, ...
    'maximum_pg_movement_mw', Inf);
target_pg = double(options.target_pg(:));
if numel(target_pg) ~= size(mpc.gen, 1) || any(~isfinite(target_pg))
    error('project_s11_hard_ac_feasibility:TargetPG', ...
        'target_pg must contain one finite value per generator row.');
end

opf_case = mpc;
untrusted = ~logical(trusted_branch_mask(:));
opf_case.branch(untrusted, [RATE_A RATE_B RATE_C]) = 0;
opf_case.gencost = zeros(size(opf_case.gen, 1), 7);
for g = 1:size(opf_case.gen, 1)
    span = max(100, opf_case.gen(g, PMAX)-opf_case.gen(g, PMIN));
    c2 = 1/span^2;
    opf_case.gencost(g, :) = ...
        [2 0 0 3 c2 -2*c2*target_pg(g) c2*target_pg(g)^2];
end

try
    opfopt = mpoption('verbose', 0, 'out.all', 0, 'opf.ac.solver', ...
        char(string(options.opf_solver)), 'opf.flow_lim', 'S', ...
        'opf.violation', 1e-6, 'opf.use_vg', 0, ...
        'opf.ignore_angle_lim', 0, 'opf.start', 2);
    if upper(string(options.opf_solver)) == "IPOPT"
        opfopt.ipopt.opts = struct('max_iter', options.max_iterations, ...
            'tol', 1e-8, 'acceptable_tol', 1e-6);
    end
    result = runopf(opf_case, opfopt);
catch err
    projection.reason = "ACOPF exception: " + string(err.message);
    return;
end
projection.result = result;
projection.success = isfield(result, 'success') && logical(result.success);
if ~projection.success
    projection.reason = "Hard ACOPF returned success=0";
    return;
end

projected = mpc;
projected.bus(:, [VM VA]) = result.bus(:, [VM VA]);
projected.gen(:, [PG QG VG]) = result.gen(:, [PG QG VG]);
movement = result.gen(:, PG)-target_pg;
projection.input_case = projected;
projection.total_absolute_pg_movement_mw = sum(abs(movement));
projection.maximum_pg_movement_mw = max(abs(movement));
projection.reason = "Hard ACOPF feasible without restoration slacks";
end
