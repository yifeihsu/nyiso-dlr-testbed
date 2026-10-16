function results = test_s13_phase1c_candidate
%TEST_S13_PHASE1C_CANDIDATE Nominal and adversarial source/role regressions.
b=build_s13_phase1c_candidate(struct('write_outputs',false,'verbose',false));
assert(b.validation.all_passed);
names=["source_resistance";"transformer_tap";"parent_row"; ...
    "false_promotion";"physical_zone";"missing_device_audit";"fabricated_circuit_id"];
rejected=false(size(names));
for k=1:numel(names)
    x=b;
    switch names(k)
        case "source_resistance",x.candidate.branch(263,3)=-0.01;
        case "transformer_tap",x.candidate.branch(270,9)=1.1;
        case "parent_row",x.candidate.branch(94,4)=0.1;
        case "false_promotion",x.candidate.userdata.s13.construction_source_qualified=true;
        case "physical_zone",x.candidate.userdata.nyiso_physical_zone{150}='H';
        case "missing_device_audit",x.phase1c_report.injection_audit.source_pd_mw(10)=0;
        case "fabricated_circuit_id",x.phase1c_report.branch_map.source_circuit_id(1)="1";
    end
    v=validate_s13_phase1c_candidate(x,struct('fail_on_error',false));
    rejected(k)=~v.all_passed;
end
assert(all(rejected),'test_s13_phase1c_candidate:Mutation','An invalid candidate passed.');
results=table(names,rejected);
% An analytic two-row fixture verifies receiving-terminal signs and losses;
% it is never exported or presented as a solved network snapshot.
fixture=b.candidate;fixture.success=true;fixture.branch(:,14:17)=0;
a=b.phase1c_report.branch_map;
ij=a.model_branch_row(a.source_branch_row==1236);
kj=a.model_branch_row(a.source_branch_row==1260);
fixture.branch(ij,14:17)=[-90 -9 100 10];
fixture.branch(kj,14:17)=[80 8 -78 -7.8];
flows=measure_s13_phase1c_flows(fixture);
assert(isequal(flows.received_mw,[0;90;-80;10]));
fixture.branch(:,[1 2])=fixture.branch(:,[2 1]);
fixture.branch(:,14:17)=fixture.branch(:,[16 17 14 15]);
assert(isequal(measure_s13_phase1c_flows(fixture),flows));
disp(results);
end
