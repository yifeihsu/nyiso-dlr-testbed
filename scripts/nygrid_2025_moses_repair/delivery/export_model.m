function receipt=export_model()
% Compile the source-defined hydro allocation and northern boundary routing.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
out=fullfile(root,'output','nygrid_2025_moses_repair','model');
base=fullfile(root,'output','nygrid_2025_physical_repair','model');
repair=fullfile(root,'output','nygrid_2025_moses_repair');
runtime=fullfile(root,'scripts','nygrid_2025_moses_repair','delivery','runtime');addpath(runtime);
candidate_path=fullfile(repair,'candidate_receipt.json');candidate=jsondecode(fileread(candidate_path));assert(candidate.passed);
for k=1:numel(candidate.files)
    a=candidate.files(k);assert(strcmp(nylatest_file_sha256(fullfile(root,a.path)),a.sha256));
end
assert(~isfile(fullfile(out,'latest_model.mat')),'nymoses:PreserveModel','Use a new candidate version rather than overwrite a compiled model.');
prior=jsondecode(fileread(fullfile(base,'model_receipt.json')));
for k=1:numel(prior.model_files)
    a=prior.model_files(k);assert(strcmp(nylatest_file_sha256(fullfile(base,a.name)),a.sha256));
end
s=load(fullfile(base,'latest_model.mat'),'model');model=s.model;original=model;
g=load(fullfile(repair,'generation','generation_candidate.mat'));
b=load(fullfile(repair,'boundary','boundary_rerouting.mat'));
q=logical(model.axis.source_qualified(:));assert(nnz(q)==8651);
assert(isequal(logical(b.source_qualified(:)),q));
hy=double(g.hydro_rows_1based(:));st=double(g.stlawrence_rows_1based(:));pool=double(b.ISONE_pool_rows_1based(:));
assert(numel(st)==16&&ismember(1465,st)&&all(ismember(st,hy)));
assert(size(g.hydro_PG_public_MW,1)==8760&&size(g.hydro_PG_public_MW,2)==numel(hy));
gamma=model.scale_factor_gamma;
if ~isfolder(out),mkdir(out);end
parts=cell(2,1);file_records=repmat(struct('name','','bytes',0,'sha256',''),3,1);
for k=1:2
    item=original.profile_shards(k);loaded=load(fullfile(base,item.name),'profiles');profiles=loaded.profiles;
    ix=item.first_hour:item.last_hour;before=profiles;count=numel(ix);
    profiles.generator_PG_MW(:,1465:1466)=nan(count,2);
    profiles.generator_Pmin_MW(:,1465:1466)=nan(count,2);
    profiles.generator_Pmax_MW(:,1465:1466)=nan(count,2);
    profiles.generator_PG_MW(:,hy)=g.hydro_PG_public_MW(ix,:)*gamma;
    profiles.generator_Pmin_MW(:,st)=g.stlawrence_Pmin_public_MW(ix,:)*gamma;
    profiles.generator_Pmax_MW(:,st)=g.stlawrence_Pmax_public_MW(ix,:)*gamma;
    profiles.generator_PG_MW(:,pool)=b.ISONE_pool_PG_public_MW(ix,:)*gamma;
    pv=b.PV20_boundary_PG_public_MW(ix)*gamma;
    profiles.generator_PG_MW(:,1466)=pv;profiles.generator_Pmin_MW(:,1466)=pv;profiles.generator_Pmax_MW(:,1466)=pv;
    oldhy=hy(hy<=1464);good=q(ix);
    assert(max(abs(sum(profiles.generator_PG_MW(good,hy),2)-sum(before.generator_PG_MW(good,oldhy),2)))<1e-7);
    assert(max(abs(sum(profiles.generator_PG_MW(good,:),2)-sum(before.generator_PG_MW(good,:),2)))<1e-7);
    unchanged=setdiff(1:1464,[hy;pool]);assert(isequaln(profiles.generator_PG_MW(:,unchanged),before.generator_PG_MW(:,unchanged)));
    other=setdiff(1:1464,st);assert(isequaln(profiles.generator_Pmax_MW(:,other),before.generator_Pmax_MW(:,other)));
    assert(isequaln(profiles.bus_PD_MW,before.bus_PD_MW)&&isequaln(profiles.bus_QD_MVAr,before.bus_QD_MVAr));
    assert(isequaln(profiles.fixed_transfer_PF_MW,before.fixed_transfer_PF_MW)&&isequaln(profiles.dover_bank_phase_shift_deg,before.dover_bank_phase_shift_deg));
    assert(all(isfinite(profiles.generator_PG_MW(good,:)),'all'));
    parts{k}=profiles;path=fullfile(out,item.name);save(path,'profiles','-v7');fi=dir(path);
    file_records(k+1)=struct('name',item.name,'bytes',fi.bytes,'sha256',nylatest_file_sha256(path));
    model.profile_shards(k).sha256=file_records(k+1).sha256;model.profile_shards(k).bytes=fi.bytes;
