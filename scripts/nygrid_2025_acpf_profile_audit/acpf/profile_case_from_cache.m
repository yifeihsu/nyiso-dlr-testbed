function m=profile_case_from_cache(cache,h)
% Numerically reproduce npcc_nygrid_2025_ac(h) without repeated file hashing.
assert(isscalar(h)&&h==fix(h)&&h>=1&&h<=8760&&cache.qualified(h));
s=cache.state_index(h);m=cache.templates{s};ng=size(m.gen,1);
m.bus(1:140,3)=cache.dispatch.bus_pd(h,:)';m.bus(1:140,4)=cache.dispatch.bus_qd(h,:)';
m.gen(:,2)=cache.western.gen_pg(h,:)';
m.gen(:,9)=cache.bounds.gen_pmax(h,:)';m.gen(:,10)=cache.bounds.gen_pmin(h,:)';
m.gen(cache.external,9:10)=repmat(m.gen(cache.external,2),1,2);
m.gen(:,8)=m.gen(:,9)>0|m.gen(:,10)<0;
m.bus(:,2)=1;m.bus(ismember(m.bus(:,1),m.gen(m.gen(:,8)>0,1)),2)=2;
ref=double(cache.dispatch.reference_bus(h));m.bus(m.bus(:,1)==ref,2)=3;
assert(any(m.gen(:,1)==ref&m.gen(:,8)>0));
p_cap=max(abs(m.gen(:,9:10)),[],2);cap=p_cap;cap(cache.external)=cache.external_capacity;
qcap=cap*tan(acos(.95));qcap(cache.external)=sqrt(max(0,(cap(cache.external)/.95).^2-m.gen(cache.external,2).^2));
qcap(m.gen(:,8)==0)=0;m.gen(:,3)=0;m.gen(:,4)=qcap;m.gen(:,5)=-qcap;
m.gen(:,6)=m.bus(cache.generator_bus_index{s},8);m.gen(:,7)=max(cap/.95,1);
wp=1./max(p_cap,1);wq=.01./max(qcap,1);p=m.gen(:,2);
m.gencost=[2*ones(ng,1),zeros(ng,2),3*ones(ng,1),wp,-2*wp.*p,wp.*p.^2; ...
    2*ones(ng,1),zeros(ng,2),3*ones(ng,1),wq,zeros(ng,2)];
dc=[cache.dispatch.dc_pf(h,:)';cache.western.P34_control_targets_model_mw(h,:)'];
m.dcline(:,4:5)=repmat(dc,1,2);m.dcline(:,10:11)=repmat(dc,1,2);m.dcline(:,6:7)=0;
if cache.dover.post_full_service(h)
    phase=cache.dover.controls.bounded_x_nominal.bank_shift_model_deg(h,:)';
    assert(all(isfinite(phase))&&all(abs(phase)<=40*cache.dover.gamma+1e-8));
    m.branch(411:412,10)=phase;
end
% Static provenance belongs to the cached topology; no stale hourly DC
% interface operators or simulated-flow metadata are exposed as current.
if isfield(m.userdata,'source_dc'),m.userdata=rmfield(m.userdata,'source_dc');end
m.userdata.profile_cache=struct('template_hour',cache.template_hours(s),'requested_hour',h, ...
    'physics_arrays_validated_against_public_loader',true,'internal_interface_observations_read',false);
u=m.userdata.ac_system;u.hour_index=h;u.timestamp_utc=string(cache.dispatch.timestamp_utc{h});
u.generator_p_reference=p;u.generator_capability_reference=cap;u.generator_q_cap=qcap;
u.generator_assumed_s_cap=cap/.95;u.p_objective_weight=wp;u.q_objective_weight=wq;
m.userdata.ac_system=u;
assert(all(isfinite(m.bus),'all')&&all(isfinite(m.gen),'all')&&all(isfinite(m.dcline),'all'));
end
