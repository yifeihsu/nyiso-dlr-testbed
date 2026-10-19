function [m,a]=nylatest_apply_budget(base,p,budget)
% Convert NY gross boundary demand to served load; balance external losses.
assert(numel(budget)==14&&all(isfinite(budget))&&all(budget>=0));m=base;
ratios=ones(11,1);allocation=zeros(size(m.gen,1),1);
for g=1:11
    total=p.group_gross_PD(g);assert(total>0,'acLoss:NoZonalLoad','NY zone has no positive load pool.');
    assert(budget(g)<total,'acLoss:NegativeServedDemand','Allocated NY losses exhaust a zonal gross-load target.');
    ratios(g)=1-budget(g)/total;use=p.bus_group==g;
    assert(all(p.gross_PD(use)>=0));m.bus(use,3)=p.gross_PD(use)*ratios(g);m.bus(use,4)=p.gross_QD(use)*ratios(g);
end
for g=12:14
    use=find(p.external_gen_group==g);room=p.Pmax(use)-p.baseline_PG(use);
    assert(sum(room)>=budget(g)-1e-8,'acLoss:ExternalCapacity','Regional losses exceed finite original external capability.');
    x=zeros(size(use));remaining=budget(g);w=p.generator_share(use);
    for iteration=1:numel(use)+1
        eligible=room-x>1e-10&w>0;if remaining<1e-10,break;end
        assert(any(eligible));proposal=remaining*w(eligible)/sum(w(eligible));step=min(proposal,room(eligible)-x(eligible));
        x(eligible)=x(eligible)+step;remaining=budget(g)-sum(x);
    end
    assert(abs(sum(x)-budget(g))<1e-7);allocation(use)=x;
end
m.gen(:,2)=p.baseline_PG+allocation;m.gen(:,9)=p.Pmax;m.gen(:,10)=p.Pmin;
assert(all(m.gen(:,2)<=m.gen(:,9)+1e-8&m.gen(:,2)>=m.gen(:,10)-1e-8));
external=m.userdata.ac_system.external_generator_mask;
qcap=m.userdata.ac_system.generator_q_cap;
qcap(external)=sqrt(max(0,p.S_cap(external).^2-m.gen(external,2).^2));
m.gen(external,4)=qcap(external);m.gen(external,5)=-qcap(external);
m.userdata.ac_system.generator_q_cap=qcap;
m.userdata.ac_system.generator_p_reference=m.gen(:,2);
m.userdata.ac_loss_revision.loss_policy=p.policy;
a=struct('applied_budget_MW',budget,'NY_served_to_gross_ratio',ratios,'allocated_generator_increment_MW',allocation, ...
    'native_and_HQ_PG_unchanged',isequal(m.gen(p.native,2),p.baseline_PG(p.native))&&m.gen(p.HQ,2)==p.baseline_PG(p.HQ), ...
    'external_delivered_PD_QD_unchanged',isequal(m.bus(p.bus_group>11,3:4),base.bus(p.bus_group>11,3:4)));
end
