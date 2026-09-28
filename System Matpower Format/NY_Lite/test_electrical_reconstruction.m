function out=test_electrical_reconstruction
% Feasible reconstruction, fixed-input PF, explicit aggregate metering and
% impossible bounded dispatch exercise separate success and failure paths.
define_constants;
m=loadcase('case9');m.bus(:,VMIN)=0.95;m.bus(:,VMAX)=1.05;
o=reconstruct_ac_operating_point(m,struct(),struct('verbose',true));
assert(o.success && o.network_parameters_frozen && abs(o.accounting_error_mw)<1e-3);
Af=sparse(1,size(m.branch,1));At=Af;Af(1,[1 4])=1;
c=struct('operator_from',Af,'operator_to',At, ...
    'target_mw',sum(o.result.branch([1 4],PF)),'tolerance_mw',0.1, ...
    'Pg_prior_mw',o.result.gen(:,PG),'Pg_sigma_mw',ones(3,1)*10);
p=reconstruct_ac_operating_point(o.result,c);
assert(p.success && abs(p.operator_mw-c.target_mw)<=0.101);
c.Pg_prior_mw=c.Pg_prior_mw';c.Pg_sigma_mw=c.Pg_sigma_mw';
row_inputs=reconstruct_ac_operating_point(o.result,c);
assert(row_inputs.success);
isolated=m;isolated.bus(end+1,:)=isolated.bus(1,:);
isolated.bus(end,[BUS_I BUS_TYPE PD QD])=[99 4 100 20];rejected=false;
try,reconstruct_ac_operating_point(isolated);catch e
    rejected=strcmp(e.identifier,'reconstruct_ac_operating_point:ExcludedInjection');
end
assert(rejected,'Excluded load must never disappear from power accounting.');
m.gen(:,PMAX)=1;m.gen(:,PMIN)=0;
bad=reconstruct_ac_operating_point(m,struct(),struct('max_iterations',25));
assert(~bad.success);
out=struct('pass',true,'test_count',5,'feasible',o,'aggregate',p, ...
    'infeasible_rejected',~bad.success);
end
