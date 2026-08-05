function [mpc, report] = balance_scenario_dispatch(mpc, options)
%BALANCE_SCENARIO_DISPATCH Adjust only an explicit balancing generator pool.

if nargin < 2, options=struct(); end
if ~isfield(options,'balance_gen_idx'), options.balance_gen_idx=[]; end
if ~isfield(options,'balance_bus_ids'), options.balance_bus_ids=[]; end
if ~isfield(options,'participation_factors'), options.participation_factors=[]; end
if ~isfield(options,'expected_losses_mw'), options.expected_losses_mw=0; end
if ~isfield(options,'target_system_net_export_mw'), options.target_system_net_export_mw=0; end
if ~isfield(options,'allow_existing_limit_violations'), options.allow_existing_limit_violations=false; end

PG=2; GEN_STATUS=8; PMAX=9; PMIN=10;
idx=unique(options.balance_gen_idx(:));
if ~isempty(options.balance_bus_ids)
    idx=unique([idx; find(ismember(mpc.gen(:,1),options.balance_bus_ids(:)) & mpc.gen(:,GEN_STATUS)>0)]);
end
if isempty(idx), error('balance_scenario_dispatch:PoolRequired','Specify balance_gen_idx or balance_bus_ids.'); end
online=find(mpc.gen(:,GEN_STATUS)>0);
viol=find(mpc.gen(online,PG)>mpc.gen(online,PMAX)+1e-8 | mpc.gen(online,PG)<mpc.gen(online,PMIN)-1e-8);
viol_idx=online(viol);
if ~options.allow_existing_limit_violations && any(~ismember(viol_idx,idx))
    error('balance_scenario_dispatch:ExistingViolations', ...
        'Generators outside the balancing pool violate PMIN/PMAX. Repair them first.');
end

pool_before = mpc.gen(idx, PG);
mpc.gen(idx, PG) = min(max(pool_before, mpc.gen(idx, PMIN)), mpc.gen(idx, PMAX));
pool_clip_mw = sum(mpc.gen(idx, PG) - pool_before);

target=sum(mpc.bus(:,3))+options.expected_losses_mw+options.target_system_net_export_mw;
current=sum(mpc.gen(online,PG)); delta=target-current;
[mpc.gen,allocation,remaining]=ny_lite_allocate_pg_delta( ...
    mpc.gen,idx,delta,options.participation_factors);
if abs(remaining)>1e-6
    error('balance_scenario_dispatch:InsufficientRoom', ...
        'Balancing pool cannot absorb %.6g MW of the required change.',remaining);
end
report=struct('target_generation_mw',target,'initial_generation_mw',current, ...
    'requested_delta_mw',delta,'applied_delta_mw',sum(allocation), ...
    'pool_limit_clip_mw',pool_clip_mw, ...
    'balance_gen_idx',idx(:)','expected_losses_mw',options.expected_losses_mw, ...
    'target_system_net_export_mw',options.target_system_net_export_mw);
mpc.userdata.ny_lite.dispatch_balance_report=report;
end
