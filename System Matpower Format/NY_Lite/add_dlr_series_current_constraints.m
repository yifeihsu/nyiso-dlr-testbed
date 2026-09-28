function mpc=add_dlr_series_current_constraints(mpc,realizations,ampacity_subconductor)
%ADD_DLR_SERIES_CURRENT_CONSTRAINTS Enforce series current, not terminal MVA.
% Existing RATE_A continues to cap terminal equipment MVA independently.
n=height(realizations);ampacity_subconductor=ampacity_subconductor(:);
assert(numel(ampacity_subconductor)==n&&all(isfinite(ampacity_subconductor)&ampacity_subconductor>0));
r=realizations.branch_row;assert(numel(unique(r))==n&&all(mpc.branch(r,11)>0));
amp=ampacity_subconductor.*realizations.circuits.*realizations.bundle_count;
d=struct('external_rows',r,'limit_pu',amp.*sqrt(3).*realizations.base_kv/(mpc.baseMVA*1000));
mpc=add_userfcn(mpc,'formulation',@formulation,d,true);
end
function om=formulation(om,mpopt,args)
assert(~mpopt.opf.v_cartesian,'dlr:Polar','Only polar voltages are supported.');
m=om.get_mpc();[ok,r]=ismember(args.external_rows,m.order.branch.status.on);assert(all(ok),'dlr:Inactive','A thermal branch was removed.');
d=args;d.branch=m.branch(r,:);nb=size(m.bus,1);n=numel(r);
y=1./(d.branch(:,3)+1i*d.branch(:,4));
d.Yseries=sparse((1:n)',d.branch(:,1),y,n,nb)-sparse((1:n)',d.branch(:,2),y,n,nb);
om.add_nln_constraint('synthetic_series_ampacity',n,0,@(x)constraint(x,d),@(x,mu)hessian(x,mu,d),{'Va','Vm'});
end
function [h,dh]=constraint(x,d),[h,dh]=dlr_series_constraint(x,d);end
function H=hessian(x,mu,d),[~,~,H]=dlr_series_constraint(x,d,mu);end
