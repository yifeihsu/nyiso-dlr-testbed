function out=test_compact_npcc_asset_register
%TEST_COMPACT_NPCC_ASSET_REGISTER Analytic terminal-current and identity tests.
[b,a,m,v]=fixture;t=compact_npcc_asset_register(b,a,m,v);
names="all_NY_rows_and_stable_source_identity";passed=true;
assert(height(t)==3&&isequal(t.ny_branch_row,(1:3)')&&t.source_branch_row(1)==1391 ...
    && all(isnan(t.source_branch_row(2:3)))&&t.source_device_key(1)=="SOURCE:AC:1");
assert(abs(t.from_terminal_rms_amp(1)-100*1000/(sqrt(3)*1.02*345))<1e-10 ...
    && abs(t.to_terminal_rms_amp(1)-98*1000/(sqrt(3)*.98*345))<1e-10);
names(end+1)="three_phase_MVA_to_RMS_amp_includes_actual_VM";passed(end+1)=true;
assert(abs(t.from_terminal_rms_amp(2)-200*1000/(sqrt(3)*.98*345))<1e-10 ...
    && abs(t.to_terminal_rms_amp(2)-198*1000/(sqrt(3)*1.05*138))<1e-10 ...
    && t.to_terminal_rms_amp(2)>2*t.from_terminal_rms_amp(2));
names(end+1)="separate_HV_and_LV_terminal_voltage_bases";passed(end+1)=true;
assert(t.electrical_role(1)=="source_AC_branch_electrical_copy" ...
    && t.electrical_role(2)=="inherited_transformer_or_machine_connection_equivalent" ...
    && t.electrical_role(3)=="inherited_transformer_or_machine_connection_equivalent");
names(end+1)="source_AC_and_equivalent_transformer_roles_distinguished";passed(end+1)=true;
assert(~t.online(3)&&t.from_terminal_rms_amp(3)==0&&t.to_terminal_rms_amp(3)==0 ...
    && ~any(t.thermal_eligible)&&~any(t.dlr_eligible));
names(end+1)="offline_currents_zero_and_no_thermal_qualification";passed(end+1)=true;
assert(t.from_loading_percent(1)==50&&t.to_loading_percent(1)==49 ...
    && t.rate_a_mva(2)==300&&t.rate_b_mva(2)==400&&t.rate_c_mva(2)==500);
names(end+1)="static_ratings_and_both_end_loading_preserved";passed(end+1)=true;
% Reverse all branch orientations consistently. At each physical terminal,
% the reported current must remain the same, including unequal voltage bases.
r=m;r.branch(:,[1 2])=r.branch(:,[2 1]);br=b;br.full_candidate=r;
ar=a;ar.candidate=r;vr=v;vr.branch.from_bus=r.branch(:,1);vr.branch.to_bus=r.branch(:,2);
vr.branch.from_mva=v.branch.to_mva;vr.branch.to_mva=v.branch.from_mva;
q=compact_npcc_asset_register(br,ar,r,vr);
assert(max(abs(q.from_terminal_rms_amp-t.to_terminal_rms_amp))<1e-10 ...
    && max(abs(q.to_terminal_rms_amp-t.from_terminal_rms_amp))<1e-10);
names(end+1)="orientation_reversal_preserves_terminal_currents";passed(end+1)=true;
va=v;va.branch=va.branch([3 1 2],:);aa=a;aa.branch_map=aa.branch_map([2 3 1],:);
assert(isequaln(compact_npcc_asset_register(b,aa,m,va),t));
names(end+1)="maps_and_audit_join_by_identity_not_table_order";passed(end+1)=true;
bad=v;bad.branch.device_key(1)="WRONG";reject(@()compact_npcc_asset_register(b,a,m,bad),'KeyIdentity');
names(end+1)="wrong_audit_key_rejected";passed(end+1)=true;
bad=m;bad.bus(1,8)=0;reject(@()compact_npcc_asset_register(b,a,bad,v),'Voltage');
names(end+1)="active_zero_voltage_rejected";passed(end+1)=true;
bad=v;bad.branch.from_mva(3)=10;reject(@()compact_npcc_asset_register(b,a,m,bad),'AuditPower');
names(end+1)="offline_nonzero_audit_power_rejected";passed(end+1)=true;
bad=m;bad.branch(1,6)=100000;reject(@()compact_npcc_asset_register(b,a,bad,v),'FrozenHardware');
names(end+1)="altered_static_rating_rejected";passed(end+1)=true;
bad=m;bad.baseMVA=200;reject(@()compact_npcc_asset_register(b,a,bad,v),'FrozenHardware');
names(end+1)="altered_per_unit_MVA_base_rejected";passed(end+1)=true;
bad=v;bad.passed=false;q=compact_npcc_asset_register(b,a,m,bad);
assert(~any(q.power_flow_audit_passed)&&~any(q.thermal_eligible));
names(end+1)="diagnostic_audit_failure_remains_explicit";passed(end+1)=true;
out=struct('pass',all(passed),'assertion_groups',numel(passed), ...
    'gates',table(names(:),passed(:),'VariableNames',{'test','passed'}));disp(out.gates);
end

function [b,a,m,v]=fixture
m=struct('baseMVA',100,'success',true,'bus',zeros(4,13),'branch',zeros(3,13));
m.bus(:,1)=[101;102;103;104];m.bus(:,8)=[1.02;.98;1.05;1];m.bus(:,10)=[345;345;138;22];
m.branch(:,1:2)=[101 102;102 103;103 104];m.branch(:,3:5)=repmat([.01 .1 .05],3,1);
m.branch(:,6:8)=[200 250 300;300 400 500;150 200 250];m.branch(:,9)=[0;1.05;0];
m.branch(:,10)=[0;10;0];m.branch(:,11)=[1;1;0];m.branch(:,12:13)=repmat([-360 360],3,1);
keys=["SOURCE:AC:1";"NPCC:XFMR:2";"NPCC:MACHINE:3"];
p=table(1,1391,"SOURCE:AC:1","ac_branch_unresolved_line_cable_or_equivalent",651,902, ...
    'VariableNames',{'model_branch_row','source_branch_row','device_key','source_device_role','source_from_bus','source_to_bus'});
b=struct('full_candidate',m,'branch_keys',keys,'physical_branch_register',p);
a=struct('candidate',m,'branch_map',table((1:3)',(1:3)',keys, ...
    'VariableNames',{'model_branch_row','full_branch_row','branch_key'}));
v=struct('passed',true,'branch',table((1:3)',keys,m.branch(:,1),m.branch(:,2),logical(m.branch(:,11)), ...
    [100;200;0],[98;198;0],'VariableNames',{'branch_row','device_key','from_bus','to_bus','online','from_mva','to_mva'}));
end

function reject(fn,suffix)
id=['compact_asset:' suffix];
try,fn();catch err,assert(strcmp(err.identifier,id),'Unexpected error %s',err.identifier);return;end
error('compact_asset_test:MissingGuard','Expected %s.',id);
end