end
model.generator_bus_ids=[model.generator_bus_ids(:);48;49];
model.external.generator_mask=[logical(model.external.generator_mask(:));false;true];
model.external.capability_proxy_MW=[model.external.capability_proxy_MW(:);0];
model.external.boundary_proxy_cap_is_hourly_absolute_fixed_P=true;
reg=model.generator_registry;new=reg(309,:);new.generator_row(:)=1465;
new.device_key(:)="EIA860:2025:PLANT:2694:GEN:21";new.current_bus_id(:)=48;new.native_profile_row(:)=true;
reg=[reg;new];new=reg(1464,:);new.generator_row(:)=1466;
new.device_key(:)="NYISO:P34:PTID:325270:SANDBAR_BOUNDARY_PROXY";new.current_bus_id(:)=49;new.native_profile_row(:)=false;
model.generator_registry=[reg;new];
model.boundary_injections=struct('generator_rows',1466,'external_groups',12,'fixed_Q_MVAr',0, ...
    'NY_bus_ids',49,'source_PTIDs',325270,'positive_direction','import into New York', ...
    'source_meter','Sand Bar PAR','physical_boundary_meter','Plattsburgh', ...
    'physical_meter_equivalence_certified',false,'AC_impedance_invented',false, ...
    'SouthHero_and_intervening_losses_measured',false,'same_total_ISONE_exchange_preserved',true);
