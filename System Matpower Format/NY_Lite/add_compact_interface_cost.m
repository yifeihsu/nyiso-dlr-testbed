function mpc=add_compact_interface_cost(mpc,operators,targets,scale_mw)
%ADD_COMPACT_INTERFACE_COST Add train-only cost after external-row mapping.
assert(isscalar(scale_mw)&&isfinite(scale_mw)&&scale_mw>0);
[ok,ix]=ismember(operators.names,string(targets.interface_name));assert(all(ok));
d=struct('Cf',operators.from_coefficients,'Ct',operators.to_coefficients, ...
    'target',targets.target_flow_mw(ix),'scale',scale_mw*ones(numel(ix),1));
assert(all(isfinite(d.target)));
mpc=add_userfcn(mpc,'formulation',@formulation,d,true);
end
function om=formulation(om,mpopt,args)
assert(~mpopt.opf.v_cartesian,'compact_interfaces:Polar','Only polar voltage formulation is supported.');
d=args;m=om.get_mpc();ix=m.order.branch.status.on;
d.Cf=d.Cf(:,ix);d.Ct=d.Ct(:,ix);d.branch=m.branch;d.baseMVA=m.baseMVA;
[~,d.Yf,d.Yt]=makeYbus(m.baseMVA,m.bus,m.branch);
nl=size(m.branch,1);nb=size(m.bus,1);
d.F=sparse(1:nl,m.branch(:,1),1,nl,nb);d.T=sparse(1:nl,m.branch(:,2),1,nl,nb);
om.add_nln_cost('compact_interface_training',1,@(x)compact_interface_ac_cost(x,d),{'Va','Vm'});
end
