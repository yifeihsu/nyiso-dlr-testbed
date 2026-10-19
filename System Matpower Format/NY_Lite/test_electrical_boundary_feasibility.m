function report=test_electrical_boundary_feasibility
%TEST_ELECTRICAL_BOUNDARY_FEASIBILITY Reject only justified aggregate shortages.
m=struct('version','2','baseMVA',100);
m.bus=zeros(4,13);m.bus(:,1)=[10;20;30;40];m.bus(:,2)=1;
m.bus(:,3)=[0;100;120;0];m.bus(:,10)=345;
m.gen=zeros(2,21);m.gen(:,1)=[20;30];m.gen(:,8)=1;m.gen(:,9)=[80;100];
m.branch=zeros(3,13);m.branch(:,1:2)=[10 20;30 10;20 30];m.branch(:,3)=0.01;m.branch(:,11)=1;
% Bus 40 is explicitly out of service and contributes no external component.
m.bus(4,2)=4;
Af=sparse([-1 0 0;0 0 0]);At=sparse([0 0 0;0 -1 0]);
inputs=struct('candidate',m,'controls',struct('operator_from',Af,'operator_to',At, ...
    'target_mw',[20;30],'tolerance_mw',[5;5]),'regional_names',["HQ";"ONTARIO"]);
opts=struct('ny_bus_ids',10);
a=audit_electrical_boundary_feasibility(inputs,opts);
assert(height(a.components)==1&&a.provably_infeasible);
assert(a.components.required_min_generation_mw==260&&a.components.generation_shortage_mw==80);
assert(a.components.control_groups=="HQ;ONTARIO");
assert(~a.ac_feasibility_established);
names=["connected_regions_aggregated_once";"tolerance_lower_bound_applied";"shortage_proves_infeasibility"];
bad=inputs;bad.controls.operator_to(2,2)=0;
b=audit_electrical_boundary_feasibility(bad,opts);
assert(~b.provably_infeasible&&~b.all_components_certified);
names(end+1)="uncontrolled_tie_blocks_certificate";
bad=inputs;bad.controls.operator_from(2,1)=-1;
b=audit_electrical_boundary_feasibility(bad,opts);
assert(~b.provably_infeasible&&~b.all_components_certified);
names(end+1)="overlapping_groups_block_certificate";
bad=inputs;bad.controls.operator_from(2,2)=-1;bad.controls.operator_to(2,2)=0;
b=audit_electrical_boundary_feasibility(bad,opts);
assert(~b.provably_infeasible&&~b.all_components_certified);
names(end+1)="wrong_measurement_terminal_blocks_certificate";
bad=inputs;bad.candidate.branch(3,3)=-0.01;
b=audit_electrical_boundary_feasibility(bad,opts);
assert(~b.provably_infeasible&&~b.all_components_certified);
names(end+1)="negative_loss_element_blocks_certificate";
bad=inputs;bad.candidate.gen(:,9)=500;
b=audit_electrical_boundary_feasibility(bad,opts);
assert(~b.provably_infeasible&&b.necessary_conditions_passed&&~b.ac_feasibility_established);
names(end+1)="adequate_capacity_does_not_claim_AC_feasibility";
% One group spanning two electrically disconnected external areas cannot
% support separate component certificates without an allocation constraint.
bad=inputs;bad.candidate.branch(3,11)=0;
bad.controls.operator_from=Af(1,:);bad.controls.operator_to=At(2,:);
bad.controls.target_mw=50;bad.controls.tolerance_mw=10;bad.regional_names="COMBINED";
b=audit_electrical_boundary_feasibility(bad,opts);
assert(~b.provably_infeasible&&~b.all_components_certified);
names(end+1)="group_spanning_components_blocks_certificate";
bad=inputs;bad.candidate.dcline=[20 10 1 zeros(1,14)];
b=audit_electrical_boundary_feasibility(bad,opts);
assert(~b.provably_infeasible&&~b.all_components_certified);
names(end+1)="unmapped_DC_blocks_certificate";
report=table(names(:),true(numel(names),1),'VariableNames',{'test','passed'});disp(report);
end
