function report = test_s14_external_equivalent
%TEST_S14_EXTERNAL_EQUIVALENT Source identity, injection accounting and freeze tests.
mpc=fixture;
source=runpf(mpc,mpoption('verbose',0,'out.all',0));
assert(source.success==1);
opts=struct('retention_options',struct('zone_map', ...
    table([10;20],["A";"J"],'VariableNames',{'bus_id','physical_zone'}), ...
    'overlay_bus_map',table(zeros(0,1),strings(0,1), ...
        'VariableNames',{'model_bus','physical_zone'}),'require_all_zones',false, ...
    'boundary_groups',table([30;40],["REGION";"REGION"], ...
        'VariableNames',{'bus_id','boundary_group'})));
a=build_s14_external_equivalent(source,opts);
assert(a.direct_passed&&all(a.direct_validation.passed));
assert(~isempty(a.eliminated_external_bus_ids));
assert(isequal(a.candidate.branch(1:3,1:13),source.branch(1:3,1:13)));
assert(sum(a.candidate.bus(:,3))==sum(source.bus(1:2,3)));
assert(size(a.candidate.gen,1)==1+height(a.injection_register));
assert(all(a.injection_register.p_min_mw==a.injection_register.p_max_mw));
assert(all(a.injection_register.q_min_mvar==a.injection_register.q_max_mvar));
assert(~a.promotion_eligible && ~a.public_target_fit_evaluated);
% Replay at the same fixed bounded dispatch with a new PF, independent of
% the builder's direct nodal check. No boundary source acts as REF or PV.
replay=runpf(a.candidate,mpoption('verbose',0,'out.all',0));
assert(replay.success==1);
assert(max(abs(replay.bus(:,8)-source.bus(a.retained_source_bus_rows,8)))<1e-7);
assert(all(replay.bus(ismember(replay.bus(:,1),a.injection_register.bus_id),2)==1));
names=["same_state_identity";"external_devices_mapped_once"; ...
    "fixed_bounded_external_PQ";"no_public_fit_or_promotion_claim";"independent_pf_replay"];
passed=true(size(names));values=zeros(size(names));
% A baseline-equivalent held-out load perturbation must not refit the matrix
% or external injections. Record its error; this synthetic test is not public
% target validation and establishes no full-network held-out qualification.
pert=source;pert.bus(2,3)=pert.bus(2,3)+1;
full_pert=runpf(pert,mpoption('verbose',0,'out.all',0));
red_pert=a.candidate;red_pert.bus(2,3)=red_pert.bus(2,3)+1;
red_pert=runpf(red_pert,mpoption('verbose',0,'out.all',0));
assert(full_pert.success==1&&red_pert.success==1);
error_vm=max(abs(red_pert.bus(1:2,8)-full_pert.bus(1:2,8)));
assert(error_vm<0.005);
names(end+1)="frozen_equivalent_heldout_1MW_voltage_error";passed(end+1)=true;values(end+1)=error_vm;
% Explicit source-scenario remapping reuses the frozen network, but is
% separately labelled and never substituted for the preceding held-out test.
opts.frozen_equivalent=a.frozen_equivalent;
b=build_s14_external_equivalent(full_pert,opts);
assert(isequal(a.frozen_equivalent.multiport_y,b.frozen_equivalent.multiport_y));
assert(b.direct_passed);
names(end+1)="scenario_remap_preserves_frozen_matrix";passed(end+1)=true;values(end+1)=0;
bad_options=opts;bad_options.frozen_equivalent.injection_map(1,1)= ...
    bad_options.frozen_equivalent.injection_map(1,1)+0.1;
expect_error(@()build_s14_external_equivalent(source,bad_options),'s14:FrozenEquivalentChanged');
names(end+1)="frozen_injection_map_tamper_rejected";passed(end+1)=true;values(end+1)=0;
bad_options=opts;bad_options.frozen_equivalent.equivalent_branches(1,4)= ...
    bad_options.frozen_equivalent.equivalent_branches(1,4)*1.1;
