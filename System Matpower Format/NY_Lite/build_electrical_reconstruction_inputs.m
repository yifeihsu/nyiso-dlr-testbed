function out=build_electrical_reconstruction_inputs(source, scenario_id)
%BUILD_ELECTRICAL_RECONSTRUCTION_INPUTS Historical bounded research inputs.
% PERFORM installed capacities are separate from gamma-scaled availability.
% This repairs the inherited A/B/C participation cap without calling it an
% outage/availability observation. Spatial weights and Q/P limits are assumed.
% Contemporary input ingestion uses validate_research_inputs, separately.
define_constants;
here=fileparts(mfilename('fullpath'));
T=readtable(fullfile(here,'s13_phase1a_common_input_spec.csv'),'TextType','string');
T=T(T.scenario_id==string(scenario_id),:);
assert(height(T)==11 && numel(unique(T.zone))==11,'Unknown/incomplete historical scenario.');
m=attach_nyiso_zone_metadata(source); zones=string(m.userdata.nyiso_zone);
if isempty(zones),error('No zone metadata.');end
% Source case row metadata cannot be reused after appending aggregate devices.
remove={'gen_name','genfuel','gentype','gencost','userfcn','A','l','u'};
for k=1:numel(remove),if isfield(m,remove{k}),m=rmfield(m,remove{k});end,end
prior=m.gen(:,PG); sig=max(50,0.25*(m.gen(:,PMAX)-m.gen(:,PMIN)));
register=table();
for k=1:height(T)
    z=T.zone(k); bi=find(zones==z);
    assert(~isempty(bi),'Missing zone allocation bus.');
    weight=max(0,m.bus(bi,PD));
    if sum(weight)==0,weight=ones(numel(bi),1);end
    weight=weight/sum(weight);
    m.bus(bi,PD)=T.target_load_mw(k)*weight;
    m.bus(bi,QD)=T.target_reactive_load_mvar(k)*weight;
    gr=find(ismember(m.gen(:,GEN_BUS),m.bus(bi,BUS_I)) & m.gen(:,GEN_STATUS)>0 & m.gen(:,PMAX)>0);
    added=false;
    if isempty(gr) && T.s12_generation_capacity_mw(k)>0
        % Prefer existing generator terminal, including offline aggregate rows.
        old=find(ismember(m.gen(:,GEN_BUS),m.bus(bi,BUS_I)),1);
        if isempty(old),bus_id=m.bus(bi(1),BUS_I);else,bus_id=m.gen(old,GEN_BUS);end
        row=zeros(1,size(m.gen,2)); row(GEN_BUS)=bus_id;row(VG)=1;
        row(MBASE)=m.baseMVA;row(GEN_STATUS)=1;
        m.gen(end+1,:)=row;gr=size(m.gen,1);prior(gr)=0;sig(gr)=50;added=true;
    end
    assert(~isempty(gr),'Missing generation allocation for zone %s.',z);
    capacity=T.s12_generation_capacity_mw(k)*T.scale_factor_gamma(k);
    gw=max(0,m.gen(gr,PMAX));if sum(gw)==0,gw=ones(numel(gr),1);end
    gw=gw/sum(gw);available=capacity*gw;
    m.gen(gr,PMAX)=available;m.gen(gr,PMIN)=0;
    m.gen(gr,QMAX)=available*tan(acos(0.9));m.gen(gr,QMIN)=-m.gen(gr,QMAX);
    prior(gr)=T.target_generation_mw(k)*gw;
    sig(gr)=max(50,0.3*available);
    m.gen(gr,PG)=min(available,prior(gr));m.gen(gr,QG)=0;
    [~,gb]=ismember(m.gen(gr,GEN_BUS),m.bus(:,BUS_I));
    m.bus(gb(m.bus(gb,BUS_TYPE)~=REF),BUS_TYPE)=PV;
    for j=1:numel(gr)
        register=[register;table(string(scenario_id),z,gr(j),m.gen(gr(j),GEN_BUS), ...
            T.s12_generation_capacity_mw(k)*gw(j),available(j),prior(gr(j)), ...
            m.gen(gr(j),QMIN),m.gen(gr(j),QMAX),added, ...
            "reconstructed","assumed_capacity_share","assumed_pf_0p9", ...
            'VariableNames',{'scenario_id','zone','gen_row','bus_id','installed_mw', ...
            'available_mw','dispatch_prior_mw','qmin_mvar','qmax_mvar', ...
            'new_zonal_equivalent','provenance','spatial_allocation','q_capability_policy'})]; %#ok<AGROW>
    end
end
% A declared research envelope, applied to all retained NPCC voltage levels.
m.bus(:,VMIN)=0.95;m.bus(:,VMAX)=1.05;
E=readtable(fullfile(here,'s13_phase1a_external_schedule_map.csv'),'TextType','string');
E=E(E.scenario_id==string(scenario_id),:);
regions=["HQ";"ONTARIO";"ISONE";"PJM"];
% Derive PJM membership from endpoint identities instead of trusting row IDs.
external_ids={100,[102 103],[29 35],[140 134 138 124 125]};
ny=m.bus(ismember(zones,string(('A':'K')')),BUS_I);
Af=sparse(4,size(m.branch,1));At=Af;target=zeros(4,1);op=table();
for k=1:4
    rr=find((ismember(m.branch(:,F_BUS),ny)&ismember(m.branch(:,T_BUS),external_ids{k})) | ...
        (ismember(m.branch(:,T_BUS),ny)&ismember(m.branch(:,F_BUS),external_ids{k})));
    rr=rr(m.branch(rr,BR_STATUS)>0);
    assert(~isempty(rr),'Missing regional tie.');
    rows=E(E.s13_region==regions(k),:);
    assert(~isempty(rows) && max(rows.regional_target_mw)-min(rows.regional_target_mw)<1e-6, ...
        'Incomplete/inconsistent regional schedule.');
    target(k)=rows.regional_target_mw(1);
    for r=rr(:)'
        if ismember(m.branch(r,F_BUS),ny),Af(k,r)=-1;terminal="from";else,At(k,r)=-1;terminal="to";end
        op=[op;table(regions(k),r,terminal,-1,"regional_aggregate_proxy", ...
            'VariableNames',{'region','branch_row','terminal','coefficient','measurement_class'})]; %#ok<AGROW>
    end
end
controls=struct('Pg_prior_mw',prior(:),'Pg_sigma_mw',sig(:), ...
    'operator_from',Af,'operator_to',At,'target_mw',target,'tolerance_mw',ones(4,1)*10);
m.userdata.electrical_reconstruction=struct('scenario_id',string(scenario_id), ...
    'input_vintage',2019,'scale_policy','historical_scaled_pattern', ...
    'availability_policy','gamma_times_PERFORM_installed_not_observed', ...
    'voltage_policy','assumed_0p95_to_1p05','promotion_eligible',false);
out=struct('candidate',m,'controls',controls,'generator_register',register, ...
    'operator_register',op,'regional_names',regions,'scenario',T, ...
    'public_operator_exact',false,'promotion_eligible',false);
end
