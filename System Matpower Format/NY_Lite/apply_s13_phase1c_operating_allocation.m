function out=apply_s13_phase1c_operating_allocation(candidate,scenario)
%APPLY_S13_PHASE1C_OPERATING_ALLOCATION Redistribute existing zonal devices.
% This separate operating transformation never changes the constructor.
% Source PD/PMAX/QG supply spatial priors, not current operating observations.
% Unlimited source Q placeholders are replaced by relocated, bounded existing
% zonal Q capability. No source generator or shunt is added on top of totals.
define_constants;
assert(istable(scenario)&&height(scenario)==11&&numel(unique(scenario.zone))==11, ...
    'apply_s13_phase1c_operating_allocation:Scenario','Eleven unique zone rows required.');
assert(isfield(candidate.userdata,'s13')&&isfield(candidate.userdata.s13,'phase1c_report'), ...
    'apply_s13_phase1c_operating_allocation:Phase','A Phase 1C candidate is required.');
assert(~isfield(candidate.userdata,'phase1c_operating_allocation'), ...
    'apply_s13_phase1c_operating_allocation:AlreadyApplied','Allocation was already applied.');
[src,bm,~,~,sha]=s13_phase1c_source;
m=candidate;old_ng=size(m.gen,1);z=string(m.userdata.nyiso_physical_zone);
[~,mi]=ismember(bm.model_bus,m.bus(:,BUS_I));[~,si]=ismember(bm.source_bus,src.bus(:,BUS_I));
isnew=bm.model_action=="appended_zero_injection_terminal";
sz=perform_nyiso_zone_letters(src);[~,sgb]=ismember(src.gen(:,GEN_BUS),src.bus(:,BUS_I));
gz=sz(sgb);
% Fixed-P source proxies and huge Q boxes do not establish physical capacity.
realgen=src.gen(:,GEN_STATUS)>0&src.gen(:,PMAX)>0& ...
    src.gen(:,PMAX)<5000&src.gen(:,PMAX)>src.gen(:,PMIN)& ...
    max(abs(src.gen(:,[QMIN QMAX])),[],2)<2000;
