function out=test_compact_2025_infrastructure(base)
%TEST_COMPACT_2025_INFRASTRUCTURE Accounting, provenance and sensitivity gates.
if nargin<1,base=build_compact_npcc_corridors();end
o=apply_compact_2025_infrastructure(base);m=o.candidate;s=o.infrastructure_branch_register;
names="construction_validation";passed=o.infrastructure_validation.pass;assert(passed);
assert(size(m.bus,1)==160&&sum(o.ny_bus_mask)==66&&size(m.branch,1)==290 ...
    && sum(o.ny_branch_mask)==125&&sum(o.ny_branch_mask&m.branch(:,11)>0)==112);
names(end+1)="bounded_expansion_counts_66_NY_buses";passed(end+1)=true;
assert(isequal(m.bus(1:145,:),base.candidate.bus)&&all(m.bus(146:end,3:6)==0,'all') ...
    && isequal(m.gen,base.candidate.gen)&&isequal(m.gencost,base.candidate.gencost));
names(end+1)="parent_load_generation_shunt_and_capability_conservation";passed(end+1)=true;
assert(isequal(o.generator_keys,base.generator_keys)&&isequal(o.branch_keys(1:257),base.branch_keys) ...
    && isequal(m.branch(247:257,:),base.candidate.branch(247:257,:)));
names(end+1)="all_original_source_circuits_and_keys_preserved";passed(end+1)=true;
rr=o.branch_dispositions.parent_branch_row;expected=base.candidate.branch;expected(rr,11)=0;
assert(numel(rr)==8&&numel(unique(rr))==8&&all(m.branch(rr,11)==0) ...
    && isequal(m.branch(1:257,:),expected)&&all(strlength(o.branch_dispositions.replacement_branch_keys)>0));
names(end+1)="all_replaced_equivalents_retired_exactly_once";passed(end+1)=true;
sp=s(s.project_id=="SMART_PATH",:);
assert(height(sp)==4&&all(sp.from_base_kv==230&sp.to_base_kv==230) ...
    && abs(sp.r_pu(1)-.85*.0136)<1e-14&&sp.x_pu(1)==.10931&&sp.b_pu(1)==.41705 ...
    && sp.rate_a_mva(1)==575&&sp.r_pu(3)==.00815);
names(end+1)="SmartPath230_template_and_rebuild_assumption_explicit";passed(end+1)=true;
assert(all(~o.project_register.included(ismember(o.project_register.project_id, ...
    ["CHPE","SMART_PATH_CONNECT","RCC_LONG_ISLAND_CITY","PROPEL_NY"]))) ...
    && all(o.project_register.cutoff=="2025-12-31"));
names(end+1)="2026_and2030_projects_excluded_from2025";passed(end+1)=true;
cross=s.from_base_kv~=s.to_base_kv;
assert(all(s.tap(cross)==1)&&all(s.shift_degree==0)&&all(s.base_mva==100) ...
    && all(m.branch(258:end,12)==-360&m.branch(258:end,13)==360));
names(end+1)="coherent_nominal_voltage_bases_and_fixed_PAR_controls";passed(end+1)=true;
assert(all(~s.thermal_eligible&~s.dlr_eligible&~s.parameter_ground_truth_verified) ...
    && all(~o.project_register.as_built_parameters_verified));
