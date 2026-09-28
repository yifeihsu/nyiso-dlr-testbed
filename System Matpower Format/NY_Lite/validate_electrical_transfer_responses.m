function report=validate_electrical_transfer_responses(source,reduction)
%VALIDATE_ELECTRICAL_TRANSFER_RESPONSES Frozen A-to-J load-transfer diagnostics.
% Freeze network, controls and external equivalent injections. Only the two
% registered load terms change. Source/reduced comparison is not public truth.
zone=attach_nyiso_zone_metadata(source);zone=string(zone.userdata.nyiso_zone);
aa=find(zone=="A");jj=find(zone=="J");
assert(~isempty(aa)&&~isempty(jj),'A/J transfer terminals unavailable.');
[~,ai]=max(source.bus(aa,3));a=aa(ai);
[~,ji]=max(source.bus(jj,3));j=jj(ji);
assert(source.bus(a,3)>0,'Source Zone A needs positive transferable demand.');
% Inherited J may have zero allocated demand. Use positive transfers only
% and cap their magnitude to keep all loads nonnegative in every fixture.
amount=[5;10;25;50;75;100]*min(1,0.9*source.bus(a,3)/100);report=table();
for k=1:numel(amount)
    p=source;p.bus(a,3)=p.bus(a,3)-amount(k);p.bus(j,3)=p.bus(j,3)+amount(k);
    p=runpf(p,mpoption('verbose',0,'out.all',0));
    r=reduction;[~,ra]=ismember(source.bus(a,1),r.candidate.bus(:,1));
    [~,rj]=ismember(source.bus(j,1),r.candidate.bus(:,1));
    r.candidate.bus(ra,3)=r.candidate.bus(ra,3)-amount(k);
    r.candidate.bus(rj,3)=r.candidate.bus(rj,3)+amount(k);
    vm=NaN;current=NaN;flow=NaN;passed=false;limits=false;
    if p.success
        try
            v=validate_s14_against_s13_full(p,r);
            vm=v.gates.value(2);current=v.gates.value(3);flow=v.gates.value(6);
            passed=v.reduction_metrics_passed;limits=v.source_and_candidate_capability_passed;
        catch err
            if ~strcmp(err.identifier,'s14:ReplayFailed'),rethrow(err);end
        end
    end
    report=[report;table(amount(k),source.bus(a,1),source.bus(j,1), ...
        vm,current,flow,passed,limits,false, ...
        'VariableNames',{'transfer_mw','from_load_bus','to_load_bus','voltage_max_error_pu', ...
        'current_relative_error','interface_error_mw','reduction_response_pass', ...
        'capability_pass','independent_public_validation'})]; %#ok<AGROW>
end
end