qweight=abs(src.gen(:,QG)).*(src.gen(:,GEN_STATUS)>0);
qweight(~isfinite(qweight)|qweight>2000)=0;
load_audit=table();gen_audit=table();zone_audit=table();
for k=1:height(scenario)
    zone=string(scenario.zone(k));bi=find(z==zone);sel=find(bm.physical_zone==zone);
    if isempty(sel),continue;end
    oldbi=bi(~ismember(bi,mi(isnew)));newsel=sel(isnew(sel));
    totalpd=sum(m.bus(bi,PD));totalqd=sum(m.bus(bi,QD));
    assert(abs(totalpd-scenario.target_load_mw(k))<1e-5&& ...
        abs(totalqd-scenario.target_reactive_load_mvar(k))<1e-5, ...
        'apply_s13_phase1c_operating_allocation:LoadTarget','Apply reconstruction inputs first.');
    denom=sum(max(0,src.bus(sz==zone,PD)));
    share=zeros(numel(newsel),1);
    if denom>0,share=max(0,src.bus(si(newsel),PD))/denom;end
    fraction=sum(share);assert(fraction<=1+1e-12);
    % Input reconstruction may have used uniform weights for a zone with no
    % original demand. Reallocate that complete zonal total exactly once.
    wp=max(0,m.bus(oldbi,PD));if sum(wp)==0,wp=ones(size(wp));end
    wp=wp/sum(wp);wq=wp;
    if abs(sum(m.bus(oldbi,QD)))>1e-12,wq=m.bus(oldbi,QD)/sum(m.bus(oldbi,QD));end
    m.bus(oldbi,PD)=totalpd*(1-fraction)*wp;
    m.bus(oldbi,QD)=totalqd*(1-fraction)*wq;
    for j=1:numel(newsel)
        r=newsel(j);m.bus(mi(r),PD)=totalpd*share(j);m.bus(mi(r),QD)=totalqd*share(j);
        load_audit=[load_audit;table(zone,bm.source_bus(r),bm.model_bus(r), ...
            share(j),m.bus(mi(r),PD),m.bus(mi(r),QD),"reconstructed_source_PD_share", ...
            'VariableNames',{'zone','source_bus','model_bus','zonal_share','pd_mw','qd_mvar','policy'})]; %#ok<AGROW>
    end
    [~,gb]=ismember(m.gen(1:old_ng,GEN_BUS),m.bus(:,BUS_I));
    donors=find(z(gb)==zone&m.gen(1:old_ng,GEN_STATUS)>0);
    sums=sum(m.gen(donors,[PG PMIN PMAX QG QMIN QMAX]),1);
    pden=sum(src.gen(realgen&gz==zone,PMAX));qden=sum(qweight(gz==zone));
    pshare=zeros(numel(sel),1);qshare=pshare;
    for j=1:numel(sel)
        sr=bm.source_bus(sel(j));at=src.gen(:,GEN_BUS)==sr;
        if pden>0,pshare(j)=sum(src.gen(at&realgen,PMAX))/pden;end
        if qden>0,qshare(j)=sum(qweight(at))/qden;end
        gamma=scenario.scale_factor_gamma(k);
        if sums(3)>0
            pshare(j)=min(pshare(j),gamma*sum(src.gen(at&realgen,PMAX))/sums(3));
        end
        active=at&src.gen(:,GEN_STATUS)>0;
        placeholder=any(max(abs(src.gen(active,[QMIN QMAX])),[],2)>=2000);
        if ~placeholder
            if sums(6)>0
                qshare(j)=min(qshare(j),gamma*sum(max(0,src.gen(active,QMAX)))/sums(6));
            end
            if sums(5)<0
                qshare(j)=min(qshare(j),gamma*sum(max(0,-src.gen(active,QMIN)))/(-sums(5)));
            end
        end
    end
    assert(sum(pshare)<=1+1e-12&&sum(qshare)<=1+1e-12);
    m.gen(donors,[PG PMIN PMAX])=m.gen(donors,[PG PMIN PMAX])*(1-sum(pshare));
    m.gen(donors,[QG QMIN QMAX])=m.gen(donors,[QG QMIN QMAX])*(1-sum(qshare));
    for j=1:numel(sel)
        if pshare(j)==0&&qshare(j)==0,continue;end
        r=sel(j);sr=bm.source_bus(r);at=src.gen(:,GEN_BUS)==sr&src.gen(:,GEN_STATUS)>0;
        vg=median(src.gen(at,VG));vg=min(m.bus(mi(r),VMAX),max(m.bus(mi(r),VMIN),vg));
        row=zeros(1,size(m.gen,2));row(GEN_BUS)=bm.model_bus(r);row(GEN_STATUS)=1;
        row(MBASE)=m.baseMVA;row(VG)=vg;
        row([PG PMIN PMAX])=sums(1:3)*pshare(j);
        row([QG QMIN QMAX])=sums(4:6)*qshare(j);
        m.gen(end+1,:)=row;
        if m.bus(mi(r),BUS_TYPE)~=REF,m.bus(mi(r),BUS_TYPE)=PV;end
        placeholder=any(max(abs(src.gen(at,[QMIN QMAX])),[],2)>=2000);
        policy="relocated_bounded_zonal_generation_and_Q";
        if placeholder,policy="relocated_bounded_Q_source_placeholder_not_copied";end
        gen_audit=[gen_audit;table(zone,sr,bm.model_bus(r),size(m.gen,1), ...
            pshare(j),qshare(j),row(PMAX),row(QMIN),row(QMAX),vg,placeholder,policy, ...
            'VariableNames',{'zone','source_bus','model_bus','gen_row','active_capacity_share', ...
            'reactive_capability_share','pmax_mw','qmin_mvar','qmax_mvar','vg_pu', ...
            'source_Q_limits_placeholder','policy'})]; %#ok<AGROW>
    end
    [~,gb]=ismember(m.gen(:,GEN_BUS),m.bus(:,BUS_I));
    after=find(z(gb)==zone&m.gen(:,GEN_STATUS)>0);
    errors=[sum(m.bus(bi,PD))-totalpd,sum(m.bus(bi,QD))-totalqd, ...
        sum(m.gen(after,[PG PMIN PMAX QG QMIN QMAX]),1)-sums];
    assert(max(abs(errors))<1e-7,'apply_s13_phase1c_operating_allocation:Conservation', ...
        'Zonal load or generator capability was not conserved.');
    zone_audit=[zone_audit;table(zone,totalpd,totalqd,fraction,sum(pshare),sum(qshare), ...
        max(abs(errors)),true,'VariableNames',{'zone','pd_mw','qd_mvar','load_relocated_share', ...
        'P_capability_relocated_share','Q_capability_relocated_share', ...
        'max_conservation_error','conservation_pass'})]; %#ok<AGROW>
end
% Existing zonal shunts are retained. In particular, the source 500-MVAr EGC
% shunt is recorded as unresolved rather than silently added a second time.
shunt_audit=table(bm.source_bus,bm.model_bus,src.bus(si,GS),src.bus(si,BS), ...
    m.bus(mi,GS),m.bus(mi,BS),repmat("existing_model_shunts_preserved_source_shunts_not_added",height(bm),1), ...
    'VariableNames',{'source_bus','model_bus','source_gs_mw','source_bs_mvar', ...
    'model_gs_mw','model_bs_mvar','policy'});
prior=m.gen(:,PG);[~,gb]=ismember(m.gen(:,GEN_BUS),m.bus(:,BUS_I));
for k=1:height(scenario)
    rows=find(z(gb)==string(scenario.zone(k))&m.gen(:,GEN_STATUS)>0&m.gen(:,PMAX)>0);
    if ~isempty(rows)
        weights=m.gen(rows,PMAX)/sum(m.gen(rows,PMAX));
        prior(rows)=scenario.target_generation_mw(k)*weights;
    end
end
stale={'gen_name','genfuel','gentype','gencost','userfcn','A','l','u'};
for k=1:numel(stale),if isfield(m,stale{k}),m=rmfield(m,stale{k});end,end
m.userdata.phase1c_operating_allocation=struct('source_sha256',sha, ...
    'policy','source_spatial_priors_with_conserved_zonal_load_and_capability', ...
    'input_class','reconstructed_assumed_not_observed','promotion_eligible',false);
m.userdata.s13.model_role='unpromoted_phase1c_reconstructed_operating_case';
out=struct('candidate',m,'load_audit',load_audit,'generator_audit',gen_audit, ...
    'zone_audit',zone_audit,'shunt_audit',shunt_audit,'Pg_prior_mw',prior, ...
    'Pg_sigma_mw',max(50,0.3*max(0,m.gen(:,PMAX)-m.gen(:,PMIN))), ...
    'promotion_eligible',false,'source_shunt_qualification',false);
end
