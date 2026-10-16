function out=audit_electrical_boundary_feasibility(inputs, options)
%AUDIT_ELECTRICAL_BOUNDARY_FEASIBILITY Necessary external active-power bound.
% For each connected external component after removing registered NY buses:
%   sum(PMAX_online) >= sum(PD_external) + sum(import_target - tolerance).
% Imports are measured at the NY tie terminals. Nonnegative series/shunt
% losses can only increase required external generation. A shortage proves
% infeasibility; passing this inequality establishes no AC feasibility.
% Certification requires exact, disjoint, complete tie-operator accounting.
% Regional groups spanning disconnected components are left uncertified.
if nargin<2,options=struct();end
if ~isfield(options,'numeric_tolerance_mw'),options.numeric_tolerance_mw=1e-7;end
m=inputs.candidate;c=inputs.controls;ids=m.bus(:,1);n=numel(ids);
if isfield(options,'ny_bus_ids')
    ny_ids=options.ny_bus_ids(:);
else
    annotated=attach_nyiso_zone_metadata(m);
    zones=string(annotated.userdata.nyiso_zone);
    ny_ids=ids(ismember(zones,string(('A':'K')')));
end
assert(all(ismember(ny_ids,ids))&&~isempty(ny_ids),'boundary_audit:NYMembership', ...
    'The NY retained bus set must be registered and present.');
ny=ismember(ids,ny_ids);external=~ny & m.bus(:,2)~=4;
[known_f,f]=ismember(m.branch(:,1),ids);[known_t,t]=ismember(m.branch(:,2),ids);
assert(all(known_f&known_t),'boundary_audit:UnknownBus','Unknown branch terminal.');
active=m.branch(:,11)>0 & m.bus(f,2)~=4 & m.bus(t,2)~=4;
ext_rows=find(external);ne=numel(ext_rows);local=zeros(n,1);local(ext_rows)=1:ne;
ee=active&external(f)&external(t);er=find(ee);
adj=sparse([local(f(er));local(t(er))],[local(t(er));local(f(er))],1,ne,ne);
component=conncomp(graph(adj));nc=max([component,0]);
Af=c.operator_from;At=c.operator_to;target=c.target_mw(:);band=c.tolerance_mw(:);
assert(isequal(size(Af),size(At))&&size(Af,2)==size(m.branch,1) && ...
    size(Af,1)==numel(target)&&numel(target)==numel(band), ...
    'boundary_audit:OperatorDimensions','Control matrix dimensions are inconsistent.');
assert(all(isfinite(target)&isfinite(band)&band>=0), ...
    'boundary_audit:InvalidTarget','Control targets/tolerances must be finite with nonnegative tolerances.');
if isfield(inputs,'regional_names'),names=string(inputs.regional_names(:));
else,names="CONTROL_"+string((1:numel(target))');end
assert(numel(names)==numel(target),'boundary_audit:GroupNames','Control group labels are incomplete.');
support=abs(Af)>1e-12|abs(At)>1e-12;
all_ties=active&xor(ny(f),ny(t));
all_ties=all_ties&(external(f)|external(t));
components=table();
for k=1:nc
    rows=ext_rows(component==k);in=false(n,1);in(rows)=true;
    ties=find(all_ties&(in(f)|in(t)));
    groups=find(any(support(:,ties),2));
    status="necessary_active_power_bound_satisfied_not_sufficient";
    eligible=true;covered=zeros(numel(ties),1);
    for g=groups(:)'
        members=find(support(g,:));
        if any(~ismember(members,ties))
            eligible=false;status="unavailable_group_spans_component_or_nonboundary_rows";break;
        end
        for br=members(:)'
            if ny(f(br)),expected_f=-1;expected_t=0;else,expected_f=0;expected_t=-1;end
            if abs(Af(g,br)-expected_f)>1e-12 || abs(At(g,br)-expected_t)>1e-12
                eligible=false;status="unavailable_operator_not_NY_terminal_import";break;
            end
            covered(ties==br)=covered(ties==br)+1;
        end
        if ~eligible,break;end
    end
    if eligible&&any(covered~=1)
        eligible=false;status="unavailable_incomplete_or_overlapping_tie_accounting";
    end
    passive_rows=find(active&((in(f)&in(t))|ismember((1:size(m.branch,1))',ties)));
    if eligible&&(any(~isfinite(m.branch(passive_rows,3))|m.branch(passive_rows,3)<0) || ...
            any(~isfinite(m.bus(rows,5))|m.bus(rows,5)<0))
        eligible=false;status="unavailable_nonnegative_loss_premise_not_met";
    end
    if isfield(m,'dcline')&&~isempty(m.dcline)
        dc=m.dcline(:,3)>0 & (ismember(m.dcline(:,1),ids(rows))|ismember(m.dcline(:,2),ids(rows)));
        if eligible&&any(dc),eligible=false;status="unavailable_unaccounted_controlled_DC";end
    end
    gr=ismember(m.gen(:,1),ids(rows))&m.gen(:,8)>0;
    cap=sum(m.gen(gr,9));minimum=sum(m.gen(gr,10));load_mw=sum(m.bus(rows,3));
    if eligible&&(any(~isfinite(m.gen(gr,[9 10])),'all') || ...
            any(m.gen(gr,10)>m.gen(gr,9)) || ~isfinite(load_mw))
        eligible=false;status="unavailable_invalid_or_unbounded_capability";
    end
    target_lower=NaN;required=NaN;shortage=NaN;infeasible=false;necessary_pass=false;
    if eligible
        target_lower=sum(target(groups)-band(groups));required=load_mw+target_lower;
        shortage=max(0,required-cap);infeasible=shortage>options.numeric_tolerance_mw;
        necessary_pass=~infeasible;
        if infeasible,status="provably_infeasible_external_active_power_shortage";end
    end
    components=[components;table(k,strjoin(string(ids(rows)),';'),strjoin(string(ties),';'), ...
        strjoin(names(groups),';'),load_mw,minimum,cap,target_lower,required,shortage, ...
        eligible,necessary_pass,infeasible,status, ...
        'VariableNames',{'component_id','external_bus_ids','boundary_branch_rows','control_groups', ...
        'external_load_mw','online_pmin_mw','online_pmax_mw','NY_import_lower_bound_mw', ...
        'required_min_generation_mw','generation_shortage_mw','certificate_eligible', ...
        'necessary_condition_passed','provably_infeasible','status'})]; %#ok<AGROW>
end
if isempty(components)
    infeasible=false;all_evaluated=true;passed=true;
else
    infeasible=any(components.provably_infeasible);
    all_evaluated=all(components.certificate_eligible);
    passed=all_evaluated&&all(components.necessary_condition_passed);
end
out=struct('components',components,'provably_infeasible',infeasible, ...
    'all_components_certified',all_evaluated,'necessary_conditions_passed',passed, ...
    'ac_feasibility_established',false,'promotion_eligible',false, ...
    'premise','Complete NY-terminal import accounting; nonnegative external/tie active losses; finite online P bounds.');
end
