function tests=test_extract_compact_ny_boundary
%TEST_EXTRACT_COMPACT_NY_BOUNDARY Independent cut signs, accounting and replay.
define_constants;m=loadcase('case9');ids=[42;100;101;43;44;45;102;103;104];
m.bus(:,BUS_I)=ids;m.gen(:,GEN_BUS)=ids(m.gen(:,GEN_BUS));
m.branch(:,F_BUS)=ids(m.branch(:,F_BUS));m.branch(:,T_BUS)=ids(m.branch(:,T_BUS));
m.bus_name=cellstr("fixture_"+string(ids));ny=ismember(ids,[42;43;44;45]);
zones=repmat("outside_NY",9,1);zones(ny)="F";m.userdata.nyiso_physical_zone=cellstr(zones);
b=struct('full_candidate',m,'ny_bus_mask',ny,'ny_bus_ids',ids(ny), ...
    'generator_keys',"GEN:"+string((1:3)'),'branch_keys',"BRANCH:"+string((1:9)'));
f=runpf(m,mpoption('verbose',0,'out.all',0,'pf.tol',1e-10));
a=extract_compact_ny_boundary(f,b);c=a.candidate;
p=runpf(c,mpoption('verbose',0,'out.all',0,'pf.enforce_q_lims',1,'pf.tol',1e-10));
v=audit_ny_ac_reference(p);
assert(p.success&&v.passed&&max(abs(p.bus(:,VM)-f.bus(ny,VM)))<1e-9);
assert(max(abs(p.gen(:,PG)-f.gen(ismember(f.gen(:,GEN_BUS),ids(ny)),PG)))<1e-7);
names="cut_replays_matched_voltage_and_generation_with_limits";
expected=zeros(nnz(ny),2);
for k=1:height(a.boundary_register)
    r=a.boundary_register.full_branch_row(k);j=find(c.bus(:,BUS_I)==a.boundary_register.ny_bus(k));
    if a.boundary_register.ny_is_from_terminal(k),s=f.branch(r,[PF QF]);else,s=f.branch(r,[PT QT]);end
    expected(j,:)=expected(j,:)-s;
end
assert(max(abs(expected-[a.bus_injection_ledger.p_boundary_mw,a.bus_injection_ledger.q_boundary_mvar]),[],'all')<1e-10);
assert(max(abs(c.bus(:,[PD QD])+expected-f.bus(ny,[PD QD])),[],'all')<1e-10);
names(end+1)="both_terminal_signs_and_gross_effective_accounting";
rev=m;cut=xor(ismember(m.branch(:,F_BUS),ids(ny)),ismember(m.branch(:,T_BUS),ids(ny)));
rev.branch(cut,[F_BUS T_BUS])=rev.branch(cut,[T_BUS F_BUS]);br=b;br.full_candidate=rev;
rf=runpf(rev,mpoption('verbose',0,'out.all',0,'pf.tol',1e-10));ra=extract_compact_ny_boundary(rf,br);
assert(max(abs(ra.candidate.bus(:,[PD QD])-c.bus(:,[PD QD])),[],'all')<1e-7);
names(end+1)="reversed_tie_orientation_preserves_boundary_injection";
bad=f;bad.branch(1,PF)=bad.branch(1,PF)+10;
reject(@()extract_compact_ny_boundary(bad,b),'compact_ny:FullReference');
names(end+1)="fabricated_terminal_flows_rejected";
bad=f;bad.bus(1,PD)=bad.bus(1,PD)+1;
reject(@()extract_compact_ny_boundary(bad,b),'compact_ny:FrozenFullHardware');
names(end+1)="full_reference_load_change_rejected";
bad=f;bad.gen(1,QMAX)=bad.gen(1,QMAX)+100;
reject(@()extract_compact_ny_boundary(bad,b),'compact_ny:FrozenFullHardware');
names(end+1)="capability_widening_rejected";
bad=f;bad.baseMVA=2*f.baseMVA;
reject(@()extract_compact_ny_boundary(bad,b),'compact_ny:FrozenFullHardware');
names(end+1)="power_base_change_rejected";
reject(@()extract_compact_ny_boundary(f,b,struct('reference_bus',43)),'compact_ny:Reference');
names(end+1)="load_bus_cannot_become_fictitious_reference";
assert(~a.electrical_baseline_qualified&&~a.boundary_response_equivalence_established&&~a.dlr_ready);
names(end+1)="extraction_does_not_claim_qualification_or_external_response";
tests=table(names(:),true(numel(names),1),'VariableNames',{'test','passed'});disp(tests);
end
function reject(fn,id)
try,fn();catch e,assert(strcmp(e.identifier,id),'Unexpected error %s',e.identifier);return;end
error('compact_ny_test:MissingGuard','Expected %s',id);
end
