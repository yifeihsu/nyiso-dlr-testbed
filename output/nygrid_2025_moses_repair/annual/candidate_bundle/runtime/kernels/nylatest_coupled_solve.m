function [result,audit,r,allocation]=nylatest_coupled_solve(base,options)
% Solve voltage and physically declared loss accounting simultaneously.
if nargin<2,options=struct();end
defaults=struct('backend','compact','loss_mode','boundary_consistent','max_coupled_iterations',80, ...
    'coupled_tolerance_pu',1e-10,'max_line_search',24);
names=fieldnames(defaults);for i=1:numel(names),if ~isfield(options,names{i}),options.(names{i})=defaults.(names{i});end,end
assert(strcmp(options.loss_mode,'boundary_consistent'));
started=tic;ctx=nylatest_coupled_context(base,options.backend);V=ctx.V0;trace=struct([]);
complete=false;status='coupled_iteration_limit';nr=0;
for iteration=1:options.max_coupled_iterations
    [F,J,s]=nylatest_coupled_equations(ctx,V,true);
    if ~s.valid,status=s.reason;break;end
    residual=norm(F,inf);
    t=struct('loss_iteration',iteration,'NR_iterations',1,'NR_success',false, ...
        'budget_residual_MW',0,'reference_PG_change_MW',NaN,'actual_total_loss_MW',sum(s.budget_MW), ...
        'applied_NY_loss_MW',sum(s.budget_MW(1:11)),'applied_external_loss_MW',sum(s.budget_MW(12:14)), ...
        'minimum_NY_served_fraction',min(s.applied.NY_served_to_gross_ratio),'damping',NaN, ...
        'termination_reason','coupled_step','power_mismatch_pu',residual,'line_search_trials',0);
    if residual<options.coupled_tolerance_pu
        complete=true;status='loss_accounting_converged';t.NR_success=true;t.termination_reason=status;
        trace=[trace;t];break; %#ok<AGROW>
    end
    step=-(J\F);nr=nr+1;
    if any(~isfinite(step)),status='nonfinite_coupled_step';t.termination_reason=status;trace=[trace;t];break;end %#ok<AGROW>
    Va=angle(V);Vm=abs(V);np=numel(ctx.pvpq);alpha=1;accepted=false;
    for ls=1:options.max_line_search
        va=Va;vm=Vm;va(ctx.pvpq)=va(ctx.pvpq)+alpha*step(1:np);vm(ctx.pq)=vm(ctx.pq)+alpha*step(np+1:end);
        if all(vm>1e-5)
            trial=vm.*exp(1j*va);[Ft,~,st]=nylatest_coupled_equations(ctx,trial,false);
            if st.valid&&norm(Ft,inf)<(1-1e-4*alpha)*residual
                V=trial;accepted=true;break;
            end
        end
        alpha=alpha/2;
    end
    t.damping=alpha;t.line_search_trials=ls;t.NR_success=accepted;
    if ~accepted
        status='coupled_line_search_failed';
        if min(s.applied.NY_served_to_gross_ratio)<1e-5,status='NY_delivered_load_domain_boundary';end
        t.termination_reason=status;
    end
    trace=[trace;t]; %#ok<AGROW>
    if ~accepted,break;end
end
[F,~,s]=nylatest_coupled_equations(ctx,V,false);
assert(s.valid,'acLoss:NoAdmissibleState','Initial voltage violates the declared loss accounting domain.');
if norm(F,inf)<options.coupled_tolerance_pu,complete=true;status='loss_accounting_converged';end
m=s.input;c=ctx.compact;p=ctx.policy;Vfull=ctx.voltage_lift*V;
mi=ext2int(m,ctx.opt);[ref,pv,pq]=bustypes(mi.bus,mi.gen);
if size(mi.branch,2)<17,mi.branch(:,17)=0;end
[ok,fr]=ismember(mi.order.bus.i2e,m.bus(:,1));assert(all(ok));active=mi.order.branch.status.on;
[mi.bus,mi.gen,mi.branch]=pfsoln(mi.baseMVA,mi.bus,mi.gen,mi.branch,c.Yfull(fr,fr), ...
    c.Yf_full(active,fr),c.Yt_full(active,fr),Vfull(fr),ref,pv,pq,ctx.opt);
mi.success=complete;mi.iterations=nr;mi.et=toc(started);r=int2ext(mi);
if ~isempty(r.order.gen.status.off),r.gen(r.order.gen.status.off,[2 3])=0;end
if ~isempty(r.order.branch.status.off),r.branch(r.order.branch.status.off,14:17)=0;end
[budget,detail]=nylatest_budget(m,r,p);
[result,audit,r,allocation]=nylatest_finalize(base,m,r,p,c,options,complete,status,trace,budget,detail,s.applied,nr,toc(started));
audit.loss_solver='simultaneous_voltage_and_loss_Newton';audit.final_coupled_mismatch_pu=norm(F,inf);
audit.active_global_identity_residual_MW=s.active_global_identity_residual_MW;
audit.global_infeasibility_claimed_from_failed_solve=false;
result.audit=audit;allocation.solver='simultaneous_voltage_and_loss_Newton';
r.userdata.ac_loss_allocation.audit=audit;
end
