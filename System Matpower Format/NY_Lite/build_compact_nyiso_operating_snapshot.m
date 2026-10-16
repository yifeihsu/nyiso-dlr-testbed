function out=build_compact_nyiso_operating_snapshot(build,inputs,scenario_id,options)
%BUILD_COMPACT_NYISO_OPERATING_SNAPSHOT Matched load and scheduled-import case.
% Starts from the gross compact construction, never the old fixed-boundary PF.
% Public P58C determines zonal MW shares. Within-zone placement, load Q/P,
% boundary landings and zero boundary Q are explicitly assumed model inputs.
if nargin<4,options=struct();end
if ~isfield(options,'default_load_power_factor'),options.default_load_power_factor=.97;end
if ~isfield(options,'prior_loss_fraction'),options.prior_loss_fraction=.03;end
if ~isfield(options,'generation_participation'),options.generation_participation=[];end
if ~isfield(options,'include_distinct_controllers'),options.include_distinct_controllers=true;end
if ~isfield(options,'hq_boundary_policy'),options.hq_boundary_policy="physical_proxy_with_separate_Cedars";end
assert(ismember(string(options.hq_boundary_policy),["physical_proxy_with_separate_Cedars","net_market_proxy_with_separate_Cedars"]));
define_constants;id=string(scenario_id);c=build.candidate;
s=inputs.snapshots(string(inputs.snapshots.scenario_id)==id,:);assert(height(s)==1,'compact_snapshot:Scenario','Unique scenario required.');
l=inputs.loads(string(inputs.loads.scenario_id)==id,:);
b=inputs.boundaries(string(inputs.boundaries.scenario_id)==id,:);
omitted=table();
if isfield(inputs,'external_records')
    e=inputs.external_records(string(inputs.external_records.scenario_id)==id,:);
    distinct=ismember(string(e.public_interface_name),["SCH - NPX_CSC";"SCH - NPX_1385";"SCH - PJM_NEPTUNE";"SCH - PJM_VFT";"SCH - PJM_HTP"]);
    if options.include_distinct_controllers
        take=e.default_primary_scope|distinct|e.public_interface_name=="SCH - HQ_CEDARS";
        if string(options.hq_boundary_policy)=="net_market_proxy_with_separate_Cedars"
            take(e.public_interface_name=="SCH - HQ - NY")=false;
            take(e.public_interface_name=="SCH - HQ_IMPORT_EXPORT")=true;
        end
        b=e(take,:);
        extra=~b.default_primary_scope;b.external_region(extra)=b.public_interface_name(extra);
    end
    omitted=e(~ismember(e.public_interface_name,b.public_interface_name),:);
