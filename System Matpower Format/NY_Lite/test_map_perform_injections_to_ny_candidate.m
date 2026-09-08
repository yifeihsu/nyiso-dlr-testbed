function out=test_map_perform_injections_to_ny_candidate(n,foundation)
%TEST_MAP_PERFORM_INJECTIONS_TO_NY_CANDIDATE Real-source replacement guards.
if nargin<1,n=normalize_perform_ny_source;end
if nargin<2
    root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
    foundation=load(fullfile(root,'output','ny_only_package_a','ny_foundation_reference.mat'));
end
c=n.source;c.userdata.nyiso_physical_zone=n.bus_inventory.source_zone;
map=table(c.bus(:,1),c.bus(:,1),repmat("exact_source_identity",size(c.bus,1),1), ...
    'VariableNames',{'source_bus','model_bus','mapping_kind'});
options=struct('source_bus_map',map);
a=map_perform_injections_to_ny_candidate(c,n,foundation,options);
assert(a.conservation_error_max<1e-8&&size(a.candidate.gen,1)==595&&height(a.boundary_register)==20);
assert(isequal(a.candidate.bus(:,3:6),foundation.mpc.bus(:,3:6)) && isequal(a.candidate.branch,c.branch));
assert(nnz(startsWith(a.generator_map.source_device_role,"native_"))==594 && ...
    nnz(a.generator_map.source_device_role=="assumed_reactive_support")==1 && ...
    ~any(contains(a.generator_keys,":RF")) && ~any(contains(a.generator_keys,":QS")));
assert(isequal(a.candidate.gen(:,[8 9 10 4 5]),foundation.mpc.gen(:,[8 9 10 4 5])));
assert(height(a.shunt_register)==34 && abs(sum(a.candidate.bus(:,6))-1035.9)<1e-8);
assert(height(a.retired_legacy_generators)==615 && height(a.retired_legacy_bus_injections)==1576);
assert(~a.electrical_baseline_qualified && ~a.dlr_ready && a.mapping_only);

% Nonidentity aggregation relocates every source device family together.
% One retained terminal per zone makes double-counting conspicuous.
z=n.bus_inventory.source_zone;targets=zeros(11,1);
for k=1:11,targets(k)=find(z==string(char('A'+k-1)),1);end
agg=c;agg.bus=c.bus(targets,:);agg.bus_name=c.bus_name(targets);
agg.userdata.nyiso_physical_zone=z(targets);agg.branch=zeros(0,size(c.branch,2));
agg.gen=c.gen(1:2,:);agg.gen(:,1)=agg.bus(1,1);
agg.bus(:,3:6)=12345; % All old injections must be discarded, never added.
amap=map;
for k=1:11,amap.model_bus(z==string(char('A'+k-1)))=agg.bus(k,1);end
amap.mapping_kind(:)="assumed_same_zone_aggregation";
ag=map_perform_injections_to_ny_candidate(agg,n,foundation,struct('source_bus_map',amap));
assert(ag.conservation_error_max<1e-8 && height(ag.model_bus_ledger)==11 && ...
    abs(sum(ag.model_bus_ledger.pd_gross_mw)-sum(n.source.bus(:,3)))<1e-8);
assert(all(ag.generator_map.model_bus==amap.model_bus(ismember_row(ag.generator_map.source_bus,map.source_bus))));
assert(all(ag.boundary_register.model_bus==amap.model_bus(ismember_row(ag.boundary_register.source_bus,map.source_bus))));
assert(all(ag.shunt_register.model_bus==amap.model_bus(ismember_row(ag.shunt_register.source_bus,map.source_bus))));
assert(numel(unique(ag.control_map.mapped_vg_pu(ag.control_map.model_bus==ag.reference_bus & ag.control_map.status>0)))==1);

bad=options;bad.source_bus_map(1,:)=[];
reject(@()map_perform_injections_to_ny_candidate(c,n,foundation,bad),'ny_injection_map:MapCoverage');
bad=options;bad.source_bus_map.source_bus(2)=bad.source_bus_map.source_bus(1);
reject(@()map_perform_injections_to_ny_candidate(c,n,foundation,bad),'ny_injection_map:MapCoverage');
bad=options;bad.source_bus_map.model_bus(1)=999999;
reject(@()map_perform_injections_to_ny_candidate(c,n,foundation,bad),'ny_injection_map:MapTarget');
bad=options;different=find(z~=z(1),1);bad.source_bus_map.model_bus(1)=c.bus(different,1);
reject(@()map_perform_injections_to_ny_candidate(c,n,foundation,bad),'ny_injection_map:Zone');
bad=foundation;bad.mpc.gen(1,9)=bad.mpc.gen(1,9)+1;
reject(@()map_perform_injections_to_ny_candidate(c,n,bad,options),'ny_injection_map:NativeBounds');
bad=foundation;bad.mpc.gen(end,4)=9900;
reject(@()map_perform_injections_to_ny_candidate(c,n,bad,options),'ny_injection_map:Support');
bad=foundation;bad.gross_boundary_ledger.pd_gross_mw(1)=bad.gross_boundary_ledger.pd_gross_mw(1)+1;
reject(@()map_perform_injections_to_ny_candidate(c,n,bad,options),'ny_injection_map:FoundationLedger');
reject(@()map_perform_injections_to_ny_candidate(a.candidate,n,foundation,options),'ny_injection_map:AlreadyApplied');
out=struct('pass',true,'test_count',20,'native_records',594,'boundary_records',20,'support_records',1);
end

function rows=ismember_row(ids,all_ids)
[found,rows]=ismember(ids,all_ids);assert(all(found));
end
function reject(f,id)
try,f();catch e,assert(strcmp(e.identifier,id),'Unexpected error: %s',e.identifier);return;end
error('test_map_perform_injections_to_ny_candidate:MissedGuard','Expected rejection %s',id);
end
