function out = validate_s14_against_s13_full(source, reduction, options)
%VALIDATE_S14_AGAINST_S13_FULL Independent PF replay of direct-source reduction.
% Reports reduction error, never public-target fit. Fixed external PQ sources
% must remain at their registered bounds. NY PV/slack P/Q capability is checked
% after PF; a converged power flow alone cannot qualify an operating case.
if nargin<3,options=struct();end
if ~isfield(options,'boundary_q_absolute_band_mvar'),options.boundary_q_absolute_band_mvar=1;end
if ~isfield(options,'zero_current_floor_ka'),options.zero_current_floor_ka=1e-3;end
if ~isfield(options,'interface_map')
    if isfield(source.userdata.s13,'overlay_report')
        options.interface_map=source.userdata.s13.overlay_report.operator_map;
    else
        options.interface_map=table(strings(0,1),zeros(0,1),zeros(0,1), ...
            'VariableNames',{'interface_name','model_branch_row','operator_sign'});
    end
end
assert(strcmp(s14_network_fingerprint(source),reduction.source_network_hash), ...
    's14:ValidationSourceChanged','Source changed after the reduction was built.');
candidate=reduction.candidate;
replay=runpf(candidate,mpoption('verbose',0,'out.all',0));
assert(replay.success==1,'s14:ReplayFailed','Reduced-case independent PF replay did not converge.');
rows=reduction.retained_source_bus_rows;
err_v=replay.bus(:,8)-source.bus(rows,8);
keep=reduction.source_keep_branch_rows;
% Recompute the full-source powers independently, including branch-end Q.
[sp,si]=powers(source);[rp,ri]=powers(replay);
nyrows=reduction.retention.ny_internal_branch_rows;
[~,nyred]=ismember(nyrows,keep);
assert(all(nyred>0),'s14:InternalBranchOmitted','NY internal branch was omitted.');
current_error=max(abs(ri(nyred,:)-si(nyrows,:))./ ...
    max(abs(si(nyrows,:)),options.zero_current_floor_ka),[],'all');
if isempty(current_error),current_error=0;end
src_loss=sum(sp(nyrows,1)+sp(nyrows,3));red_loss=sum(rp(nyred,1)+rp(nyred,3));
loss_error=abs(src_loss-red_loss)/max(abs(src_loss),1e-3);
ties=reduction.retention.tie_branch_rows;[~,tred]=ismember(ties,keep);
nyids=reduction.retention.ny_bus_ids;
nyfrom=ismember(source.branch(ties,1),nyids);
source_q=sp(ties,4);source_q(nyfrom)=sp(ties(nyfrom),2);
reduced_q=rp(tred,4);reduced_q(nyfrom)=rp(tred(nyfrom),2);
q_error=abs(source_q-reduced_q);
q_band=max(0.1*abs(source_q),options.boundary_q_absolute_band_mvar);
q_ratio=max(q_error./q_band);if isempty(q_ratio),q_ratio=0;end
map=options.interface_map;interface_names=unique(string(map.interface_name),'stable');
source_flow=zeros(numel(interface_names),1);reduced_flow=source_flow;
for k=1:numel(interface_names)
    mask=string(map.interface_name)==interface_names(k);
    sr=map.model_branch_row(mask);[present,rr]=ismember(sr,keep);
    assert(all(present),'s14:InterfaceBranchOmitted','Interface component was not retained.');
    signs=map.operator_sign(mask);
    source_flow(k)=sum(signs.*sp(sr,1));reduced_flow(k)=sum(signs.*rp(rr,1));
end
interface_error=abs(source_flow-reduced_flow);
if isempty(interface_error),max_interface_error=NaN;else,max_interface_error=max(interface_error);end
g=replay.gen;active=g(:,8)>0;
bound_excess=max([g(active,2)-g(active,9);g(active,10)-g(active,2); ...
    g(active,3)-g(active,4);g(active,5)-g(active,3);0]);
sg=source.gen;sa=sg(:,8)>0;
source_bound_excess=max([sg(sa,2)-sg(sa,9);sg(sa,10)-sg(sa,2); ...
    sg(sa,3)-sg(sa,4);sg(sa,5)-sg(sa,3);0]);
source_voltage_excess=max([source.bus(:,8)-source.bus(:,12);source.bus(:,13)-source.bus(:,8);0]);
candidate_voltage_excess=max([replay.bus(:,8)-replay.bus(:,12);replay.bus(:,13)-replay.bus(:,8);0]);
sl=source.branch(:,11)>0 & source.branch(:,6)>0;
cl=replay.branch(:,11)>0 & replay.branch(:,6)>0;
source_rating_excess=max([max(hypot(sp(sl,1),sp(sl,2)),hypot(sp(sl,3),sp(sl,4)))-source.branch(sl,6);0]);
candidate_rating_excess=max([max(hypot(rp(cl,1),rp(cl,2)),hypot(rp(cl,3),rp(cl,4)))-replay.branch(cl,6);0]);
source_angle_excess=angle_excess(source);candidate_angle_excess=angle_excess(replay);
if any(~isfinite(g(active,[4 5 9 10])),'all'),bound_excess=Inf;end
if any(~isfinite(sg(sa,[4 5 9 10])),'all'),source_bound_excess=Inf;end
if any(~isfinite(source.bus(:,[8 12 13])),'all'),source_voltage_excess=Inf;end
if any(~isfinite(replay.bus(:,[8 12 13])),'all'),candidate_voltage_excess=Inf;end
reg=reduction.injection_register;extrows=reg.candidate_gen_row;
external_excess=max([abs(g(extrows,2)-reg.reference_p_mw); ...
    abs(g(extrows,3)-reg.reference_q_mvar);0]);
