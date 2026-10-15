function [m,receipt]=nyrepair_apply_185195(m)
% Redistribute the existing 75% reactor rating along the two long equivalents.
% This is a declared synthetic compensation design, not installed equipment.
% Per-section charging is compensated with a half reactor at each local end.
% R/X/B, thermal data, voltage controls, limits and axes stay unchanged.
assert(~isfield(m.userdata,'physical_repair_185195'),'nyrepair:AlreadyApplied','Apply the compensation repair once.');
old=m;ids=m.bus(:,1);nb=size(m.bus,1);sec=m.userdata.ac_sections;
parents=m.userdata.ac_system.branch_parent_row(:);ledger=sec.reactor_ledger;
original_count=double(sec.original_bus_count);
old_delta=zeros(nb,1);old_delta(1:numel(sec.reactor_BS_delta))=sec.reactor_BS_delta(:);
net_change=zeros(nb,1);entries=struct([]);
% Extend every ledger row consistently; unchanged rows retain empty new fields.
for j=1:numel(ledger)
    ledger(j).distributed_bus_ids=[];ledger(j).distributed_bus_BS_delta_mvar=[];
    ledger(j).intermediate_compensation_is_synthetic=false;
end
for parent=[185,195]
    rr=find(parents==parent);jj=find([ledger.original_branch_row]==parent);
    assert(isscalar(jj)&&~isempty(rr),'nyrepair:Parent','Expected one reactor record per target parent.');
    rec=ledger(jj);active=m.branch(rr,11)>0;
    assert(all(active)||~any(active),'nyrepair:PartialStatus','All sections must share the parent status.');
    assert(all(m.branch(rr,9)==0|m.branch(rr,9)==1)&&all(m.branch(rr,10)==0));
    [ok,fr]=ismember(m.branch(rr,1),ids);assert(all(ok));
    [ok,tr]=ismember(m.branch(rr,2),ids);assert(all(ok));
    f=find(ids==rec.from_bus);t=find(ids==rec.to_bus);assert(isscalar(f)&&isscalar(t));
    assert(rec.fraction==.75&&logical(rec.associated_line_active)==all(active));
    nominal=.75*m.baseMVA*sum(m.branch(rr,5).*double(active));
    assert(abs(nominal-rec.applied_total_reactor_mvar_at1pu)<1e-8,'nyrepair:Rating','Frozen reactor rating differs from 75%% charging.');
    removed=zeros(nb,1);removed(f)=rec.from_bus_BS_delta_mvar;removed(t)=rec.to_bus_BS_delta_mvar;
    assert(abs(sum(removed)+nominal)<1e-8);
    new_delta=accumarray([fr;tr],[-.75*m.baseMVA*m.branch(rr,5).*double(active)/2; ...
        -.75*m.baseMVA*m.branch(rr,5).*double(active)/2],[nb,1]);
    nodes=unique([fr;tr]);internal=setdiff(nodes,[f;t]);
    assert(all(m.bus(internal,[2,3,4,5,6])==repmat([1,0,0,0,0],numel(internal),1),'all'), ...
        'nyrepair:Interior','Expected passive unloaded uncompensated section interiors.');
    assert(~any(ismember(ids(internal),m.gen(:,1)))&&~any(ismember(ids(internal),m.dcline(:,1:2)),'all'));
    assert(abs(sum(new_delta)+nominal)<1e-8);
    net_change=net_change+new_delta-removed;
    ledger(jj).from_bus_BS_delta_mvar=new_delta(f);ledger(jj).to_bus_BS_delta_mvar=new_delta(t);
    ledger(jj).policy='section_local_75pct_fixed_reactors_declared_synthetic_design';
    ledger(jj).distributed_bus_ids=ids(nodes)';ledger(jj).distributed_bus_BS_delta_mvar=new_delta(nodes)';
    ledger(jj).intermediate_compensation_is_synthetic=true;
    entries=[entries;struct('parent_row',parent,'runtime_branch_rows',rr', ...
        'section_count',numel(rr),'nominal_kV',m.bus(f,10),'total_rating_MVAr_at1pu',nominal, ...
        'bus_ids',ids(nodes)','removed_BS_MVAr_at1pu',removed(nodes)', ...
        'new_BS_MVAr_at1pu',new_delta(nodes)','net_BS_change_MVAr_at1pu',(new_delta(nodes)-removed(nodes))')]; %#ok<AGROW>
end
m.bus(:,6)=m.bus(:,6)+net_change;
all_delta=old_delta+net_change;
m.userdata.ac_sections.reactor_ledger=ledger;
% Preserve the original-bus view, and add an explicit full-axis view.
m.userdata.ac_sections.reactor_BS_delta=all_delta(1:original_count);
m.userdata.ac_sections.reactor_BS_delta_all_buses=all_delta;
m.userdata.ac_sections.reactor_BS_bus_ids=ids;
m.userdata.ac_sections.reactor_placement_schema_version=2;
assert(abs(sum(net_change))<1e-8&&max(abs((m.bus(:,6)-all_delta)-(old.bus(:,6)-old_delta)))<1e-10);
assert(isequaln(m.branch,old.branch)&&isequaln(m.gen,old.gen)&&isequaln(m.dcline,old.dcline));
assert(isequal(m.bus(:,[1:5,7:size(m.bus,2)]),old.bus(:,[1:5,7:size(m.bus,2)])));
assert(isequaln(m.userdata.ac_system,old.userdata.ac_system));
receipt=struct('schema_version',1,'parent_rows',[185,195],'fixed_fraction',.75, ...
    'selection_uses_interface_observations',false,'total_nominal_rating_changed',false, ...
    'branch_RXB_conductor_and_thermal_data_changed',false,'voltage_controls_or_limits_changed',false, ...
    'physical_installed_equipment_claimed',false,'passive_interior_nodes_preserved',true, ...
    'entries',entries,'net_BS_change_MVAr_at1pu',net_change,'original_reactor_ledger',sec.reactor_ledger);
m.userdata.physical_repair_185195=receipt;
end
