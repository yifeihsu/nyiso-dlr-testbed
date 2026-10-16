function [m,info]=load_nygrid_latest(hour_index)
%LOAD_NYGRID_LATEST Construct the current detailed case from frozen profiles.
% All8760 UTC rows are retained in the bundle; only8651 source-qualified
% hours can construct a case. Already includes the released E-G equivalent.
if nargin<1||isempty(hour_index),hour_index=8508;end
[data,receipt]=nylatest_data();h=hour_index;
assert(isnumeric(h)&&isscalar(h)&&isfinite(h)&&h==fix(h)&&h>=1&&h<=8760,'nylatest:Hour','Use an integer hour index from1 to8760.');
assert(data.axis.source_qualified(h),'nylatest:UnqualifiedHour','This hour is outside the frozen source-qualified cohort.');
s=double(data.axis.state_index(h));m=data.templates{s};ng=size(m.gen,1);external=data.external.generator_mask;
boundary=double(data.boundary_injections.generator_rows(:));
m.bus(1:140,3)=data.profiles.bus_PD_MW(h,:)';m.bus(1:140,4)=data.profiles.bus_QD_MVAr(h,:)';
m.gen(:,2)=data.profiles.generator_PG_MW(h,:)';
m.gen(:,9)=data.profiles.generator_Pmax_MW(h,:)';m.gen(:,10)=data.profiles.generator_Pmin_MW(h,:)';
m.gen(external,9:10)=repmat(m.gen(external,2),1,2);
m.gen(:,8)=m.gen(:,9)>0|m.gen(:,10)<0;
voltage_control=m.gen(:,8)>0;voltage_control(boundary)=false;
m.bus(:,2)=1;m.bus(ismember(m.bus(:,1),m.gen(voltage_control,1)),2)=2;
ref=double(data.axis.reference_bus(h));m.bus(m.bus(:,1)==ref,2)=3;
assert(any(m.gen(:,1)==ref&m.gen(:,8)>0));
p_cap=max(abs(m.gen(:,9:10)),[],2);cap=p_cap;cap(external)=data.external.capability_proxy_MW;
cap(boundary)=abs(m.gen(boundary,2));
qcap=cap*tan(acos(.95));qcap(external)=sqrt(max(0,(cap(external)/.95).^2-m.gen(external,2).^2));
qcap(m.gen(:,8)==0)=0;qcap(boundary)=0;m.gen(:,3)=0;m.gen(:,4)=qcap;m.gen(:,5)=-qcap;
m.gen(:,6)=m.bus(data.generator_bus_rows{s},8);m.gen(:,7)=max(cap/.95,1);
wp=1./max(p_cap,1);wq=.01./max(qcap,1);p=m.gen(:,2);
m.gencost=[2*ones(ng,1),zeros(ng,2),3*ones(ng,1),wp,-2*wp.*p,wp.*p.^2; ...
    2*ones(ng,1),zeros(ng,2),3*ones(ng,1),wq,zeros(ng,2)];
dc=data.profiles.fixed_transfer_PF_MW(h,:)';
m.dcline(:,4:5)=repmat(dc,1,2);m.dcline(:,10:11)=repmat(dc,1,2);m.dcline(:,6:7)=0;
if data.axis.post_dover_full_service(h)
    phase=data.profiles.dover_bank_phase_shift_deg(h,:)';
    assert(all(isfinite(phase))&&all(abs(phase)<=40*data.scale_factor_gamma+1e-8));m.branch(411:412,10)=phase;
end
u=m.userdata.ac_system;u.hour_index=h;u.timestamp_utc=string(data.axis.timestamp_utc(h));
u.generator_p_reference=p;u.generator_capability_reference=cap;u.generator_q_cap=qcap;
u.generator_assumed_s_cap=cap/.95;u.generator_assumed_s_cap(boundary)=abs(p(boundary));
u.boundary_injection_rows=boundary;u.boundary_injections_are_fixed_PQ=true;
u.p_objective_weight=wp;u.q_objective_weight=wq;m.userdata.ac_system=u;
m.userdata.latest_runtime=struct('schema_version',1,'state_index',s,'state_name',char(data.axis.state_names(s)), ...
    'hour_index',h,'timestamp_utc',char(data.axis.timestamp_utc(h)),'source_qualified',true, ...
    'retained_bus_ids',data.retained_bus_ids,'loss_static',data.loss_static{s}, ...
    'source_model_commit',data.source_model_commit,'model_sha256',receipt.model_file.sha256, ...
    'only_current_model',true,'historical_loader_chain_used',false,'OPF_supported',false);
% Recreate standard MATPOWER handles from the selected vendor; no serialized
% handles pointing at the authoring machine are carried in the bundle.
m=toggle_dcline(m,'on');if isfield(m.userfcn,'formulation'),m.userfcn=rmfield(m.userfcn,'formulation');end
assert(all(isfinite(m.bus),'all')&&all(isfinite(m.gen),'all')&&all(isfinite(m.dcline),'all'));
info=m.userdata.latest_runtime;info=rmfield(info,'loss_static');
end