external_is_reference=any(ismember(replay.bus(replay.bus(:,2)~=1,1),reg.bus_id));
name=["retained_voltage_rmse_pu";"retained_voltage_max_error_pu"; ...
    "ny_internal_branch_max_current_relative_error";"ny_active_loss_relative_error"; ...
    "boundary_reactive_error_over_registered_band";"registered_interface_max_error_mw"; ...
    "generator_capability_max_violation";"external_fixed_PQ_max_violation"; ...
    "external_PV_or_REF_bus_count";"source_generator_capability_max_violation"; ...
    "source_voltage_bound_excess_pu";"candidate_voltage_bound_excess_pu"; ...
    "source_branch_rating_excess_mva";"candidate_branch_rating_excess_mva"; ...
    "source_angle_limit_excess_rad";"candidate_angle_limit_excess_rad"];
value=[sqrt(mean(err_v.^2));max(abs(err_v));current_error;loss_error;q_ratio; ...
    max_interface_error;bound_excess;external_excess;double(external_is_reference); ...
    source_bound_excess;source_voltage_excess;candidate_voltage_excess;source_rating_excess;candidate_rating_excess; ...
    source_angle_excess;candidate_angle_excess];
limit=[0.005;0.015;0.05;0.05;1;50;1e-5;1e-5;0;1e-5;1e-5;1e-5;1e-3;1e-3;1e-6;1e-6];
passed=value<=limit;
status=repmat("evaluated",numel(name),1);
if isempty(interface_error),status(name=="registered_interface_max_error_mw")="unavailable_no_registered_operator";end
gates=table(name,value,limit,passed,status, ...
    'VariableNames',{'metric','value','limit','passed','status'});
interfaces=table(interface_names,source_flow,reduced_flow,interface_error, ...
    'VariableNames',{'interface_name','source_mw','reduced_mw','absolute_error_mw'});
required_reduction_metrics=["retained_voltage_rmse_pu";"retained_voltage_max_error_pu"; ...
    "ny_internal_branch_max_current_relative_error";"ny_active_loss_relative_error"; ...
    "boundary_reactive_error_over_registered_band";"registered_interface_max_error_mw"; ...
    "external_fixed_PQ_max_violation";"external_PV_or_REF_bus_count"];
[present,required_rows]=ismember(required_reduction_metrics,gates.metric);
reduction_pass=all(present) && all(gates.passed(required_rows)) && ...
    all(gates.status(required_rows)=="evaluated");
out=struct('gates',gates,'interfaces',interfaces,'replay',replay, ...
    'passed',all(passed),'reduction_metrics_passed',reduction_pass, ...
    'required_reduction_metrics',required_reduction_metrics, ...
    'source_and_candidate_capability_passed',max(bound_excess,source_bound_excess)<=1e-5, ...
    'public_target_fit_evaluated',false,'promotion_eligible',false);
end

function excess=angle_excess(m)
br=m.branch(m.branch(:,11)>0,1:13);
[~,br(:,1)]=ismember(br(:,1),m.bus(:,1));[~,br(:,2)]=ismember(br(:,2),m.bus(:,1));
[D,l,u]=makeAang(m.baseMVA,br,size(m.bus,1),mpoption);
a=D*m.bus(:,9)*pi/180;excess=max([0;a-u;l-a]);
end

function [s,i]=powers(mpc)
bus=mpc.bus;ids=bus(:,1);bus(:,1)=(1:size(bus,1))';
br=mpc.branch(:,1:13);[~,br(:,1)]=ismember(br(:,1),ids);[~,br(:,2)]=ismember(br(:,2),ids);
[~,yf,yt]=makeYbus(mpc.baseMVA,bus,br);
v=bus(:,8).*exp(1j*bus(:,9)*pi/180); cf=yf*v;ct=yt*v;
sf=mpc.baseMVA*v(br(:,1)).*conj(cf);st=mpc.baseMVA*v(br(:,2)).*conj(ct);
s=[real(sf) imag(sf) real(st) imag(st)];
i=[abs(cf)*mpc.baseMVA./(sqrt(3)*bus(br(:,1),10)), ...
    abs(ct)*mpc.baseMVA./(sqrt(3)*bus(br(:,2),10))];
end
