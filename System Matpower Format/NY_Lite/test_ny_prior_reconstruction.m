function t=test_ny_prior_reconstruction
%TEST_NY_PRIOR_RECONSTRUCTION Native/slack bounds and replay, no interface fit.
define_constants;m=loadcase('case9');m.bus(:,VMIN)=0.95;m.bus(:,VMAX)=1.05;
r=reconstruct_ac_operating_point(m,struct(),struct('solver','matpower_prior'));
a=audit_ny_ac_reference(r.fixed_input_pf);
assert(r.success&&a.passed&&r.network_parameters_frozen);
assert(all(r.fixed_input_pf.gen(:,PG)<=m.gen(:,PMAX)+1e-3)&& ...
    all(r.fixed_input_pf.gen(:,QG)>=m.gen(:,QMIN)-1e-3));
impossible=m;impossible.gen(:,PMAX)=1;impossible.gen(:,PMIN)=0;
r2=reconstruct_ac_operating_point(impossible,struct(),struct('solver','matpower_prior'));
assert(~r2.success,'Reference generator must not silently cover impossible load.');
rejected=false;
try
    reconstruct_ac_operating_point(m,struct('operator_from',sparse(1,size(m.branch,1))),struct('solver','matpower_prior'));
catch e,rejected=strcmp(e.identifier,'reconstruct_ac_operating_point:PriorOnly');end
assert(rejected);
t=table(["bounded_prior_only_reconstructs_and_replays";"native_and_reference_limits_hold"; ...
    "impossible_native_capacity_fails";"interface_fit_rejected_by_prior_only_backend"],true(4,1), ...
    'VariableNames',{'test','passed'});
end
