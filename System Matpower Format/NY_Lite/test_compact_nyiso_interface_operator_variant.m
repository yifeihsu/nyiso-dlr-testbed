function tests=test_compact_nyiso_interface_operator_variant
%TEST_COMPACT_NYISO_INTERFACE_OPERATOR_VARIANT No target data or optimization.
b=apply_compact_2025_infrastructure(build_compact_npcc_corridors);
m=b.candidate;keys=b.branch_keys(b.ny_branch_mask);
m.bus=m.bus(b.ny_bus_mask,:);m.branch=m.branch(b.ny_branch_mask,:);
m.gen=m.gen(b.ny_generator_mask,:);m.gencost=m.gencost(b.ny_generator_mask,:);
m.bus_name=m.bus_name(b.ny_bus_mask);m.userdata.nyiso_physical_zone=m.userdata.nyiso_physical_zone(b.ny_bus_mask);
o=compact_nyiso_interface_operator_variant(m,keys);names=strings(0,1);
counts=arrayfun(@(k)nnz(o.from_coefficients(k,:)|o.to_coefficients(k,:)),(1:7)');
assert(isequal(counts,[3;4;3;5;6;6;6]));names(end+1)="current66bus_active_stable_membership_counts";
ix=find(keys=="NPCC_S7:BRANCH_ROW:73");
assert(all(o.from_coefficients([1;2],ix)==1));names(end+1)="Stolle_Meyer_A_C_bypass_in_both_western_interfaces";
ix=find(keys=="NPCC_S7:BRANCH_ROW:37");
assert(o.to_coefficients(5,ix)==1&&~o.to_coefficients(4,ix));
assert(~any(ismember(o.members.branch_key(o.members.interface_name=="Total_East_proxy"), ...
    ["NPCC_S7:BRANCH_ROW:34";"NPCC_S7:BRANCH_ROW:234"])));
names(end+1)="TotalEast_crosses_west_to_east_and_excludes_F_G_series_gate";
old=compact_nyiso_interface_operators(m,keys);
assert(isequal(old.from_coefficients([3 4 6 7],:),o.from_coefficients([3 4 6 7],:)) ...
    &&isequal(old.to_coefficients([3 4 6 7],:),o.to_coefficients([3 4 6 7],:)));
names(end+1)="unjustified_other_proxy_changes_not_introduced";
assert(~any(o.from_coefficients(:,m.branch(:,11)==0),'all')&&~any(o.to_coefficients(:,m.branch(:,11)==0),'all'));
assert(~any(contains(o.members.branch_key(o.members.interface_name=="UPNY_ConEd"),"897:902")));
names(end+1)="retired_rows_and_downstream_UPNY_series_paths_excluded";
% Arbitrary phasors test the actual AC metering and regional balance identity.
nb=size(m.bus,1);n=size(m.branch,1);mm=m;
[~,mm.branch(:,1)]=ismember(m.branch(:,1),m.bus(:,1));[~,mm.branch(:,2)]=ismember(m.branch(:,2),m.bus(:,1));
mm.bus(:,1)=(1:nb)';[Y,Yf,Yt]=makeYbus(mm.baseMVA,mm.bus,mm.branch);
V=(1+.015*sin((1:nb)')).*exp(1i*.04*cos((1:nb)'));
sf=V(mm.branch(:,1)).*conj(Yf*V)*mm.baseMVA;st=V(mm.branch(:,2)).*conj(Yt*V)*mm.baseMVA;
m.branch(:,14:17)=[real(sf),imag(sf),real(st),imag(st)];
flow=o.from_coefficients*m.branch(:,14)+o.to_coefficients*m.branch(:,16);
inj=real(V.*conj(Y*V))*mm.baseMVA;
err=0;
for k=find(o.registry.complete_NY_partition)'
    up=o.upstream_bus_mask(:,k);internal=up(mm.branch(:,1))&up(mm.branch(:,2));
    expected=sum(inj(up))-sum(real(sf(internal)+st(internal)))-sum(mm.bus(up,5).*abs(V(up)).^2);
    err=max(err,abs(expected-flow(k)));
end
assert(err<1e-8);names(end+1)="complete_partitions_obey_independent_AC_power_balance";
p=(n:-1:1)';mp=m;mp.branch=m.branch(p,:);op=compact_nyiso_interface_operator_variant(mp,keys(p));
fp=op.from_coefficients*mp.branch(:,14)+op.to_coefficients*mp.branch(:,16);
assert(max(abs(fp-flow))<1e-9);names(end+1)="branch_permutation_keeps_physical_members_and_flows";
mr=m;mr.branch(:,[1 2 14 15 16 17])=m.branch(:,[2 1 16 17 14 15]);
orr=compact_nyiso_interface_operator_variant(mr,keys);
fr=orr.from_coefficients*mr.branch(:,14)+orr.to_coefficients*mr.branch(:,16);
assert(max(abs(fr-flow))<1e-9);names(end+1)="reversal_uses_correct_terminal_without_loss_sign_error";
mb=m;mb.gen(:,2:3)=0;mb.bus(:,3:4)=0;mb.branch(:,14:17)=0;
ob=compact_nyiso_interface_operator_variant(mb,keys);
assert(isequal(ob,o));names(end+1)="operators_independent_of_dispatch_load_and_solved_flows";
assert(~o.public_operator_complete&&~any(o.registry.exact_public_operator)&&~o.targets_used_to_construct ...
    &&~o.boundary_offsets_inferred&&all(o.boundary_offset_mw==0)&&height(o.coverage_gaps)==7);
names(end+1)="public_gaps_and_unresolved_external_metering_remain_explicit";
bad=keys;bad(1)=bad(2);reject(@()compact_nyiso_interface_operator_variant(m,bad),'Keys');
names(end+1)="duplicate_stable_key_rejected";
bad=m;at=find(keys=="NPCC_S7:BRANCH_ROW:73");bad.branch(at,1)=61;
reject(@()compact_nyiso_interface_operator_variant(bad,keys),'AnchorEndpoint');
names(end+1)="critical_stable_key_with_wrong_physical_endpoint_rejected";
bad=m;at=find(keys=="PERFORM2019:AC:651:858:1");bad.branch(at,11)=0;
reject(@()compact_nyiso_interface_operator_variant(bad,keys),'InactiveAnchor');
names(end+1)="retired_required_UPNY_member_fails_closed";
bad=m;bad.userdata.nyiso_physical_zone{1}='NON_NY';
reject(@()compact_nyiso_interface_operator_variant(bad,keys),'Zones');
names(end+1)="unregistered_external_bus_zone_rejected";
tests=table(names(:),true(numel(names),1),'VariableNames',{'test','passed'});disp(tests);
end

function reject(fn,suffix)
id="compact_operator_variant:"+suffix;
try,fn();catch e,assert(string(e.identifier)==id,'Unexpected error %s instead of %s.',e.identifier,id);return;end
error('compact_operator_variant_test:MissingGuard','Expected %s.',id);
end
