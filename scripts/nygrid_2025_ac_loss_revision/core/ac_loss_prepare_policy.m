function p=ac_loss_prepare_policy(m)
%AC_LOSS_PREPARE_POLICY Loss ownership and finite regional balancing contract.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
p.labels=[cellstr(('A':'K')');{'ISONE';'ONTARIO';'PJM'}];p.NY=1:11;p.external=12:14;
registry=readtable(fullfile(root,'output','nygrid_2025_downstate','network','bus_register.csv'),'TextType','string');
ids=m.bus(:,1);nb=size(m.bus,1);p.bus_group=zeros(nb,1);
for i=1:height(registry)
    r=find(ids==registry.model_bus(i));if isempty(r),continue;end
    zone=char(registry.accounting_zone(i));g=find(strcmp(p.labels,zone));
    if isempty(g)
        area=m.bus(r,7);
        if area==1,g=12;elseif area==4,g=13;elseif ismember(area,[5 6]),g=14;
        else,error('acLoss:Region','Unresolved original bus region.');end
    end
    p.bus_group(r)=g;
end
% The fixed-PAR auxiliary is on the NY side of the Dover export corridor.
p.bus_group(ids==21001)=find(strcmp(p.labels,'G'));
map=m.userdata.ac_sections.branch_map;parent=m.userdata.ac_system.branch_parent_row(:);
np=max(parent);p.parent=parent;p.parent_from=zeros(np,1);p.parent_to=zeros(np,1);
p.from_runtime=zeros(np,1);p.to_runtime=zeros(np,1);p.loss_ownership=zeros(14,np);
for k=1:np
    rows=find(parent==k);assert(~isempty(rows));
    first=rows(map.physical_terminal_from(rows));last=rows(map.physical_terminal_to(rows));
    assert(isscalar(first)&&isscalar(last));
    p.from_runtime(k)=first;p.to_runtime(k)=last;
    f=find(ids==m.branch(first,1));t=find(ids==m.branch(last,2));
    gf=p.bus_group(f);gt=p.bus_group(t);assert(gf>0&&gt>0,'acLoss:UnmappedPhysicalEnd','Physical corridor endpoint has no accounting group.');
    p.parent_from(k)=gf;p.parent_to(k)=gt;
    if gf<=11&&gt<=11
        p.loss_ownership(gf,k)=p.loss_ownership(gf,k)+.5;p.loss_ownership(gt,k)=p.loss_ownership(gt,k)+.5;
    elseif gf>11&&gt>11
        assert(gf==gt,'acLoss:ExternalMesh','Policy requires no inter-external-region corridors.');p.loss_ownership(gf,k)=1;
    else
        g=max(gf,gt);p.loss_ownership(g,k)=1;
    end
end
assert(all(abs(sum(p.loss_ownership,1)-1)<1e-14));
assert(all(m.bus(:,5)==0),'acLoss:Conductance','Add explicit ownership before modeling nonzero GS.');
assert(all(m.dcline(:,16:17)==0,'all'),'acLoss:DCLoss','Current policy requires zero modeled DC losses.');
p.DC_external_group=zeros(size(m.dcline,1),1);
for k=1:size(m.dcline,1)
    f=find(ids==m.dcline(k,1));t=find(ids==m.dcline(k,2));gf=p.bus_group(f);gt=p.bus_group(t);
    assert(gf>11&&gt>=1&&gt<=11,'acLoss:DCRegion','Expected signed external-to-NY controlled transfer.');
    p.DC_external_group(k)=gf;
end
p.gross_PD=m.bus(:,3);p.gross_QD=m.bus(:,4);p.baseline_PG=m.gen(:,2);
p.group_gross_PD=accumarray(max(1,p.bus_group),m.bus(:,3),[14 1]);
assert(all(m.bus(p.bus_group==0,3:4)==0,'all'),'acLoss:InteriorLoad','Unmapped numerical interior must stay zero injection.');
p.native=~m.userdata.ac_system.external_generator_mask;
p.external_gen_group=zeros(size(m.gen,1),1);p.generator_share=zeros(size(m.gen,1),1);
allocation=readtable(fullfile(root,'output','nygrid_2025_western_audit','dispatch','all_boundary_external_generator_shares.csv'),'TextType','string');
assert(all(ismember({'model_gen_row_1based','region','frozen_generation_share'},allocation.Properties.VariableNames)));
for j=1:height(allocation)
    row=allocation.model_gen_row_1based(j);g=find(strcmp(p.labels,char(allocation.region(j))));
    if isempty(g),assert(strcmp(allocation.region(j),'HQ'));continue;end
    assert(g>11);p.external_gen_group(row)=g;p.generator_share(row)=allocation.frozen_generation_share(j);
end
p.HQ=find(m.userdata.ac_system.external_generator_mask&p.external_gen_group==0);
assert(isscalar(p.HQ)&&m.gen(p.HQ,1)==48);
base=load(fullfile(root,'output','nygrid_2025_inputs','model','operating_inputs.mat'),'base_case');
original=m.userdata.ac_system.external_parent_generator_rows(:);current=m.userdata.ac_system.external_current_generator_rows(:);
assert(isequal(base.base_case.gen(original,1),m.gen(current,1)));
p.Pmax=m.gen(:,9);p.Pmin=m.gen(:,10);
for g=12:14
    use=find(p.external_gen_group==g);assert(abs(sum(p.generator_share(use))-1)<1e-12);
    [ok,k]=ismember(use,current);assert(all(ok));
    p.Pmax(use)=base.base_case.gen(original(k),9);p.Pmin(use)=base.base_case.gen(original(k),10);
end
assert(all(p.baseline_PG>=p.Pmin-1e-8&p.baseline_PG<=p.Pmax+1e-8));
for g=12:14
    p.target_NY_import(g-11,1)=sum(p.baseline_PG(p.external_gen_group==g))-sum(p.gross_PD(p.bus_group==g));
end
ref=m.bus(m.bus(:,2)==3,1);assert(isscalar(ref));p.reference=find(m.gen(:,1)==ref&m.gen(:,8)>0,1);
p.reference_bus=ref;p.S_cap=m.userdata.ac_system.generator_assumed_s_cap;
p.external_original_P_capabilities_are_proxies=true;
p.policy='NY_boundary_load_partition_and_external_area_loss_balance_at_NY_terminals';
end
