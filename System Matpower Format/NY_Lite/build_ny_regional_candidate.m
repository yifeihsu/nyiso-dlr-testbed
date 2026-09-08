function out=build_ny_regional_candidate(n,foundation,options)
%BUILD_NY_REGIONAL_CANDIDATE Package B complete downstate function replacement.
% Preserve NPCC A-C branch parameters by default. Retire inherited branches
% touching D-K. Import original-source branches incident on the region plus
% satellite closure required to preserve source voltage classes at the cut.
% Upstate source injections and cut terminals use declared aggregation; this
% is not an assertion of exact physical correspondence for old equivalents.
if nargin<3,options=struct();end
define_constants;h=fileparts(mfilename('fullpath'));
if isfield(options,'parent'),parent=options.parent;else
    p=build_s13_phase1c_candidate(struct('write_outputs',false,'verbose',false));parent=p.candidate;
end
first=build_row235_replacement(parent,struct('write_outputs',false));
s=n.source;z=perform_nyiso_zone_letters(s);pz=string(parent.userdata.nyiso_physical_zone);
if ~isfield(options,'replacement_zones'),options.replacement_zones=string(('D':'K')');end
replacement_zones=unique(string(options.replacement_zones(:)));
assert(all(ismember(string(('G':'K')'),replacement_zones))&&all(ismember(replacement_zones,string(('A':'K')'))), ...
    'ny_region:Zones','The replacement must include G-K and only NY zones.');
oldregion=ismember(pz,replacement_zones);up=ismember(pz,string(('A':'K')'))&~oldregion;
uid=parent.bus(up,BUS_I);ub=parent.bus(up,1:13);uz=pz(up);
assert(~any(uid>=20000),'ny_region:IDs','Source region ID namespace is occupied.');
assert(s.baseMVA==parent.baseMVA,'ny_region:Base','Source and parent power bases differ.');
region=ismember(z,replacement_zones);
% Include all branch records in closure, so inactive identities cannot later
% reactivate with wrong voltage bases or silently missing electrical ports.
changed=true;
while changed
    touching=region(s.branch(:,F_BUS))|region(s.branch(:,T_BUS));
    ports=unique([s.branch(touching,F_BUS);s.branch(touching,T_BUS)]);
    outside=ports(~region(ports));include=false(size(outside));
    for k=1:numel(outside)
        row=outside(k);include(k)=~any(uz==z(row)&ub(:,BASE_KV)==s.bus(row,BASE_KV));
    end
    changed=any(include);region(outside(include))=true;
end
source_rows=find(region(s.branch(:,F_BUS))|region(s.branch(:,T_BUS)));
cross=region(s.branch(source_rows,F_BUS))~=region(s.branch(source_rows,T_BUS));
ports=unique([s.branch(source_rows(cross),F_BUS);s.branch(source_rows(cross),T_BUS)]);
ports=ports(~region(ports));
[map,anchors]=source_mapping(s,z,region,ports,ub,uz,parent,up,h);

% The operating case has disjoint source-region IDs; historical identity is
% represented in registers rather than by retaining inactive duplicate buses.
c=struct('version','2','baseMVA',parent.baseMVA);
rb=s.bus(region,1:13);rb(:,BUS_I)=20000+s.bus(region,BUS_I);
rb(:,[VM VA])=foundation.mpc.bus(region,[VM VA]);
% All initial phasors share the Package A reference angle. Aggregated bus
% phasors are declared anchor seeds, not measured states or new controls.
for k=1:size(ub,1)
    at=find(anchors.model_bus==ub(k,BUS_I));
    if ~isempty(at)
        rows=anchors.source_anchor_bus(at);
        ub(k,[VM VA])=mean(foundation.mpc.bus(rows,[VM VA]),1);
    end
end
c.bus=[ub;rb];c.bus_name=[parent.bus_name(up);s.bus_name(region)];
model_zones=[uz;z(region)];
c.userdata=struct('nyiso_physical_zone',{cellstr(model_zones)}, ...
    'package_b',struct('model_role','NPCC_retained_network_and_PERFORM_regional_research_candidate', ...
    'source_hash',n.canonical_sha256,'power_scale','historical_actual_mw', ...
    'electrical_baseline_qualified',false,'contemporary_validation_coverage','none','dlr_ready',false));
retained=find(ismember(parent.branch(:,F_BUS),uid)&ismember(parent.branch(:,T_BUS),uid));
retired=find(ismember(parent.branch(:,F_BUS),parent.bus(oldregion,BUS_I))| ...
    ismember(parent.branch(:,T_BUS),parent.bus(oldregion,BUS_I)));
physical=s.branch(source_rows,1:13);
physical(:,F_BUS)=map.model_bus(physical(:,F_BUS));physical(:,T_BUS)=map.model_bus(physical(:,T_BUS));
c.branch=[parent.branch(retained,1:13);physical];
old_native=ismember(parent.gen(:,GEN_BUS),uid);c.gen=parent.gen(old_native,1:21);
% Preserve legacy values for the allocation retirement ledger before complete
% replacement; retired-region legacy devices are separately registered below.
allocation=map_perform_injections_to_ny_candidate(c,n,foundation,struct('source_bus_map',map));
c=allocation.candidate;
source_branch_map=table(source_rows,(numel(retained)+(1:numel(source_rows)))', ...
    n.branch_inventory.device_key(source_rows),region(s.branch(source_rows,F_BUS)), ...
    region(s.branch(source_rows,T_BUS)), ...
    'VariableNames',{'source_branch_row','model_branch_row','device_key','from_in_exact_region','to_in_exact_region'});
retained_map=table(retained,(1:numel(retained))',"NPCC_PARENT:BRANCH:"+string(retained), ...
    'VariableNames',{'parent_branch_row','model_branch_row','device_key'});
disposition=repmat("fully_replaced_regional_function_assumed_correspondence",numel(retired),1);
disposition(retired==235)="fully_replaced_exact_parallel_equivalent";
legacy=table(retired,parent.branch(retired,F_BUS),parent.branch(retired,T_BUS), ...
    parent.branch(retired,BR_STATUS),disposition,zeros(numel(retired),1), ...
    repmat("historical_parent_kept_as_explicit_alternative_not_superimposed",numel(retired),1), ...
    'VariableNames',{'parent_branch_row','parent_from_bus','parent_to_bus','original_status','disposition', ...
    'new_active_contribution','alternative_policy'});
for col=[BR_R BR_X BR_B RATE_A RATE_B RATE_C TAP SHIFT ANGMIN ANGMAX]
    names={'r_pu','x_pu','b_pu','rate_a_mva','rate_b_mva','rate_c_mva','tap','shift_deg','angle_min_deg','angle_max_deg'};
    columns=[BR_R BR_X BR_B RATE_A RATE_B RATE_C TAP SHIFT ANGMIN ANGMAX];
    legacy.(names{find(columns==col)})=parent.branch(retired,col);
end
allny=up|oldregion;
oldbus=parent.bus(allny,:);oldgen=parent.gen(ismember(parent.gen(:,GEN_BUS),oldbus(:,BUS_I)),:);
legacy_bus=array2table(oldbus(:,[BUS_I PD QD GS BS]), ...
    'VariableNames',{'parent_bus','retired_pd_mw','retired_qd_mvar','retired_gs_mw','retired_bs_mvar'});
legacy_gen=table(find(ismember(parent.gen(:,GEN_BUS),oldbus(:,BUS_I))),oldgen(:,GEN_BUS), ...
    oldgen(:,PG),oldgen(:,QG),oldgen(:,PMIN),oldgen(:,PMAX),oldgen(:,QMIN),oldgen(:,QMAX), ...
    repmat("retired_once_replaced_by_source_keyed_native_records",size(oldgen,1),1), ...
    'VariableNames',{'parent_gen_row','parent_bus','old_pg_mw','old_qg_mvar','old_pmin_mw','old_pmax_mw', ...
    'old_qmin_mvar','old_qmax_mvar','disposition'});
branch_keys=[retained_map.device_key;source_branch_map.device_key];
parent_disposition=repmat("external_NPCC_network_removed_NY_boundary_PQ_registered_separately",size(parent.branch,1),1);
parent_disposition(retained)="retained_upstate_NPCC_parameters";
parent_disposition(retired)="replaced_downstate_regional_function";parent_disposition(235)="exact_parallel_equivalent_retired";
parent_branch_disposition=table((1:size(parent.branch,1))',parent.branch(:,F_BUS),parent.branch(:,T_BUS), ...
    parent.branch(:,BR_STATUS),parent_disposition,'VariableNames',{'parent_branch_row','parent_from_bus', ...
    'parent_to_bus','parent_status','disposition'});
out=struct('candidate',c,'parent',parent,'row235',first,'source_inventory',n,'foundation',foundation, ...
    'source_bus_map',map,'anchor_register',anchors,'source_branch_map',source_branch_map, ...
    'retired_branch_register',legacy,'retained_parent_branch_map',retained_map, ...
    'parent_branch_disposition',parent_branch_disposition, ...
    'region_source_buses',s.bus(region,BUS_I),'source_boundary_ports',ports,'replacement_zones',replacement_zones, ...
    'allocation',allocation,'branch_keys',branch_keys,'generator_keys',allocation.generator_keys, ...
    'retired_legacy_bus_injections',legacy_bus,'retired_legacy_generators',legacy_gen, ...
    'power_scale','historical_actual_mw','electrical_baseline_qualified',false, ...
    'contemporary_validation_coverage','none','dlr_ready',false);
end

function [map,a]=source_mapping(s,z,region,ports,ub,uz,parent,up,h)
define_constants;
names=upper(strtrim(string(s.bus_name)));pnames=upper(strtrim(string(parent.bus_name(up))));
old=readtable(fullfile(h,'perform_retained_control_anchors.csv'),'TextType','string');
a=table(zeros(0,1),zeros(0,1),strings(0,1), ...
    'VariableNames',{'source_anchor_bus','model_bus','anchor_policy'});
for k=1:size(ub,1)
    exact=find(names==pnames(k)&s.bus(:,BASE_KV)==ub(k,BASE_KV)&z==uz(k));
    if ~isempty(exact)
        a=[a;table(exact,repmat(ub(k,BUS_I),numel(exact),1),repmat("name_voltage_zone_source_anchor",numel(exact),1), ...
            'VariableNames',{'source_anchor_bus','model_bus','anchor_policy'})]; %#ok<AGROW>
    end
    % Historical plant anchors only seed a declared distance allocation. Their
    % source IDs are never represented as exact physical branch endpoints.
    at=find(old.retained_bus==ub(k,BUS_I));
    if ~isempty(at)&&old.source_anchor_count(at)>0
        ids=str2double(split(old.source_anchor_buses(at),'|'));
        ids=ids(isfinite(ids)&ids>=1&ids<=size(s.bus,1));ids=ids(z(ids)==uz(k));
        a=[a;table(ids,repmat(ub(k,BUS_I),numel(ids),1),repmat("historical_plant_proxy_for_distance_allocation",numel(ids),1), ...
            'VariableNames',{'source_anchor_bus','model_bus','anchor_policy'})]; %#ok<AGROW>
    end
end
% Documented spelling alias in the NPCC conversion, with matching345-kV base.
if any(ub(:,BUS_I)==37)
    assert(ub(ub(:,BUS_I)==37,BASE_KV)==345&&names(800)=="NEW SCOTLAND"&&z(800)=="F");
    a=[a;{800,37,"NEW_SEATHED_to_NEW_SCOTLAND_documented_345kV_alias"}];
end
[~,unique_rows]=unique([a.source_anchor_bus,a.model_bus],'rows','stable');a=a(unique_rows,:);
[~,ar]=ismember(a.model_bus,ub(:,BUS_I));a.zone=uz(ar);a.model_base_kv=ub(ar,BASE_KV);
active=s.branch(:,BR_STATUS)>0;
G=graph(s.branch(active,F_BUS),s.branch(active,T_BUS), ...
    max(hypot(s.branch(active,BR_R),s.branch(active,BR_X)),1e-8),size(s.bus,1));
[distinct,~,anchor_row]=unique(a.source_anchor_bus);
D=distances(G,distinct);D=D(anchor_row,:);
model=zeros(size(s.bus,1),1);kind=strings(size(model));distance=zeros(size(model));anchor=zeros(size(model));
for i=1:numel(model)
    if region(i),model(i)=20000+s.bus(i,BUS_I);kind(i)="exact_source_region";anchor(i)=i;continue;end
    eligible=find(a.zone==z(i));
    if ismember(i,ports),eligible=eligible(a.model_base_kv(eligible)==s.bus(i,BASE_KV));end
    assert(~isempty(eligible),'ny_region:Anchor','No declared same-zone/required-voltage anchor for source%d.',i);
    [distance(i),j]=min(D(eligible,i));selected=eligible(j);
    assert(isfinite(distance(i)),'ny_region:DisconnectedSource','Source%d has no finite path to a declared anchor.',i);
    model(i)=a.model_bus(selected);anchor(i)=a.source_anchor_bus(selected);
    kind(i)="assumed_same_zone_source_distance_aggregation";
    if ismember(i,ports),kind(i)="assumed_same_zone_same_kV_boundary_aggregation";end
end
map=table(s.bus(:,BUS_I),model,z,kind,anchor,distance,s.bus(:,BASE_KV), ...
    'VariableNames',{'source_bus','model_bus','zone','mapping_kind','allocation_anchor_source_bus', ...
    'source_path_impedance_distance_pu','source_base_kv'});
map.is_external_boundary_proxy=ismember(s.bus(:,BUS_I),[19;69;81;571;580;651;756;773;799;1132;1136;1148;1231;1313;1320;1413;1528;1546;1558;1570]);
end