end
t=inputs.interfaces(string(inputs.interfaces.scenario_id)==id,:);
assert(height(l)==11&&numel(unique(string(l.zone)))==11&&all(isfinite(l.target_load_mw)&l.target_load_mw>=0));
ny=ismember(c.bus(:,BUS_I),build.ny_bus_ids);ids=c.bus(ny,BUS_I);
assert(nnz(ny)<=200&&all(ismember((37:82)',ids)),'compact_snapshot:NYIdentity','NY-only bus budget/original identity failed.');
br=ismember(c.branch(:,F_BUS),ids)&ismember(c.branch(:,T_BUS),ids);ge=ismember(c.gen(:,GEN_BUS),ids);
zones=string(c.userdata.nyiso_physical_zone(ny));
m=struct('version','2','baseMVA',c.baseMVA,'bus',c.bus(ny,1:13),'branch',c.branch(br,1:13), ...
    'gen',c.gen(ge,1:21),'bus_name',{c.bus_name(ny)}, ...
    'userdata',struct('nyiso_physical_zone',{cellstr(zones)}));
branch_keys=string(build.branch_keys(br));generator_keys=string(build.generator_keys(ge));
branch_map=table((1:nnz(br))',find(br),branch_keys, ...
    'VariableNames',{'model_branch_row','full_branch_row','branch_key'});
generator_map=table((1:nnz(ge))',find(ge),generator_keys, ...
    'VariableNames',{'model_gen_row','full_gen_row','generator_key'});
original_pd=m.bus(:,PD);original_qd=m.bus(:,QD);m.bus(:,[PD QD])=0;
map=nyiso_bus_zone_map;allocation_weight=zeros(size(m.bus,1),1);qratio=zeros(size(allocation_weight));
for k=1:height(l)
    z=string(l.zone(k));members=find(zones==z&ismember(ids,[map.bus_id]));assert(~isempty(members));
    w=max(original_pd(members),0);
    if sum(w)==0
        for j=1:numel(members),mi=find([map.bus_id]==ids(members(j)));w(j)=map(mi).load_proxy_weight;end
    end
    assert(sum(w)>0,'compact_snapshot:LoadPlacement','Zone has no original load or registered proxy weights.');
    w=w/sum(w);allocation_weight(members)=w;m.bus(members,PD)=l.target_load_mw(k)*w;
    ratios=tan(acos(options.default_load_power_factor))*ones(numel(members),1);
    prior_positive=original_pd(members)>1e-8;
    ratios(prior_positive)=original_qd(members(prior_positive))./original_pd(members(prior_positive));
    qratio(members)=ratios;m.bus(members,QD)=m.bus(members,PD).*ratios;
end
grossP=m.bus(:,PD);grossQ=m.bus(:,QD);bp=zeros(size(grossP));bq=bp;boundary=table();
for k=1:height(b)
    name=string(b.external_region(k));[landing,w,basis]=boundary_landing(name);
    assert(all(ismember(landing,ids))&&abs(sum(w)-1)<1e-12,'compact_snapshot:BoundaryLanding','Missing boundary landing or invalid weights.');
    [~,at]=ismember(landing,ids);p=b.target_import_mw(k)*w;
    assert(isfinite(b.target_import_mw(k)),'compact_snapshot:BoundaryValue','Boundary P must be finite.');
    bp=bp+accumarray(at,p,[numel(ids),1]);
    boundary=[boundary;table(repmat(id,numel(at),1),repmat(name,numel(at),1),landing,w,p,zeros(numel(at),1), ...
        repmat(basis,numel(at),1),repmat("assumed_zero_Q_unobserved",numel(at),1), ...
        'VariableNames',{'scenario_id','external_region','model_bus','allocation_weight','p_injection_mw','q_injection_mvar','landing_assumption','q_assumption'})]; %#ok<AGROW>
end
assert(numel(unique(string(b.external_region)))==height(b),'compact_snapshot:DuplicateBoundary','Each scheduled region/controller must be counted once.');
m.bus(:,PD)=grossP-bp;m.bus(:,QD)=grossQ-bq;
m.bus(m.bus(:,BUS_TYPE)==REF,BUS_TYPE)=PV;
ref=find(ids==42);assert(any(m.gen(:,GEN_BUS)==42&m.gen(:,GEN_STATUS)>0));m.bus(ref,BUS_TYPE)=REF;
m.bus(:,VM)=min(m.bus(:,VMAX),max(m.bus(:,VMIN),1));m.bus(:,VA)=0;
on=m.gen(:,GEN_STATUS)>0;capacity=max(0,m.gen(:,PMAX)-m.gen(:,PMIN));capacity(~on)=0;
if isempty(options.generation_participation),participation=capacity;
else,participation=double(options.generation_participation(:));end
assert(numel(participation)==size(m.gen,1)&&all(isfinite(participation)&participation>=0)&&sum(participation)>0);
participation(~on)=0;participation=participation/sum(participation);
required=sum(grossP)*(1+options.prior_loss_fraction)-sum(bp);
prior=m.gen(:,PMIN)+max(0,required-sum(m.gen(on,PMIN)))*participation;
prior=min(m.gen(:,PMAX),max(m.gen(:,PMIN),prior));prior(~on)=0;
m.gen(:,PG)=prior;m.gen(:,QG)=min(m.gen(:,QMAX),max(m.gen(:,QMIN),0));m.gen(:,VG)=1;
m.gencost=[2*ones(size(prior)),zeros(numel(prior),2),3*ones(size(prior)),zeros(numel(prior),3)];
ledger=table(ids,zones,original_pd,grossP,grossQ,bp,bq,m.bus(:,PD),m.bus(:,QD),allocation_weight,qratio, ...
    'VariableNames',{'model_bus','zone','parent_pd_mw','pd_gross_mw','qd_gross_mvar','p_boundary_mw','q_boundary_mvar', ...
    'pd_effective_mw','qd_effective_mvar','within_zone_allocation_weight','assumed_q_over_p'});
out=struct('candidate',m,'snapshot',s,'scenario_id',id,'loads',l,'interface_targets',t, ...
    'boundary_inputs',b,'boundary_register',boundary,'omitted_boundary_records',omitted,'bus_injection_ledger',ledger, ...
    'branch_keys',branch_keys,'generator_keys',generator_keys,'operators',compact_nyiso_interface_operators(m,branch_keys), ...
    'branch_map',branch_map,'generator_map',generator_map, ...
    'Pg_prior_mw',prior,'Pg_sigma_mw',max(100,.25*capacity),'generation_participation',participation, ...
    'prior_method',"capacity_or_frozen_training_participation_scaled_to_net_demand_plus_declared_loss_prior", ...
    'prior_loss_fraction',options.prior_loss_fraction,'heldout_interfaces_used_in_prior',false, ...
    'hq_boundary_policy',string(options.hq_boundary_policy), ...
    'electrical_baseline_qualified',false,'dlr_ready',false);
out.accounting_error_mw=max([abs(sum(grossP)-sum(l.target_load_mw));abs(sum(bp)-sum(b.target_import_mw)); ...
    abs(m.bus(:,PD)-(grossP-bp))]);
assert(out.accounting_error_mw<1e-7,'compact_snapshot:Accounting','Load or boundary accounting failed.');
end
function [bus,w,basis]=boundary_landing(region)
name=upper(strtrim(string(region)));
switch name
    case {"HQ","SCH - HQ - NY","HQ_NY"},bus=48;w=1;
    case {"SCH - HQ_CEDARS","SCH - HQ_IMPORT_EXPORT"},bus=48;w=1;
    case {"NE","ISONE","SCH - NE - NY"},bus=[37;73];w=[.4;.6];
    case {"OH","ONTARIO","SCH - OH - NY"},bus=54;w=1;
    case {"PJ","PJM","SCH - PJ - NY"},bus=[66;67;75;81];w=[.35;.15;.25;.25];
    case {"CSC","SCH - NPX_CSC"},bus=80;w=1;
    case {"1385","SCH - NPX_1385"},bus=80;w=1;
    case {"NEPTUNE","SCH - PJM_NEPTUNE"},bus=80;w=1;
    case {"VFT","SCH - PJM_VFT"},bus=81;w=1;
    case {"HTP","SCH - PJM_HTP"},bus=81;w=1;
    otherwise,error('compact_snapshot:BoundaryScope','No declared landing for %s; do not silently drop or double count it.',region);
end
basis="assumed_aggregate_NY_landing_split_not_observed_terminal_power";
end
