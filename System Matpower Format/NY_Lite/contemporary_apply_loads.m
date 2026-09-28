function [mpc, report] = contemporary_apply_loads(mpc, inputs, allocation, contract)
%CONTEMPORARY_APPLY_LOADS Apply actual public MW using explicit allocation.
% allocation: bus_id, zone, weight, q_over_p, source_uri. All Q/P values are
% assumptions, not contemporary observed reactive demand. Only PD/QD change.
if nargin < 4, contract = research_model_contract; end
if string(contract.mode) ~= "contemporary_2026" || string(contract.power_scale) ~= "actual_mw"
    error('contemporary_apply_loads:Contract', 'Requires contemporary actual-MW contract.');
end
validation = validate_research_inputs(inputs, contract);
if numel(unique(string(inputs.scenario_id))) ~= 1 || any(string(inputs.kind) ~= "load_p")
    error('contemporary_apply_loads:Scenario', 'Supply one complete load-only operating point.');
end
names = ["bus_id","zone","weight","q_over_p","source_uri"];
if ~istable(allocation) || isempty(allocation) || ~all(ismember(names,string(allocation.Properties.VariableNames)))
    error('contemporary_apply_loads:Allocation', 'Missing allocation columns.');
end
ids = allocation.bus_id; weights = allocation.weight; ratio = allocation.q_over_p;
zones = string(allocation.zone);
[exists, idx] = ismember(ids, mpc.bus(:,1));
if ~isnumeric(ids) || any(~isfinite(ids)) || numel(unique(ids)) ~= numel(ids) || any(~exists) || ...
        any(~ismember(zones,string(('A':'K')'))) || ...
        ~isnumeric(weights) || any(~isfinite(weights) | weights < 0) || ...
        ~isnumeric(ratio) || any(~isfinite(ratio)) || ...
        any(ismissing(string(allocation.source_uri)) | strlength(strtrim(string(allocation.source_uri))) == 0)
    error('contemporary_apply_loads:Allocation', 'Invalid or duplicate bus allocation or missing provenance.');
end
% Protect against leaving a positive inherited NY load outside the allocation.
[known, ~] = nyiso_bus_zone_map;
ny = ismember(mpc.bus(:,1), [known.bus_id]);
if isfield(mpc,'userdata') && isfield(mpc.userdata,'nyiso_physical_zone')
    ny = ny | ismember(string(mpc.userdata.nyiso_physical_zone),string(('A':'K')'));
end
if any(ny & ~ismember(mpc.bus(:,1),ids) & abs(mpc.bus(:,3)) > 1e-9)
    error('contemporary_apply_loads:UnaccountedLoad', 'An inherited NY load is absent from the allocation.');
end
original_p = mpc.bus(:,3); original_q = mpc.bus(:,4);
target = zeros(11,1); applied = zeros(11,1); applied_q = zeros(11,1);
for z = 1:11
    zone = string(char('A'+z-1)); rows = zones == zone;
    if ~any(rows) || abs(sum(weights(rows))-1) > 1e-10
        error('contemporary_apply_loads:Weights', 'Zone %s weights must sum to one.',zone);
    end
    target(z) = inputs.value(string(inputs.entity_id) == zone);
    p = target(z)*weights(rows);
    [~,j] = max(weights(rows)); p(j) = p(j) + target(z)-sum(p);
    mpc.bus(idx(rows),3) = p;
    mpc.bus(idx(rows),4) = p.*ratio(rows);
    applied(z) = sum(mpc.bus(idx(rows),3)); applied_q(z) = sum(mpc.bus(idx(rows),4));
end
report = struct('validation',validation,'scenario_id',string(inputs.scenario_id(1)), ...
    'power_scale',"actual_mw",'normalization_factor',1, ...
    'original_ny_load_mw',sum(original_p(idx)), 'actual_ny_load_mw',sum(applied), ...
    'reactive_policy',"explicit_assumed_bus_q_over_p",'allocation',allocation, ...
    'zone_table',table(string(('A':'K')'),target,applied,applied_q, ...
       'VariableNames',{'zone','target_mw','applied_mw','applied_mvar'}), ...
    'source_observations',inputs,'original_pd',original_p,'original_qd',original_q, ...
    'release_ready',false);
if ~isfield(mpc,'userdata'), mpc.userdata = struct(); end
mpc.userdata.contemporary_loads = report;
end
