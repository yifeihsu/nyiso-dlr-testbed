function cache=load_profile_cache()
% Read frozen annual inputs once; physical topology templates remain unchanged.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
cache.dispatch=load(fullfile(root,'output','nygrid_2025_dispatch','dispatch','dispatch.mat'), ...
    'hour_index','timestamp_utc','bus_pd','bus_qd','dc_pf','reference_bus','gamma');
cache.bounds=load(fullfile(root,'output','nygrid_2025_dispatch','dispatch','dispatch_bounds.mat'),'gen_pmin','gen_pmax','hour_index');
cache.western=load(fullfile(root,'output','nygrid_2025_western_audit','dispatch','all_boundary_actual_dispatch.mat'), ...
    'hour_index','timestamp_utc','gen_pg','qualified','gamma','original_four_dc_pf','P34_control_targets_model_mw');
cache.network=load(fullfile(root,'output','nygrid_2025_western_audit','replay','dated_combined.mat'), ...
    'hour_index','timestamp_utc','qualified','network_state_ids','corrected_generator_buses');
cache.dover=load(fullfile(root,'output','nygrid_2025_dover_parameters','replay','operating_states.mat'), ...
    'hour_index','timestamp_utc','qualified','post_full_service','controls','gamma');
axes={cache.dispatch.hour_index,cache.bounds.hour_index,cache.western.hour_index,cache.network.hour_index,cache.dover.hour_index};
for k=1:numel(axes),assert(isequal(double(axes{k}(:)),(1:8760)'));end
assert(isequal(string(cache.dispatch.timestamp_utc(:)),string(cache.western.timestamp_utc(:)),string(cache.network.timestamp_utc(:)),string(cache.dover.timestamp_utc(:))));
assert(cache.dispatch.gamma==cache.western.gamma&&cache.dispatch.gamma==cache.dover.gamma);
assert(isequaln(cache.dispatch.dc_pf,cache.western.original_four_dc_pf));
cache.qualified=logical(cache.dover.qualified(:));assert(nnz(cache.qualified)==8651);
assert(all(cache.western.qualified(cache.qualified))&&all(cache.network.qualified(cache.qualified)));
cache.state_names=unique(string(cache.network.network_state_ids(:)),'stable');assert(numel(cache.state_names)==4);
[ok,cache.state_index]=ismember(string(cache.network.network_state_ids(:)),cache.state_names);assert(all(ok));
cache.templates=cell(4,1);cache.generator_bus_index=cell(4,1);cache.template_hours=zeros(4,1);
for k=1:4
    h=find(cache.qualified&cache.state_index==k,1,'first');cache.template_hours(k)=h;
    m=npcc_nygrid_2025_ac(h);assert(isequal(m.bus(1:140,1),(1:140)'));
    assert(isequal(m.gen(:,1),double(cache.network.corrected_generator_buses(:))));
    cache.templates{k}=m;
    [ok,cache.generator_bus_index{k}]=ismember(m.gen(:,1),m.bus(:,1));assert(all(ok));
end
cache.external=cache.templates{1}.userdata.ac_system.external_generator_mask;
cache.external_capacity=cache.templates{1}.userdata.ac_system.generator_capability_reference(cache.external);
cache.canonical=cache.templates{4};
for k=1:4
    assert(all(ismember(cache.templates{k}.bus(:,1),cache.canonical.bus(:,1))));
    assert(all(ismember(string(cache.templates{k}.userdata.ac_system.branch_keys),string(cache.canonical.userdata.ac_system.branch_keys))));
end
end
