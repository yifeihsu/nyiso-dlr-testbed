function [pf,a,detail,pf_input,pf_options] = replay_acpf_solution(m,opf)
% Replay a solved loss-balanced ACOPF point with Newton AC power flow.
% Q limiting is off during the solve, but every real/transfer Q bound is audited.
% Co-located generator Q may redistribute without changing bus injections.
assert(opf.success,'AC:UnsolvedReplay','Replay requires a successful ACOPF point.');
pf_input=m;pf_input.bus(:,8:9)=opf.bus(:,8:9);pf_input.gen(:,2:3)=opf.gen(:,2:3);
[ok,gb]=ismember(m.gen(:,1),m.bus(:,1));assert(all(ok));
pf_input.gen(:,6)=opf.bus(gb,8);
[ok,f]=ismember(m.dcline(:,1),m.bus(:,1));assert(all(ok));
[ok,t]=ismember(m.dcline(:,2),m.bus(:,1));assert(all(ok));
pf_input.dcline(:,8)=opf.bus(f,8);pf_input.dcline(:,9)=opf.bus(t,8);
pf_input.dcline(:,6:7)=opf.dcline(:,6:7);
% A small deterministic start perturbation verifies a fresh Newton solve.
% Generator and converter voltage setpoints remain the OPF setpoints.
sequence=(1:size(m.bus,1))';pq=m.bus(:,2)==1;nonref=m.bus(:,2)~=3;
pf_input.bus(pq,8)=pf_input.bus(pq,8).*(1+1e-4*sin(sequence(pq)));
pf_input.bus(nonref,9)=pf_input.bus(nonref,9)+1e-3*sin(sequence(nonref));
pf_options=mpoption('model','AC','verbose',0,'out.all',0,'pf.alg','NR', ...
    'pf.nr.max_it',25,'pf.tol',1e-10,'pf.enforce_q_lims',0,'exp.use_legacy_core',1);
[pf,ok]=runpf(pf_input,pf_options);
[a,detail]=audit_ac_solution(pf_input,pf);
a.replayed_successful_ACOPF_point=true;a.PF_Q_limit_enforcement=0;
a.PF_backend='MATPOWER_legacy_NR';a.initial_PQ_VM_relative_perturbation_amplitude=1e-4;
a.PF_iterations=pf.iterations;
a.initial_nonreference_angle_perturbation_amplitude_deg=1e-3;
a.all_Q_limits_checked_after_solve=true;a.lossless_DC_dispatch_used_as_PF_state=false;
a.max_VM_change_from_OPF_pu=max(abs(pf.bus(:,8)-opf.bus(:,8)));
a.max_VA_change_from_OPF_deg=max(abs(pf.bus(:,9)-opf.bus(:,9)));
a.max_PG_change_from_OPF_mw=max(abs(pf.gen(:,2)-opf.gen(:,2)));
a.max_QG_redistribution_from_OPF_mvar=max(abs(pf.gen(:,3)-opf.gen(:,3)));
a.maximum_branch_complex_power_change_from_OPF_mva=max([ ...
    abs(complex(pf.branch(:,14)-opf.branch(:,14),pf.branch(:,15)-opf.branch(:,15))); ...
    abs(complex(pf.branch(:,16)-opf.branch(:,16),pf.branch(:,17)-opf.branch(:,17)))]);
a.passed=a.passed&&ok&&a.max_VM_change_from_OPF_pu<1e-7 ...
    &&a.max_VA_change_from_OPF_deg<1e-5&&a.max_PG_change_from_OPF_mw<1e-4;
end
