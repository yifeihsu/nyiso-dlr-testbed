function out=test_ny_boundary_assembly
%TEST_NY_BOUNDARY_ASSEMBLY Sign, source identity and double-counting gates.
n=fixture; b=build_ny_boundary_register(n);a=apply_ny_boundary_injections(n,b);
% Two independent boundary identities share bus 1 with native generator 1.
assert(height(b.boundary_register)==2&&height(b.reference_register)==1);
assert(a.bus_injection_ledger.p_boundary_mw(1)==30&& ...
    a.bus_injection_ledger.q_boundary_mvar(1)==2);
assert(a.candidate.bus(1,3)==n.source.bus(1,3)-30&& ...
    a.candidate.bus(1,4)==n.source.bus(1,4)-2);
assert(size(a.candidate.gen,1)==3&&isequal(a.candidate.gen,n.source.gen(1:3,:)));
assert(isequal(a.candidate.branch,n.source.branch));
assert(a.accounting.external_p_injection_mw==30&& ...
    a.accounting.external_q_injection_mvar==2);
assert(a.bus_injection_ledger.p_boundary_mw(3)==0&& ...
    a.bus_injection_ledger.q_boundary_mvar(3)==0,'RF values must never become external injections.');
assert(a.candidate.bus(1,2)==3,'Native REF sharing an import bus must survive.');

% A negative boundary P is an export and increases effective demand.
export_source=n;export_source.source.gen(4,2)=-40;
export=build_ny_boundary_register(export_source);
ae=apply_ny_boundary_injections(export_source,export);
assert(ae.candidate.bus(1,3)==n.source.bus(1,3)+50);

% Converted offline wins over nonzero stored PG and a raw-online status.
off=n;off.source.gen(5,8)=0;off.boundary_reconciliation.canonical_status(2)=0;
ob=build_ny_boundary_register(off);oa=apply_ny_boundary_injections(off,ob);
assert(ob.boundary_register.snapshot_pg_mw(2)==-10&& ...
    ob.boundary_register.p_injection_mw(2)==0&& ...
    oa.accounting.external_p_injection_mw==40);
bad=ob;bad.boundary_register.p_injection_mw(2)=3;
expect_failure(@()apply_ny_boundary_injections(off,bad), ...
    'apply_ny_boundary_injections:InactiveInjection');

again=n;again.source=a.candidate;
expect_failure(@()apply_ny_boundary_injections(again,b), ...
    'apply_ny_boundary_injections:AlreadyApplied');
bad=b;bad.boundary_register(2,:)=bad.boundary_register(1,:);
expect_failure(@()apply_ny_boundary_injections(n,bad), ...
    'apply_ny_boundary_injections:DuplicateIdentity');
bad=b;bad.boundary_register=bad.boundary_register(1,:);
expect_failure(@()apply_ny_boundary_injections(n,bad), ...
    'apply_ny_boundary_injections:IncompleteRemoval');
bad=b;bad.reference_register.p_injection_mw=999;
expect_failure(@()apply_ny_boundary_injections(n,bad), ...
    'apply_ny_boundary_injections:ReferencePolicy');
bad=b;bad.boundary_register.p_injection_mw(1)=45;
expect_failure(@()apply_ny_boundary_injections(n,bad), ...
    'apply_ny_boundary_injections:FrozenSnapshot');

% Reproduced PF values are accepted only with identical source hardware.
snapshot=n.source;snapshot.success=true;snapshot.gen(4,2:3)=[42,4];
sb=build_ny_boundary_register(n,struct('snapshot_case',snapshot));
sa=apply_ny_boundary_injections(n,sb);
assert(sa.accounting.external_p_injection_mw==32&&sa.accounting.external_q_injection_mvar==3);
snapshot.branch(1,3)=snapshot.branch(1,3)+0.01;
expect_failure(@()build_ny_boundary_register(n,struct('snapshot_case',snapshot)), ...
    'build_ny_boundary_register:SnapshotNetwork');

out=struct('pass',true,'test_count',15,'shared_landing_supported',true, ...
    'inactive_injection_rejected',true,'reference_injection_rejected',true, ...
    'native_generation_preserved',true,'max_assembly_error', ...
    max([a.accounting.max_P_assembly_error_mw,a.accounting.max_Q_assembly_error_mvar]));
disp(out);
end

function expect_failure(call,id)
failed=false;
try,call();catch e,failed=strcmp(e.identifier,id);end
assert(failed,'test_ny_boundary_assembly:ExpectedFailure','Expected %s.',id);
end

function n=fixture
s=loadcase('case9');s.bus(:,11)=65;s.bus_name="BUS_"+string(s.bus(:,1));
s.bus_name=cellstr(s.bus_name);s=rmfield(s,'gencost');
g=zeros(3,size(s.gen,2));g(:,1)=[1;1;3];g(:,2:3)=[40 3;-10 -1;999 999];
g(:,4)=1000;g(:,5)=-1000;g(:,6)=1;g(:,7)=100;g(:,8)=1;g(:,9)=1000;g(:,10)=-1000;
s.gen=[s.gen;g];
source_gen_row=(1:6)';source_bus=s.gen(:,1);source_generator_id=["G1";"G2";"G3";"B1";"B2";"RF"];
device_key="PERFORM2019:GEN:"+string(source_bus)+":"+source_generator_id;
source_device_role=[repmat("native_generator",3,1);repmat("external_boundary_proxy",2,1);"reference_placeholder"];
inventory=table(source_gen_row,source_bus,source_generator_id,device_key,source_device_role);
rec=inventory(4:6,:);rec.proposed_schedule_group=["TEST_IMPORT";"TEST_EXPORT";"UNASSIGNED_REFERENCE"];
rec.boundary_member=[true;true;false];rec.canonical_status=ones(3,1);rec.raw_status=ones(3,1);
rec.legacy_schedule_member=[true;true;false];
n=struct('source',s,'generator_inventory',inventory,'boundary_reconciliation',rec);
end
