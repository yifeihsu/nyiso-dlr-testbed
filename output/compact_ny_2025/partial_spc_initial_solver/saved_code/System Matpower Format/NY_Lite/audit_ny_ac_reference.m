function out=audit_ny_ac_reference(m,options)
%AUDIT_NY_AC_REFERENCE Physical-unit AC and limit ledger, including slack.
% A converged PF alone is insufficient. Every online generator and both
% branch terminals are checked, and inactive records remain in the ledger.
if nargin<2,options=struct();end
define_constants;
options=defaults(options,'power_tolerance',1e-3,'voltage_tolerance',1e-5, ...
    'angle_tolerance',1e-4);
assert(isfield(m,'success')&&isfield(m,'branch')&&size(m.branch,2)>=QT, ...
    'audit_ny_ac_reference:Unsolved','A solved case with branch flows is required.');
ni=size(m.bus,1);ng=size(m.gen,1);nl=size(m.branch,1);
mi=ext2int(m);[Y,Yf,Yt]=makeYbus(mi);
v=mi.bus(:,VM).*exp(1i*mi.bus(:,VA)*pi/180);
cg=sparse(mi.gen(:,GEN_BUS),1:size(mi.gen,1),1,size(mi.bus,1),size(mi.gen,1));
mis=(v.*conj(Y*v))*m.baseMVA+mi.bus(:,PD)+1i*mi.bus(:,QD)-cg*(mi.gen(:,PG)+1i*mi.gen(:,QG));
[~,pos]=ismember(mi.order.bus.i2e,m.bus(:,BUS_I));
p_error=zeros(ni,1);q_error=p_error;p_error(pos)=real(mis);q_error(pos)=imag(mis);
excluded=m.bus(:,BUS_TYPE)==NONE;included=~excluded;
excluded_injection=any(m.bus(excluded,[PD QD GS BS])~=0,'all');
excluded_generator=any(m.gen(:,GEN_STATUS)>0 & ismember(m.gen(:,GEN_BUS),m.bus(excluded,BUS_I)));
excluded_branch=any(m.branch(:,BR_STATUS)>0 & (ismember(m.branch(:,F_BUS),m.bus(excluded,BUS_I)) | ...
    ismember(m.branch(:,T_BUS),m.bus(excluded,BUS_I))));
bus_bounds_invalid=included & (~all(isfinite(m.bus(:,[VMIN VMAX])),2) | ...
    m.bus(:,VMIN)>m.bus(:,VMAX));
v_low=max(0,m.bus(:,VMIN)-m.bus(:,VM));v_high=max(0,m.bus(:,VM)-m.bus(:,VMAX));
v_low(excluded)=0;v_high(excluded)=0;
bus_bad=included & (abs(p_error)>options.power_tolerance|abs(q_error)>options.power_tolerance| ...
    v_low>options.voltage_tolerance|v_high>options.voltage_tolerance|bus_bounds_invalid | ...
    ~all(isfinite([m.bus(:,VM) m.bus(:,VA) p_error q_error]),2));
out.bus=table(m.bus(:,BUS_I),m.bus(:,BUS_TYPE),m.bus(:,VM),m.bus(:,VMIN),m.bus(:,VMAX), ...
    p_error,q_error,v_low,v_high,bus_bad,'VariableNames',{'source_bus','bus_type', ...
    'vm_pu','vmin_pu','vmax_pu','p_mismatch_mw','q_mismatch_mvar', ...
    'voltage_below_min_pu','voltage_above_max_pu','violated'});
on=m.gen(:,GEN_STATUS)>0;
gen_bounds_invalid=on & (~all(isfinite(m.gen(:,[PMIN PMAX QMIN QMAX])),2) | ...
    m.gen(:,PMIN)>m.gen(:,PMAX) | m.gen(:,QMIN)>m.gen(:,QMAX));
