function mpc=add_ac_terminal_current_limits(mpc,limits,constraint_name)
%ADD_AC_TERMINAL_CURRENT_LIMITS Actual terminal amperes, including charging.
% A nominal-kV MVA ceiling alone does not guarantee a fixed ampere ceiling
% when voltage drops. Existing MVA constraints remain independently active.
if nargin<3,constraint_name='synthetic_terminal_ampacity';end
assert(any(strcmp(constraint_name,{'synthetic_terminal_ampacity','conductor_section_end_ampacity','cable_section_static_ampacity'})), ...
    'acDLR:ConstraintName','Use the hardware or conductor section-end current constraint.');
rows=limits.branch_row;
assert(numel(unique(rows))==height(limits)&&all(mpc.branch(rows,11)>0), ...
    'acDLR:TerminalRows','Use unique active branch rows.');
from_selected=isfinite(limits.total_terminal_current_limit_from_a);
to_selected=isfinite(limits.total_terminal_current_limit_to_a);
assert(all(from_selected|to_selected)&&all(limits.total_terminal_current_limit_from_a(from_selected)>0) ...
    &&all(limits.total_terminal_current_limit_to_a(to_selected)>0), ...
    'acDLR:TerminalAmps','Each row needs at least one finite positive terminal limit; NaN denotes no equipment at a section interior.');
[ok,f]=ismember(mpc.branch(rows,1),mpc.bus(:,1));assert(all(ok));
[ok,t]=ismember(mpc.branch(rows,2),mpc.bus(:,1));assert(all(ok));
d=struct('external_from_rows',rows(from_selected),'external_to_rows',rows(to_selected), ...
    'constraint_name',constraint_name, ...
    'from_limit_pu',limits.total_terminal_current_limit_from_a(from_selected).*sqrt(3).*mpc.bus(f(from_selected),10)/(1000*mpc.baseMVA), ...
    'to_limit_pu',limits.total_terminal_current_limit_to_a(to_selected).*sqrt(3).*mpc.bus(t(to_selected),10)/(1000*mpc.baseMVA));
mpc=add_userfcn(mpc,'formulation',@formulation,d,true);
if strcmp(constraint_name,'synthetic_terminal_ampacity')
    mpc.userdata.ac_system.terminal_current_constraints_applied=true;
    mpc.userdata.ac_system.terminal_current_limits=limits;
elseif strcmp(constraint_name,'conductor_section_end_ampacity')
    mpc.userdata.ac_system.conductor_section_end_current_limits=limits;
else
    mpc.userdata.ac_system.cable_section_static_current_limits=limits;
end
end
function om=formulation(om,mpopt,args)
assert(~mpopt.opf.v_cartesian,'acDLR:Polar','Terminal-current callback supports polar voltage variables.');
m=om.get_mpc();[ok,rf]=ismember(args.external_from_rows,m.order.branch.status.on);assert(all(ok));
[ok,rt]=ismember(args.external_to_rows,m.order.branch.status.on);assert(all(ok));
[~,yf,yt]=makeYbus(m.baseMVA,m.bus,m.branch);
d=struct('branch',[m.branch(rf,:);m.branch(rt,:)],'Yseries',[yf(rf,:);yt(rt,:)], ...
    'limit_pu',[args.from_limit_pu;args.to_limit_pu]);
% The tested current-squared derivative routine accepts any linear Y*V;
% these matrices include shunt charging and complex transformer tap factors.
om.add_nln_constraint(args.constraint_name,numel(rf)+numel(rt),0, ...
    @(x)constraint(x,d),@(x,mu)hessian(x,mu,d),{'Va','Vm'});
end
function [h,dh]=constraint(x,d),[h,dh]=dlr_series_constraint(x,d);end
function H=hessian(x,mu,d),[~,~,H]=dlr_series_constraint(x,d,mu);end
