function [mpc, report] = repair_generator_limit_violations(mpc, options)
%REPAIR_GENERATOR_LIMIT_VIOLATIONS Clip selected/unprotected PG values to limits.
%   Run balance_scenario_dispatch afterward to restore total power balance.

if nargin < 2, options=struct(); end
if ~isfield(options,'protected_gen_idx'), options.protected_gen_idx=[]; end
if ~isfield(options,'repair_gen_idx'), options.repair_gen_idx=[]; end
PG=2; GEN_STATUS=8; PMAX=9; PMIN=10;
online=find(mpc.gen(:,GEN_STATUS)>0);
if isempty(options.repair_gen_idx), idx=online; else, idx=intersect(online,options.repair_gen_idx(:)); end
idx=setdiff(idx,options.protected_gen_idx(:));
before=mpc.gen(idx,PG);
after=min(max(before,mpc.gen(idx,PMIN)),mpc.gen(idx,PMAX));
mpc.gen(idx,PG)=after;
changed=abs(after-before)>1e-9;
report=struct('generator_indices',idx(changed)','before_mw',before(changed)', ...
    'after_mw',after(changed)','net_generation_change_mw',sum(after-before));
mpc.userdata.ny_lite.generator_limit_repair_report=report;
end
