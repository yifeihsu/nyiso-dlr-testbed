function flows = measure_s13_phase1c_flows(solved)
%MEASURE_S13_PHASE1C_FLOWS Separate downstate received-power components.
% Positive values are net power delivered into the receiving zone at its
% own branch terminal. This retains line losses and works for either source
% orientation. These are model cuts, not exact public NYISO operators.
if ~isfield(solved,'success')||~isscalar(solved.success)||~solved.success|| ...
        size(solved.branch,2)<17
    error('measure_s13_phase1c_flows:Unsolved','A solved MATPOWER case is required.');
end
define_constants;
assert(isfield(solved,'userdata')&&isfield(solved.userdata,'s13')&& ...
    isfield(solved.userdata.s13,'phase1c_report'), ...
    'measure_s13_phase1c_flows:Phase','Phase 1C provenance is required.');
z=string(solved.userdata.nyiso_physical_zone);
[~,f]=ismember(solved.branch(:,F_BUS),solved.bus(:,BUS_I));
[~,t]=ismember(solved.branch(:,T_BUS),solved.bus(:,BUS_I));
labels=["H_I_northern_approach";"I_J_received";"K_J_received";"Zone_J_total_net_import"];
from=["H";"I";"K";"*"];to=["I";"J";"J";"J"];
mw=zeros(4,1);mvar=mw;count=mw;active=solved.branch(:,BR_STATUS)>0;
for k=1:4
    ft=z(t)==to(k)&z(f)~=to(k);tf=z(f)==to(k)&z(t)~=to(k);
    if from(k)~="*",ft=ft&z(f)==from(k);tf=tf&z(t)==from(k);end
    ft=ft&active;tf=tf&active;
    mw(k)=-sum(solved.branch(ft,PT))-sum(solved.branch(tf,PF));
    mvar(k)=-sum(solved.branch(ft,QT))-sum(solved.branch(tf,QF));
    count(k)=sum(ft|tf);
end
flows=table(labels,mw,mvar,count,false(4,1),'VariableNames', ...
    {'component','received_mw','received_mvar','active_branch_count','is_exact_public_operator'});
end
