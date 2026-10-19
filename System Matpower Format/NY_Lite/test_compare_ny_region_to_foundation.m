function out=test_compare_ny_region_to_foundation
%TEST_COMPARE_NY_REGION_TO_FOUNDATION Response, phase-frame and current units.
define_constants;
[build,regional,foundation]=fixture;
c=compare_ny_region_to_foundation(build,regional,foundation);
assert(c.summary.exact_bus_count==8&&c.summary.copied_branch_count==10 && ...
    c.summary.active_copied_branch_count==9&&c.summary.inactive_copied_branch_count==1);
assert(c.summary.voltage_max_abs_delta_pu==0 && c.summary.angle_max_abs_delta_deg<1e-12 && ...
    c.summary.terminal_p_max_abs_delta_mw<1e-10 && c.summary.terminal_current_max_abs_delta_ka<1e-12);
assert(~c.qualification_assessed&&~c.response_equivalence_assessed&&~c.stored_terminal_flows_used&&~c.dlr_ready);

% Absolute angle origins can differ; all physical response quantities and
% aligned voltage angles must be invariant to a uniform rotation.
shift=regional;shift.bus(:,VA)=shift.bus(:,VA)+127.5;
x=compare_ny_region_to_foundation(build,shift,foundation);
assert(x.summary.angle_max_abs_delta_deg<1e-12&&x.summary.terminal_p_max_abs_delta_mw<1e-9);

% Bogus saved power columns cannot change a recomputed response comparison.
stale=regional;stale.branch(:,PF:QT)=987654321;
x=compare_ny_region_to_foundation(build,stale,foundation);
assert(isequaln(x.source_branch_comparison,c.source_branch_comparison));

% Verify independent three-phase units at the different-kV ends of a
% transformer, using P/Q and actual terminal voltage as a separate formula.
t=c.source_branch_comparison;r=1;
vfrom=foundation.bus(foundation.bus(:,BUS_I)==t.source_from_bus(r),VM);
vto=foundation.bus(foundation.bus(:,BUS_I)==t.source_to_bus(r),VM);
expected_from=hypot(t.source_p_from_mw(r),t.source_q_from_mvar(r))/(sqrt(3)*t.from_base_kv(r)*vfrom);
expected_to=hypot(t.source_p_to_mw(r),t.source_q_to_mvar(r))/(sqrt(3)*t.to_base_kv(r)*vto);
assert(abs(t.source_i_from_ka(r)-expected_from)<1e-12&&abs(t.source_i_to_ka(r)-expected_to)<1e-12 && ...
    abs(t.source_i_from_ka(r)-t.source_i_to_ka(r))>.1);
assert(all(t{~t.online,startsWith(t.Properties.VariableNames,'source_p_')|startsWith(t.Properties.VariableNames,'source_q_')|startsWith(t.Properties.VariableNames,'source_i_')}==0,'all'));

% A different solved load scenario has an actual response difference despite
% unchanged network hardware. It must not collapse to common-phasor identity.
changed=regional;changed.bus(5,PD)=changed.bus(5,PD)+10;
changed=runpf(changed,mpoption('verbose',0,'out.all',0,'pf.tol',1e-11));assert(changed.success);
x=compare_ny_region_to_foundation(build,changed,foundation);
assert(x.summary.voltage_max_abs_delta_pu>1e-5&&x.summary.terminal_p_max_abs_delta_mw>1);
assert(x.summary.terminal_current_max_abs_delta_ka>1e-4&&~x.response_equivalence_assessed);

bad=regional;bad.branch(1,BR_X)=bad.branch(1,BR_X)+.01;
reject(@()compare_ny_region_to_foundation(build,bad,foundation),'ny_response:BranchHardware');
bad=regional;bad.bus(1,BASE_KV)=69;
reject(@()compare_ny_region_to_foundation(build,bad,foundation),'ny_response:VoltageBase');
bad=regional;bad.bus(:,BUS_TYPE)=PQ;bad.bus(2,BUS_TYPE)=REF;
reject(@()compare_ny_region_to_foundation(build,bad,foundation),'ny_response:Reference');
bad=build;bad.source_branch_map.device_key(1)="other_identity";
reject(@()compare_ny_region_to_foundation(bad,regional,foundation),'ny_response:BranchIdentity');
bad=regional;bad.success=false;
reject(@()compare_ny_region_to_foundation(build,bad,foundation),'ny_response:Unsolved');
out=struct('pass',true,'test_count',14,'comparison_assigns_qualification',false);
end

function [b,r,s]=fixture
define_constants;s=case9;s.bus(1,BASE_KV)=13.8;
ids=s.bus(:,BUS_I);ids(1)=847;
s.gen(:,GEN_BUS)=ids(s.gen(:,GEN_BUS));s.branch(:,[F_BUS T_BUS])=ids(s.branch(:,[F_BUS T_BUS]));s.bus(:,BUS_I)=ids;
s.branch(end+1,:)=s.branch(1,:);s.branch(end,BR_STATUS)=0;
s=runpf(s,mpoption('verbose',0,'out.all',0,'pf.tol',1e-11));assert(s.success);
mapped=ids+20000;r=s;r.bus(:,BUS_I)=mapped;
[~,j]=ismember(r.gen(:,GEN_BUS),ids);r.gen(:,GEN_BUS)=mapped(j);
[~,j]=ismember(r.branch(:,F_BUS),ids);r.branch(:,F_BUS)=mapped(j);
[~,j]=ismember(r.branch(:,T_BUS),ids);r.branch(:,T_BUS)=mapped(j);
kind=repmat("exact_source_region",9,1);kind(5)="assumed_same_zone_aggregation";
bm=table(ids,mapped,kind,'VariableNames',{'source_bus','model_bus','mapping_kind'});
keys="TEST:BRANCH:"+string((1:10)');roles=repmat("ac_branch_unresolved_line_cable_or_equivalent",10,1);roles(1)="two_winding_transformer";
em=table((1:10)',(1:10)',keys,'VariableNames',{'source_branch_row','model_branch_row','device_key'});
branches=table((1:10)',keys,roles,repmat("1",10,1),repmat("fixture_explicit_identity",10,1),true(10,1), ...
    'VariableNames',{'source_branch_row','device_key','source_device_role','raw_circuit_id','identity_confidence','individual_circuit_identity_resolved'});
buses=table(ids,"TEST:BUS:"+string(ids),'VariableNames',{'source_bus','device_key'});
b=struct('source_bus_map',bm,'source_branch_map',em,'region_source_buses',ids(kind=="exact_source_region"), ...
    'source_inventory',struct('bus_inventory',buses,'branch_inventory',branches));
end

function reject(f,id)
try,f();catch e,assert(strcmp(e.identifier,id),'Unexpected error: %s',e.identifier);return;end
error('test_compare_ny_region_to_foundation:MissedGuard','Expected rejection %s',id);
end
