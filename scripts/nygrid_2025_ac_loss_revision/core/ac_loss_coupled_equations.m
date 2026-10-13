function [F,J,state]=ac_loss_coupled_equations(ctx,V,want_J)
% Exact nonlocal loss-budget response in polar AC balance equations.
% d|A*V|^2/dx = 2*real(conj(A*V).*(A*dV/dx)). No empirical flow target enters.
if nargin<3,want_J=true;end
base=ctx.base;p=ctx.policy;n=numel(V);F=[];J=[];
state=struct('valid',false,'reason','');
if any(~isfinite(V))||any(abs(V)<1e-5),state.reason='invalid_voltage';return;end
I=ctx.series_operator*V;
loss=base.baseMVA*base.branch(:,3).*abs(I).^2;
budget=ctx.ownership*loss;
try
    [m,applied]=ac_loss_apply_budget(base,p,budget);
catch err
    if startsWith(err.identifier,'acLoss:')
        state.reason=err.identifier;state.budget_MW=budget;return;
    end
    rethrow(err);
end
delta=applied.allocated_generator_increment_MW;
S=ctx.base_S+ctx.load_response*budget+ctx.generator_map*delta/base.baseMVA;
network=V.*conj(ctx.Y*V);mis=network-S;
F=[real(mis(ctx.pvpq));imag(mis(ctx.pq))];
state=struct('valid',true,'reason','admissible','input',m,'applied',applied, ...
    'budget_MW',budget,'branch_loss_MW',loss,'specified_S_pu',S,'network_S_pu',network, ...
    'active_global_identity_residual_MW',base.baseMVA*sum(real(mis)));
if ~want_J,return;end
D=ctx.load_response;
for g=12:14
    use=find(p.external_gen_group==g);room=p.Pmax(use)-p.baseline_PG(use);w=p.generator_share(use);
    free=room-delta(use)>1e-8&w>0;
    if ~any(free)
        ratio=room./max(w,eps);free=w>0&ratio>=max(ratio(w>0))-1e-7;
    end
    assert(any(free));slope=zeros(size(base.gen,1),1);slope(use(free))=w(free)/sum(w(free));
    D(:,g)=D(:,g)+ctx.generator_map*slope/base.baseMVA;
end
dI_da=ctx.series_operator*spdiags(1j*V,0,n,n);
dI_dm=ctx.series_operator*spdiags(V./abs(V),0,n,n);
factor=spdiags(2*base.baseMVA*base.branch(:,3),0,size(base.branch,1),size(base.branch,1));
dLoss_da=factor*real(spdiags(conj(I),0,numel(I),numel(I))*dI_da);
dLoss_dm=factor*real(spdiags(conj(I),0,numel(I),numel(I))*dI_dm);
dSpec_da=D*(ctx.ownership*dLoss_da);dSpec_dm=D*(ctx.ownership*dLoss_dm);
[dNet_da,dNet_dm]=dSbus_dV(ctx.Y,V);
da=dNet_da-dSpec_da;dm=dNet_dm-dSpec_dm;
J=[real(da(ctx.pvpq,ctx.pvpq)) real(dm(ctx.pvpq,ctx.pq)); ...
   imag(da(ctx.pq,ctx.pvpq)) imag(dm(ctx.pq,ctx.pq))];
state.dSspec_dVa=dSpec_da;state.dSspec_dVm=dSpec_dm;
state.active_identity_dVa_MW=base.baseMVA*sum(real(da),1);
state.active_identity_dVm_MW=base.baseMVA*sum(real(dm),1);
end