p_low=max(0,m.gen(:,PMIN)-m.gen(:,PG));p_high=max(0,m.gen(:,PG)-m.gen(:,PMAX));
q_low=max(0,m.gen(:,QMIN)-m.gen(:,QG));q_high=max(0,m.gen(:,QG)-m.gen(:,QMAX));
p_low(~on)=0;p_high(~on)=0;q_low(~on)=0;q_high(~on)=0;
gen_bad=max([p_low p_high q_low q_high],[],2)>options.power_tolerance|gen_bounds_invalid | ...
    (on & ~all(isfinite(m.gen(:,[PG QG])),2));
keys="GEN_ROW:"+string((1:ng)');
if isfield(options,'generator_keys'),keys=string(options.generator_keys(:));assert(numel(keys)==ng);end
out.generator=table((1:ng)',keys,m.gen(:,GEN_BUS),on,m.gen(:,PG),m.gen(:,PMIN),m.gen(:,PMAX), ...
    m.gen(:,QG),m.gen(:,QMIN),m.gen(:,QMAX),p_low,p_high,q_low,q_high,gen_bad, ...
    'VariableNames',{'gen_row','device_key','source_bus','online','pg_mw','pmin_mw','pmax_mw', ...
    'qg_mvar','qmin_mvar','qmax_mvar','p_below_min_mw','p_above_max_mw', ...
    'q_below_min_mvar','q_above_max_mvar','violated'});
% Recompute terminal powers independently. Saved PF/QF/PT/QT columns are
% evidence to check, never the source of rating/loss acceptance quantities.
branch_rows=mi.order.branch.status.on;
source_f=mi.baseMVA*v(mi.branch(:,F_BUS)).*conj(Yf*v);
source_t=mi.baseMVA*v(mi.branch(:,T_BUS)).*conj(Yt*v);
calculated_f=complex(zeros(nl,1));calculated_t=calculated_f;
calculated_f(branch_rows)=source_f;calculated_t(branch_rows)=source_t;
active=m.branch(:,BR_STATUS)>0;sf=abs(calculated_f);st=abs(calculated_t);
saved_f=complex(m.branch(:,PF),m.branch(:,QF));saved_t=complex(m.branch(:,PT),m.branch(:,QT));
flow_error=max(abs([saved_f-calculated_f saved_t-calculated_t]),[],2);
flow_bad=active & (flow_error>options.power_tolerance | ...
    ~all(isfinite(m.branch(:,[PF QF PT QT])),2));
branch_limits_invalid=active & (~all(isfinite(m.branch(:,[RATE_A ANGMIN ANGMAX])),2) | ...
    m.branch(:,RATE_A)<0 | m.branch(:,ANGMIN)>m.branch(:,ANGMAX));
rated=active&m.branch(:,RATE_A)>0;
f_over=max(0,sf-m.branch(:,RATE_A)).*rated;t_over=max(0,st-m.branch(:,RATE_A)).*rated;
[~,fb]=ismember(m.branch(:,F_BUS),m.bus(:,BUS_I));[~,tb]=ismember(m.branch(:,T_BUS),m.bus(:,BUS_I));
angle=m.bus(fb,VA)-m.bus(tb,VA);
% MATPOWER treats zero/zero as unrestricted, but a lone zero is a real
% one-sided limit (for example [-360,0] imposes an upper bound of zero).
% Delegate the exact convention to the same constraint constructor as OPF.
angle_branch=m.branch;angle_branch(:,F_BUS)=fb;angle_branch(:,T_BUS)=tb;
[~,angle_lower,angle_upper,angle_rows]=makeAang(m.baseMVA,angle_branch,ni,mpoption);
on_angle=active(angle_rows);angle_rows=angle_rows(on_angle);
angle_lower=angle_lower(on_angle)*180/pi;angle_upper=angle_upper(on_angle)*180/pi;
alow=zeros(nl,1);ahigh=alow;
alow(angle_rows)=max(0,angle_lower-angle(angle_rows));
ahigh(angle_rows)=max(0,angle(angle_rows)-angle_upper);
br_bad=f_over>options.power_tolerance|t_over>options.power_tolerance| ...
    alow>options.angle_tolerance|ahigh>options.angle_tolerance|branch_limits_invalid|flow_bad;
bkeys="BRANCH_ROW:"+string((1:nl)');
if isfield(options,'branch_keys'),bkeys=string(options.branch_keys(:));assert(numel(bkeys)==nl);end
out.branch=table((1:nl)',bkeys,m.branch(:,F_BUS),m.branch(:,T_BUS),active, ...
    m.branch(:,RATE_A),sf,st,f_over,t_over,angle,m.branch(:,ANGMIN),m.branch(:,ANGMAX), ...
    alow,ahigh,br_bad,'VariableNames',{'branch_row','device_key','from_bus','to_bus','online', ...
    'rate_a_mva','from_mva','to_mva','from_overload_mva','to_overload_mva','angle_deg', ...
    'angle_min_deg','angle_max_deg','angle_below_min_deg','angle_above_max_deg','violated'});
out.bus.invalid_voltage_bounds=bus_bounds_invalid;
out.generator.invalid_capability_bounds=gen_bounds_invalid;
out.branch.invalid_limit_bounds=branch_limits_invalid;
out.branch.stored_terminal_flow_error_mva=flow_error;
out.branch.stored_terminal_flow_inconsistent=flow_bad;
loss=sum(real(calculated_f(active)+calculated_t(active)));shunt=sum(m.bus(~excluded,GS).*m.bus(~excluded,VM).^2);
balance=sum(m.gen(on,PG))-sum(m.bus(~excluded,PD))-loss-shunt;
finite=all(isfinite([p_error;q_error;m.bus(included,VM);m.bus(included,VA); ...
    m.gen(on,PG);m.gen(on,QG);sf;st]));
out.passed=isscalar(m.success)&&m.success==1&&finite&&~excluded_injection&&~excluded_generator&&~excluded_branch&& ...
    ~any([bus_bad;gen_bad;br_bad])&& ...
    abs(balance)<=options.power_tolerance;
out.summary=table(logical(m.success),out.passed,sum(bus_bad),sum(gen_bad),sum(br_bad), ...
    max(abs(p_error)),max(abs(q_error)),max([v_low;v_high]),max([p_low;p_high]), ...
    max([q_low;q_high]),max([f_over;t_over]),max([alow;ahigh]),loss,shunt,balance, ...
    sum(m.gen(on,PG)),sum(m.bus(:,PD)),excluded_injection, ...
    'VariableNames',{'pf_converged','all_limits_passed','violated_buses','violated_generators', ...
    'violated_branches','max_nodal_p_mismatch_mw','max_nodal_q_mismatch_mvar', ...
    'max_voltage_violation_pu','max_generator_p_violation_mw','max_generator_q_violation_mvar', ...
    'max_branch_overload_mva','max_angle_violation_deg','branch_loss_mw','shunt_loss_mw', ...
    'active_balance_error_mw','generator_p_mw','effective_load_mw','excluded_injection_present'});
out.summary.finite_ordered_generator_bounds=~any(gen_bounds_invalid);
out.summary.finite_ordered_voltage_bounds=~any(bus_bounds_invalid);
out.summary.valid_branch_limit_bounds=~any(branch_limits_invalid);
out.summary.stored_terminal_flows_consistent=~any(flow_bad);
out.summary.excluded_online_generator_present=excluded_generator;
out.summary.excluded_active_branch_present=excluded_branch;
out.summary.max_stored_terminal_flow_error_mva=max([flow_error(active);0]);
out.tolerances=options;
end
function s=defaults(s,varargin)
for k=1:2:numel(varargin),if ~isfield(s,varargin{k}),s.(varargin{k})=varargin{k+1};end,end
end
