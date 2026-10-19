function m=ac_loss_prepare_case(m,mode)
%AC_LOSS_PREPARE_CASE Versioned treatment of the released E-G equivalent.
% No installed Gilboa-Buchanan line or conductor parameters are asserted.
if nargin<2,mode='released_equivalent';end
assert(any(strcmp(mode,{'released_equivalent','legacy_engineering'})));
assert(~isfield(m.userdata,'ac_loss_revision'),'acLoss:AlreadyApplied','Use an unrevised source case.');
assert(~isfield(m.userdata,'ac_dlr'),'acLoss:ThermalPreparedInput', ...
    'Use a fresh source case; existing temperature/current-limit state must not be carried onto the aggregate revision.');
parents=m.userdata.ac_system.branch_parent_row(:);rows=find(parents==224);
assert(numel(rows)==2&&m.branch(rows(1),1)==38&&m.branch(rows(end),2)==77);
before=sum(m.branch(rows,3:5),1);reactor_removed=0;
if strcmp(mode,'released_equivalent')
    m.branch(rows,3:5)=repmat([.02 .0147 0]/numel(rows),numel(rows),1);
    % Reverse only the synthetic compensation belonging to this aggregate.
    ledger=m.userdata.ac_sections.reactor_ledger;
    hit=find([ledger.original_branch_row]==224);assert(numel(hit)<=1);
    if ~isempty(hit)
        q=ledger(hit).applied_total_reactor_mvar_at1pu;
        f=find(m.bus(:,1)==ledger(hit).from_bus);t=find(m.bus(:,1)==ledger(hit).to_bus);
        m.bus([f;t],6)=m.bus([f;t],6)+q/2;reactor_removed=q;
        ledger(hit).applied_total_reactor_mvar_at1pu=0;
        ledger(hit).from_bus_BS_delta_mvar=0;ledger(hit).to_bus_BS_delta_mvar=0;
        ledger(hit).policy='removed_unidentified_OH_design_for_released_network_equivalent';
        m.userdata.ac_sections.reactor_ledger=ledger;
        m.userdata.ac_sections.reactor_BS_delta([f;t])=m.userdata.ac_sections.reactor_BS_delta([f;t])+q/2;
    end
    m.branch(rows,6:8)=0; % No identified conductor/apparatus rating for this equivalent.
    s=m.userdata.ac_system;
    if isfield(s,'thermal_segments')
        s.thermal_segments=s.thermal_segments(~ismember(s.thermal_segments.branch_row,rows),:);
    end
    for key={'terminal_current_limits','conductor_section_end_current_limits','cable_section_static_current_limits'}
        if isfield(s,key{1}),v=s.(key{1});s.(key{1})=v(~ismember(v.branch_row,rows),:);end
    end
    m.userdata.ac_system=s;
    m.userdata.ac_system.terminal_current_constraints_applied=false;
    m.userdata.ac_system.thermal_constraints_applied=false;
    ts=m.userdata.ac_sections.thermal_segments;
    if istable(ts),ts=ts(~ismember(ts.branch_row,rows),:);
    elseif iscell(ts),ts=ts(~cellfun(@(x)ismember(x.branch_row,rows),ts));
    else,ts=ts(~ismember([ts.branch_row],rows));end
    m.userdata.ac_sections.thermal_segments=ts;
    m.userdata.ac_sections.terminal_current_limit_A(rows,:)=NaN;
    % This public revision is PF-only. Removing formulation callbacks avoids
    % leaving invalid legacy ampacity assertions reachable through an OPF call.
    if isfield(m,'userfcn')&&isfield(m.userfcn,'formulation'),m.userfcn=rmfield(m.userfcn,'formulation');end
end
m.userdata.ac_loss_revision=struct('version',1,'impedance_mode',mode, ...
    'parent224_before_R_X_B',before,'parent224_after_R_X_B',sum(m.branch(rows,3:5),1), ...
    'parent224_runtime_rows',rows,'parent224_reactor_removed_MVAr',reactor_removed, ...
    'parent224_is_released_network_equivalent',strcmp(mode,'released_equivalent'), ...
    'parent224_physical_impedance_validated',false,'parent224_conductor_DLR_eligible',false, ...
    'parent224_temperature_resistance_update_allowed',false, ...
    'topology_bus_and_branch_axes_preserved',true,'OPF_supported',false);
end
