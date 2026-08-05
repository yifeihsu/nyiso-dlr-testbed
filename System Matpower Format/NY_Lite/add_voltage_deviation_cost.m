function mpc = add_voltage_deviation_cost(mpc, rho, vref)
%ADD_VOLTAGE_DEVIATION_COST Add quadratic penalty rho * sum((Vm-vref)^2).

if nargin < 2 || isempty(rho), rho = 1e4; end
if nargin < 3 || isempty(vref), vref = 1.0; end
if ~isscalar(rho) || ~isfinite(rho) || rho < 0
    error('add_voltage_deviation_cost:BadRho', 'rho must be a nonnegative scalar.');
end
if ~isscalar(vref) || ~isfinite(vref)
    error('add_voltage_deviation_cost:BadVref', 'vref must be a finite scalar.');
end
if rho == 0, return; end

args = struct('rho', rho, 'vref', vref);
mpc = add_userfcn(mpc, 'formulation', @voltage_deviation_formulation, args, true);
if ~isfield(mpc, 'userdata'), mpc.userdata = struct(); end
if ~isfield(mpc.userdata, 'ny_lite'), mpc.userdata.ny_lite = struct(); end
mpc.userdata.ny_lite.voltage_deviation_cost = args;
end

function om = voltage_deviation_formulation(om, mpopt, args) %#ok<INUSD>
vv = om.get_idx();
if ~isfield(vv.N, 'Vm') || vv.N.Vm == 0
    return;
end
n = vv.N.Vm;
rho = args.rho;
vref = args.vref;
Q = 2 * rho * ones(n, 1);
C = -2 * rho * vref * ones(n, 1);
K = rho * n * vref^2;
om.add_quad_cost('ny_lite_voltage_deviation', Q, C, K, {'Vm'});
end
