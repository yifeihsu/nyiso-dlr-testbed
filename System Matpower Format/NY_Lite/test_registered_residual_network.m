function out=test_registered_residual_network
m=loadcase('case9');m.bus(:,5:6)=0;
r=table(2,"registered_residual_equivalent",0,0.1,0.01,0.3,0,0.5, ...
    'VariableNames',{'branch_row','classification','r_min','r_max','x_min','x_max','b_min','b_max'});
t=m;t.branch(2,3:5)=m.branch(2,3:5).*[1.1 1.1 0.9];
ti=ext2int(t);target=struct('bus_ids',t.bus(:,1),'Y',makeYbus(ti), ...
    'source','synthetic_case9_known_residual_test','base_mva',t.baseMVA, ...
    'base_kv',t.bus(:,10),'vintage','synthetic_fixture');
opts=struct('regularization',1e-7,'candidate_vintage','synthetic_fixture');
a=fit_registered_residual_network(m,r,target,opts);
assert(a.accepted && a.relative_port_error<a.initial_relative_port_error/10);
bad=r;bad.classification="physical_circuit";rejected=false;
try,fit_registered_residual_network(m,bad,target,opts);catch e,rejected=strcmp(e.identifier,'fit_registered_residual_network:PhysicalRow');end
assert(rejected);
target.Y=-target.Y;
b=fit_registered_residual_network(m,r,target,opts);
assert(~b.accepted && isequaln(b.candidate,m));
out=struct('pass',true,'test_count',3,'fit',a,'nonpassive_rejected',~b.accepted);
end