names(end+1)="no_thermal_or_as_built_parameter_claim";passed(end+1)=true;
% Check complex admittance passivity branch by branch, including transformer
% nominal ratios. Positive charging does not create negative real conductance.
e=ext2int(m);bus=e.bus;bus(:,5:6)=0;br=e.branch;br(:,11)=0;
selected=e.order.branch.status.on>257;
assert(nnz(selected)==height(s));br(selected,11)=e.branch(selected,11);
y=full(makeYbus(e.baseMVA,bus,br));
assert(min(real(eig((y+y')/2)))>-1e-9);
names(end+1)="new_branch_admittance_real_part_passive";passed(end+1)=true;
% Source sheets contain planning futures; keep exact historical row identities
% and a byte hash so numerical template provenance remains reproducible.
t=o.historical_template_register;
assert(height(t)==7&&t.source_key(1)=="800_1233_1"&&t.xlsx_row(1)==1945 ...
    && t.xlsx_row(2)==573&&t.source_key(7)=="1493_601_1" ...
    && strlength(o.infrastructure_source_manifest.sha256)==64);
names(end+1)="historical_workbook_stable_keys_rows_and_hash";passed(end+1)=true;
for k=[95 240 97 239]
    part=s(s.parent_row==k,:);assert(height(part)==2);
    assert(max(abs(sum([part.r_pu part.x_pu part.b_pu],1)-base.candidate.branch(k,3:5)))<1e-14);
    assert(all(part.rate_a_mva==base.candidate.branch(k,6)));
end
names(end+1)="NYC_delivery_split_series_budgets_and_limits_conserved";passed(end+1)=true;
zones=string(m.userdata.nyiso_physical_zone);[found,j]=ismember(o.bus_map_2025.model_bus,m.bus(:,1));
assert(all(found)&&isequal(zones(j),o.bus_map_2025.physical_zone));
names(end+1)="added_bus_zones_match_bus_row_order";passed(end+1)=true;
oldcut=xor(ismember(base.candidate.branch(:,1),base.ny_bus_ids),ismember(base.candidate.branch(:,2),base.ny_bus_ids));
newcut=xor(ismember(m.branch(:,1),o.ny_bus_ids),ismember(m.branch(:,2),o.ny_bus_ids));
assert(isequal(find(oldcut),find(newcut))&&isequal(m.branch(newcut,:),base.candidate.branch(oldcut,:)));
names(end+1)="external_boundary_ports_and_branches_unchanged";passed(end+1)=true;
low=apply_compact_2025_infrastructure(base,struct('impedance_scale',.75,'charging_scale',0,'rating_scale',.8));
q=low.infrastructure_branch_register;sel=s.sensitivity_required;
assert(max(abs(q.r_pu(sel)-.75*s.r_pu(sel)))<1e-14&&all(q.b_pu(sel)==0) ...
    && max(abs(q.rate_a_mva(sel)-.8*s.rate_a_mva(sel)))<1e-10 ...
    && isequal(q.r_pu(~sel),s.r_pu(~sel))&&isequal(low.candidate.branch(1:257,:),m.branch(1:257,:)));
names(end+1)="sensitivity_only_changes_declared_new_assumptions";passed(end+1)=true;
off=apply_compact_2025_infrastructure(base,struct('include_announced_2025_rcc',false));
q=off.infrastructure_branch_register;k=ismember(q.branch_key,["NY2025:RCC_BROOKLYN:CABLE","NY2025:RCC_STATEN:CABLE"]);
assert(nnz(k)==2&&all(q.status(k)==0)&&nnz(q.status==0)==2 ...
    && ~any(off.project_register.included(ismember(off.project_register.project_id,["RCC_BROOKLYN","RCC_STATEN"]))));
names(end+1)="announced2025_cable_transfer_paths_can_be_excluded";passed(end+1)=true;
reject(@()apply_compact_2025_infrastructure(o),'AlreadyApplied');
names(end+1)="double_application_rejected";passed(end+1)=true;
reject(@()apply_compact_2025_infrastructure(base,struct('cutoff','2026-12-31')),'Cutoff');
names(end+1)="wrong_snapshot_cutoff_rejected";passed(end+1)=true;
reject(@()apply_compact_2025_infrastructure(base,struct('impedance_scale',0)),'SensitivityBounds');
reject(@()apply_compact_2025_infrastructure(base,struct('charging_scale',2)),'SensitivityBounds');
reject(@()apply_compact_2025_infrastructure(base,struct('rating_scale',100)),'SensitivityBounds');
names(end+1)="unbounded_or_nonphysical_sensitivity_rejected";passed(end+1)=true;
bad=base;bad.candidate.branch(36,1)=38;bad.full_candidate=bad.candidate;
reject(@()apply_compact_2025_infrastructure(bad),'RetirementIdentity');
names(end+1)="wrong_predecessor_identity_rejected";passed(end+1)=true;
out=struct('pass',all(passed),'assertion_groups',numel(passed), ...
    'gates',table(names(:),passed(:),'VariableNames',{'test','passed'}));disp(out.gates);
end

function reject(fn,suffix)
id=['compact_2025:' suffix];
try,fn();catch err,assert(strcmp(err.identifier,id),'Unexpected error %s',err.identifier);return;end
error('compact_2025_test:MissingGuard','Expected %s.',id);
end