for k=1:4
    t=original.templates{k};t.gen=[t.gen;t.gen(309,:);t.gen(1464,:)];t.gen(1465,1)=48;t.gen(1466,1)=49;
    t.genfuel=[t.genfuel(:);t.genfuel(309);t.genfuel(1464)];
    p=model.loss_static{k};p.native=[logical(p.native(:));true;false];
    p.external_gen_group=[p.external_gen_group(:);0;12];p.generator_share=[p.generator_share(:);0;0];
    p.boundary_injection_rows=1466;p.boundary_injection_external_groups=12;
    model.loss_static{k}=p;
    model.generator_bus_rows{k}=[model.generator_bus_rows{k}(:);find(t.bus(:,1)==48);find(t.bus(:,1)==49)];
    h=double(model.axis.template_hours(k));shard=1+(h>4380);local=h-(shard-1)*4380;pr=parts{shard};
    t.gen(:,2)=pr.generator_PG_MW(local,:)';t.gen(:,9)=pr.generator_Pmax_MW(local,:)';t.gen(:,10)=pr.generator_Pmin_MW(local,:)';
    t.gen(:,8)=t.gen(:,9)>0|t.gen(:,10)<0;
    external=model.external.generator_mask;t.gen(external,9:10)=repmat(t.gen(external,2),1,2);
    pcap=max(abs(t.gen(:,9:10)),[],2);cap=pcap;cap(external)=model.external.capability_proxy_MW;cap(1466)=abs(t.gen(1466,2));
    qcap=cap*tan(acos(.95));qcap(external)=sqrt(max(0,(cap(external)/.95).^2-t.gen(external,2).^2));qcap(t.gen(:,8)==0)=0;qcap(1466)=0;
    t.gen(:,3)=0;t.gen(:,4)=qcap;t.gen(:,5)=-qcap;t.gen(:,6)=t.bus(model.generator_bus_rows{k},8);t.gen(:,7)=max(cap/.95,1);
    wp=1./max(pcap,1);wq=.01./max(qcap,1);pg=t.gen(:,2);ng=size(t.gen,1);
    t.gencost=[2*ones(ng,1),zeros(ng,2),3*ones(ng,1),wp,-2*wp.*pg,wp.*pg.^2;2*ones(ng,1),zeros(ng,2),3*ones(ng,1),wq,zeros(ng,2)];
    u=t.userdata.ac_system;u.external_generator_mask=external;u.generator_p_reference=pg;u.generator_capability_reference=cap;
    u.generator_q_cap=qcap;u.generator_assumed_s_cap=cap/.95;u.generator_assumed_s_cap(1466)=abs(pg(1466));
    u.p_objective_weight=wp;u.q_objective_weight=wq;u.boundary_injection_rows=1466;u.boundary_injections_are_fixed_PQ=true;
    t.userdata.ac_system=u;t.userdata.moses_source_repair=model.boundary_injections;
    assert(isequaln(t.bus,original.templates{k}.bus)&&isequaln(t.branch,original.templates{k}.branch)&&isequaln(t.dcline,original.templates{k}.dcline));
    model.templates{k}=t;
end
model.model_id='NYGRID_2025_StLawrence_energy_and_PV20_boundary_proxy';
model.source_model_commit='f6c124a97b16f45a98a538c121c6006556255005';
model.created_utc=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd HH:mm:ss Z'));
model.moses_source_repair=struct('candidate_receipt_sha256',nylatest_file_sha256(candidate_path), ...
    'source_defined_not_fitted_to_interfaces',true,'plant_hourly_generation_is_reconstruction',true, ...
    'physical_PV20_meter_equivalence_certified',false,'baseline_static_model_sha256',prior.model_file.sha256);
model.policy.generation_monthly_energy_and_boundary_routing_changed=true;
model.policy.physical_branch_and_passive_shunt_arrays_preserved=true;
path=fullfile(out,'latest_model.mat');save(path,'model','-v7');fi=dir(path);
file_records(1)=struct('name','latest_model.mat','bytes',fi.bytes,'sha256',nylatest_file_sha256(path));
receipt=prior;receipt.model_file=file_records(1);receipt.model_files=file_records;receipt.profile_shards=model.profile_shards;
receipt.source_model_commit=model.source_model_commit;receipt.created_utc=model.created_utc;
receipt.baseline_model_receipt_sha256=nylatest_file_sha256(fullfile(base,'model_receipt.json'));
receipt.source_model_commit_role='Baseline; candidate sources and implementation bound by moses_source_repair receipt hash';
receipt.moses_source_repair=model.moses_source_repair;receipt.generator_count=1466;
receipt.all_annual_profile_arrays_copied_without_numeric_conversion=false;receipt.profile_shards_byte_identical_to_baseline=false;
receipt.fresh_PF_solve_run=false;receipt.annual_replay_run=false;
for k=1:numel(receipt.state_records)
    if isfield(receipt.state_records,'generator_count'),receipt.state_records(k).generator_count=1466;end
    if isfield(receipt.state_records,'generator_rows'),receipt.state_records(k).generator_rows=1466;end
end
fid=fopen(fullfile(out,'model_receipt.json'),'w');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(receipt,'PrettyPrint',true));
fprintf('MOSES_MODEL_EXPORTED ng1466 states4 sourcehours%d\n',nnz(q));
end
