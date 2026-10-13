function p=nylatest_prepare_policy(m)
% Current frozen ownership/membership with the original hourly policy algebra.
% No bus registry, generator-share CSV or older base-case file is required.
p=m.userdata.latest_runtime.loss_static;
external_rows=p.finite_external_generator_rows;Pmin=p.finite_external_Pmin_MW;Pmax=p.finite_external_Pmax_MW;
p=rmfield(p,{'finite_external_generator_rows','finite_external_Pmin_MW','finite_external_Pmax_MW'});
assert(all(abs(sum(p.loss_ownership,1)-1)<1e-14));
assert(all(m.bus(:,5)==0),'acLoss:Conductance','Add explicit ownership before modeling nonzero GS.');
assert(all(m.dcline(:,16:17)==0,'all'),'acLoss:DCLoss','Current policy requires zero modeled DC losses.');
p.gross_PD=m.bus(:,3);p.gross_QD=m.bus(:,4);p.baseline_PG=m.gen(:,2);
p.group_gross_PD=accumarray(max(1,p.bus_group),m.bus(:,3),[14 1]);
assert(all(m.bus(p.bus_group==0,3:4)==0,'all'),'acLoss:InteriorLoad','Unmapped numerical interior must stay zero injection.');
p.Pmax=m.gen(:,9);p.Pmin=m.gen(:,10);p.Pmax(external_rows)=Pmax;p.Pmin(external_rows)=Pmin;
assert(all(p.baseline_PG>=p.Pmin-1e-8&p.baseline_PG<=p.Pmax+1e-8));
for g=12:14
    use=find(p.external_gen_group==g);assert(abs(sum(p.generator_share(use))-1)<1e-12);
    p.target_NY_import(g-11,1)=sum(p.baseline_PG(p.external_gen_group==g))-sum(p.gross_PD(p.bus_group==g));
end
ref=m.bus(m.bus(:,2)==3,1);assert(isscalar(ref));p.reference=find(m.gen(:,1)==ref&m.gen(:,8)>0,1);
p.reference_bus=ref;p.S_cap=m.userdata.ac_system.generator_assumed_s_cap;
end
