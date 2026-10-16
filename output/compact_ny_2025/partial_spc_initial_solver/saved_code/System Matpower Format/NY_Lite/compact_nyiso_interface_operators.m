function out=compact_nyiso_interface_operators(mpc,branch_keys)
%COMPACT_NYISO_INTERFACE_OPERATORS Current-key AC terminal-flow proxies.
% Zone cuts are conceptual aggregates, not exact NYISO public operators.
% UPNY uses the six source circuits once, never their downstream series paths.
define_constants;keys=string(branch_keys(:));n=size(mpc.branch,1);
assert(numel(keys)==n&&numel(unique(keys))==n,'compact_interfaces:Keys','Unique current branch keys required.');
assert(isfield(mpc,'userdata')&&isfield(mpc.userdata,'nyiso_physical_zone'),'compact_interfaces:Zones','Explicit current zones required.');
z=string(mpc.userdata.nyiso_physical_zone(:));assert(numel(z)==size(mpc.bus,1)&&all(strlength(z)>0));
[ok,f]=ismember(mpc.branch(:,F_BUS),mpc.bus(:,BUS_I));assert(all(ok));
[ok,t]=ismember(mpc.branch(:,T_BUS),mpc.bus(:,BUS_I));assert(all(ok));
spec=["Dysinger_East" "A" "B";"West_Central" "B" "C";"Moses_South" "D" "E"; ...
    "Central_East" "E" "F";"Total_East_proxy" "F" "G";"UPNY_ConEd" "G" "H";"Dunwoodie_South" "I" "J"];
Cf=sparse(7,n);Ct=sparse(7,n);members=table();kind=repmat("conceptual_zone_cut_not_exact_public_operator",7,1);
for k=1:7
    a=z(f)==spec(k,2)&z(t)==spec(k,3)&mpc.branch(:,BR_STATUS)>0;
    b=z(t)==spec(k,2)&z(f)==spec(k,3)&mpc.branch(:,BR_STATUS)>0;
    if k==6
        source_keys=["PERFORM2019:AC:651:858:1";"PERFORM2019:AC:651:858:2"; ...
            "PERFORM2019:AC:651:902:1";"PERFORM2019:AC:651:902:2"; ...
            "PERFORM2019:AC:774:900:1";"PERFORM2019:AC:900:1519:1"];
        [ok,ix]=ismember(source_keys,keys);assert(all(ok),'compact_interfaces:UPNYKeys','Six source UPNY members must resolve.');
        upstream=[73;73;73;73;774;76];
        a=false(n,1);b=a;
        for j=1:6
            assert(mpc.branch(ix(j),BR_STATUS)>0,'compact_interfaces:InactiveMember','UPNY member inactive.');
            if mpc.branch(ix(j),F_BUS)==upstream(j),a(ix(j))=true;
            elseif mpc.branch(ix(j),T_BUS)==upstream(j),b(ix(j))=true;
            else,error('compact_interfaces:UPNYEndpoint','UPNY upstream endpoint changed without mapping.');end
        end
        kind(k)="source_six_circuit_nonintersecting_local_proxy_public_gaps_remain";
    end
    assert(any(a|b),'compact_interfaces:Empty','An interface has no active mapped members.');
    Cf(k,a)=1;Ct(k,b)=1;ix=find(a|b);col=repmat("PF",numel(ix),1);col(b(ix))="PT";
    members=[members;table(repmat(spec(k,1),numel(ix),1),keys(ix),ix,mpc.branch(ix,F_BUS), ...
        mpc.branch(ix,T_BUS),col,ones(numel(ix),1),'VariableNames', ...
        {'interface_name','branch_key','model_branch_row','from_bus','to_bus','meter_column','sign'})]; %#ok<AGROW>
end
out=struct('names',spec(:,1),'from_coefficients',Cf,'to_coefficients',Ct, ...
    'members',members,'registry',table(spec(:,1),kind,false(7,1), ...
    'VariableNames',{'interface_name','operator_kind','exact_public_operator'}), ...
    'public_operator_complete',false);
end
