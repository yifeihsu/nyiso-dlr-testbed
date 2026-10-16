function [m,meta]=ablation_load(h,scenario)
% Reconstruct every PG/capability-dependent field after a source intervention.
assert(any(strcmp(scenario,{'B','G','P','GP'})));
persistent old_profiles
if isempty(old_profiles)
    root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
    folder=fullfile(root,'output','nygrid_2025_moses_repair','annual','baseline_bundle','model');
    a=load(fullfile(folder,'profiles_h0001_4380.mat'),'profiles');b=load(fullfile(folder,'profiles_h4381_8760.mat'),'profiles');
    names=fieldnames(a.profiles);old_profiles=struct();
    for k=1:numel(names),name=names{k};old_profiles.(name)=[a.profiles.(name);b.profiles.(name)];end
end
[data,~]=nylatest_data();m=load_nygrid_latest(h);ng=size(m.gen,1);assert(ng==1466);
external=logical(data.external.generator_mask(:));boundary=double(data.boundary_injections.generator_rows(:));assert(isequal(boundary,1466));
old_ng=size(old_profiles.generator_PG_MW,2);assert(old_ng==1464);
useG=any(strcmp(scenario,{'G','GP'}));useP=any(strcmp(scenario,{'P','GP'}));
pg=data.profiles.generator_PG_MW(h,:)';hi=data.profiles.generator_Pmax_MW(h,:)';lo=data.profiles.generator_Pmin_MW(h,:)';
if ~useG
    native=find(~external&(1:ng)'<=old_ng);
    pg(native)=old_profiles.generator_PG_MW(h,native)';
    hi(native)=old_profiles.generator_Pmax_MW(h,native)';lo(native)=old_profiles.generator_Pmin_MW(h,native)';
    pg(1465)=0;hi(1465)=0;lo(1465)=0;
end
if ~useP
    original_external=find(external&(1:ng)'<=old_ng);
    pg(original_external)=old_profiles.generator_PG_MW(h,original_external)';
    hi(original_external)=old_profiles.generator_Pmax_MW(h,original_external)';lo(original_external)=old_profiles.generator_Pmin_MW(h,original_external)';
    pg(boundary)=0;hi(boundary)=0;lo(boundary)=0;
end
hi(external)=pg(external);lo(external)=pg(external);
m.gen(:,2)=pg;m.gen(:,9)=hi;m.gen(:,10)=lo;m.gen(:,8)=hi>0|lo<0;
control=m.gen(:,8)>0;control(boundary)=false;
m.bus(:,2)=1;m.bus(ismember(m.bus(:,1),m.gen(control,1)),2)=2;
ref=double(data.axis.reference_bus(h));m.bus(m.bus(:,1)==ref,2)=3;
p_cap=max(abs([hi lo]),[],2);cap=p_cap;cap(external)=data.external.capability_proxy_MW;
cap(boundary)=abs(pg(boundary));qcap=cap*tan(acos(.95));
qcap(external)=sqrt(max(0,(cap(external)/.95).^2-pg(external).^2));
qcap(m.gen(:,8)==0)=0;qcap(boundary)=0;
m.gen(:,3)=0;m.gen(:,4)=qcap;m.gen(:,5)=-qcap;
s=double(data.axis.state_index(h));m.gen(:,6)=m.bus(data.generator_bus_rows{s},8);m.gen(:,7)=max(cap/.95,1);
wp=1./max(p_cap,1);wq=.01./max(qcap,1);
m.gencost=[2*ones(ng,1),zeros(ng,2),3*ones(ng,1),wp,-2*wp.*pg,wp.*pg.^2; ...
    2*ones(ng,1),zeros(ng,2),3*ones(ng,1),wq,zeros(ng,2)];
u=m.userdata.ac_system;u.generator_p_reference=pg;u.generator_capability_reference=cap;
u.generator_q_cap=qcap;u.generator_assumed_s_cap=cap/.95;u.generator_assumed_s_cap(boundary)=abs(pg(boundary));
u.p_objective_weight=wp;u.q_objective_weight=wq;m.userdata.ac_system=u;
m.userdata.latest_runtime.only_current_model=false;
m.userdata.latest_runtime.diagnostic_factorial_scenario=scenario;
meta=struct('scenario',scenario,'G',useG,'P',useP,'unit21_PG',pg(1465),'PV20_PG',pg(boundary), ...
    'native_total_PG',sum(pg(~external)),'external_region_total_PG',zeros(3,1));
pol=nylatest_prepare_policy(m);
for g=12:14,meta.external_region_total_PG(g-11)=sum(pg(pol.external_gen_group==g));end
assert(all(isfinite(m.gen),'all')&&all(pg>=lo-1e-8&pg<=hi+1e-8));
assert(~any(ismember(boundary,pol.native))&&pol.generator_share(boundary)==0);
if ~useG,assert(all(m.gen(1465,[2 3 4 5 8 9 10])==0));end
if ~useP,assert(all(m.gen(boundary,[2 3 4 5 8 9 10])==0));end
end