expect_error(@()build_s14_external_equivalent(source,bad_options),'s14:RealizationMismatch');
names(end+1)="frozen_realization_tamper_rejected";passed(end+1)=true;values(end+1)=0;
bad=source;bad.branch(4,4)=1.01*bad.branch(4,4);
bad=runpf(bad,mpoption('verbose',0,'out.all',0));
expect_error(@()build_s14_external_equivalent(bad,opts),'s14:FrozenNetworkChanged');
names(end+1)="network_mutation_rejected";passed(end+1)=true;values(end+1)=0;
bad=source;bad.bus(2,3)=bad.bus(2,3)+10;
expect_error(@()build_s14_external_equivalent(bad,opts),'s14:StateMismatch');
names(end+1)="false_solved_flag_rejected";passed(end+1)=true;values(end+1)=0;
bad=source;bad.userdata.s12_retained_source_bus=1;
expect_error(@()build_s14_external_equivalent(bad,opts),'s14:ForbiddenSource');
names(end+1)="oracle_provenance_rejected";passed(end+1)=true;values(end+1)=0;
bad=source;bad.dcline=[10 30 1 zeros(1,14)];
expect_error(@()build_s14_external_equivalent(bad,opts),'s14:ControlledFacilityRequiresMapping');
names(end+1)="unmapped_controlled_DC_rejected";passed(end+1)=true;values(end+1)=0;
% Tap-dependent negative-conductance synthesis must preserve native detail.
tapcase=mpc;tapcase.branch(4,9)=1.1;
tapcase=runpf(tapcase,mpoption('verbose',0,'out.all',0));
opts=rmfield(opts,'frozen_equivalent');
tapped=build_s14_external_equivalent(tapcase,opts);
assert(tapped.direct_passed);
assert(all(tapped.candidate.branch(:,3)>=0)&&all(tapped.candidate.bus(:,5)>=0));
names(end+1)="tap_case_passive_realization";passed(end+1)=true;values(end+1)=0;
bad=source;isolated=source.bus(1,:);isolated(1)=70;isolated(2)=4;isolated(3:6)=0;
bad.bus=[bad.bus;isolated];
expect_error(@()build_s14_external_equivalent(bad,opts),'s14:IllConditionedExternalBlock');
names(end+1)="singular_external_block_rejected";passed(end+1)=true;values(end+1)=0;
bad_options=opts;bad_options.retention_options.require_all_zones=true;
expect_error(@()build_s14_external_equivalent(source,bad_options),'s14:ZoneCoverage');
names(end+1)="missing_NY_zone_coverage_rejected";passed(end+1)=true;values(end+1)=0;
iface=table("synthetic_NY_interface",1,1,'VariableNames', ...
    {'interface_name','model_branch_row','operator_sign'});
validation=validate_s14_against_s13_full(source,a,struct('interface_map',iface));
assert(validation.passed&&~validation.public_target_fit_evaluated&&~validation.promotion_eligible);
names(end+1)="independent_direct_source_gate_replay";passed(end+1)=true;values(end+1)=0;
assert(validation.reduction_metrics_passed && ...
    any(validation.required_reduction_metrics=="registered_interface_max_error_mw"));
missing_operator=validate_s14_against_s13_full(source,a);
interface_gate=missing_operator.gates.metric=="registered_interface_max_error_mw";
assert(~missing_operator.reduction_metrics_passed && ~missing_operator.gates.passed(interface_gate) && ...
    missing_operator.gates.status(interface_gate)=="unavailable_no_registered_operator");
names(end+1)="missing_interface_blocks_named_reduction_gate";passed(end+1)=true;values(end+1)=0;
bad=source;bad.gen(2,[4 5])=[Inf -Inf];
unbounded=build_s14_external_equivalent(bad,opts);
checked=validate_s14_against_s13_full(bad,unbounded);
assert(~checked.source_and_candidate_capability_passed);
names(end+1)="unbounded_eliminated_source_not_qualified";passed(end+1)=true;values(end+1)=0;
bad=source;bad.bus(2,13)=bad.bus(2,8)+0.01;
invalid_voltage=build_s14_external_equivalent(bad,opts);
checked=validate_s14_against_s13_full(bad,invalid_voltage);
assert(~checked.passed && checked.gates.value(11)>0);
names(end+1)="absolute_voltage_violation_not_qualified";passed(end+1)=true;values(end+1)=0;
report=table(names(:),values(:),passed(:),'VariableNames',{'test','value','passed'});
disp(report);
end

function mpc=fixture
ids=[10;20;30;40;50;60];n=numel(ids);
bus=zeros(n,13);bus(:,1)=ids;bus(:,2)=1;bus(1,2)=3;bus(6,2)=2;
bus(:,7)=1;bus(:,8)=1;bus(:,10)=345;bus(:,11)=1;bus(:,12)=1.1;bus(:,13)=0.9;
bus(:,3)=[0;100;0;20;25;0];bus(:,4)=[0;30;0;10;5;0];bus(3,5)=1;
gen=zeros(3,21);gen(:,1)=[10;60;30];gen(:,2)=[70;70;5];
gen(:,4)=200;gen(:,5)=-200;gen(:,6)=1;gen(:,7)=100;gen(:,8)=1;
gen(:,9)=200;gen(:,10)=0;
branch=zeros(6,13);branch(:,1:2)=[10 20;20 30;10 40;30 50;40 50;50 60];
branch(:,3)=0.01;branch(:,4)=0.1;branch(:,6:8)=500;branch(:,11)=1;
branch(:,12)=-360;branch(:,13)=360;
mpc=struct('version','2','baseMVA',100,'bus',bus,'gen',gen,'branch',branch, ...
    'gencost',repmat([2 0 0 2 10 0],3,1), ...
    'userdata',struct('s13',struct('status','synthetic_npcc_contract_test')));
end

function expect_error(action,identifier)
try,action();catch e,assert(strcmp(e.identifier,identifier), ...
        'Expected %s, got %s: %s',identifier,e.identifier,e.message);return;end
error('Expected rejection %s did not occur.',identifier);
end
