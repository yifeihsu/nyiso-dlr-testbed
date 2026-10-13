function [result,audit,r,allocation]=ac_loss_solve(base,options)
%AC_LOSS_SOLVE Loss-inclusive NY demand and bounded external-area balancing.
% The source dispatch is held fixed in NY/HQ; external equivalents cover their
% own and NY-border losses. NY delivered demand excludes allocated NY losses.
if nargin<2,options=struct();end
defaults=struct('loss_mode','boundary_consistent','backend','compact','max_loss_iterations',60, ...
    'loss_tolerance_MW',1e-8,'damping',1,'initialization','DC_loss_seed');
names=fieldnames(defaults);for k=1:numel(names),if ~isfield(options,names{k}),options.(names{k})=defaults.(names{k});end,end
assert(any(strcmp(options.loss_mode,{'boundary_consistent','legacy_single_slack'})));
assert(any(strcmp(options.backend,{'compact','detailed'}))&&options.damping>0&&options.damping<=1);
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
persistent configured
if isempty(configured)
    addpath(fullfile(root,'scripts','nygrid_2025_compact_ac','core'));
    addpath(fullfile(root,'scripts','nygrid_2025_ac_system','ac_validation'));
    addpath(fullfile(root,'scripts','nygrid_2025_ac_system','thermal'));
    configured=true;
end
p=ac_loss_prepare_policy(base);c=compact_ac_build(base);
assert(numel(c.retained_bus_ids)==148&&isempty(c.promoted_bus_ids));
assert(strcmp(c.source_fingerprint,compact_ac_source_fingerprint(base,c.retained_bus_ids)) ...
    &&strcmp(c.operator_fingerprint,compact_ac_operator_fingerprint(c)));
opt=mpoption('model','AC','pf.alg','NR','pf.tol',1e-10,'pf.nr.max_it',50,'pf.enforce_q_lims',0, ...
    'exp.use_legacy_core',1,'verbose',0,'out.all',0);
budget=zeros(14,1);V=[];trace=struct([]);status='maximum_loss_iterations';complete=false;
clock=tic;NR_iterations=0;last_residual=Inf;alpha=options.damping;
if strcmp(options.loss_mode,'boundary_consistent')&&strcmp(options.initialization,'DC_loss_seed')
    seed=rundcpf(base,mpoption(opt,'model','DC'));assert(seed.success);
    % Active-flow I^2R is an initializer only; final budgets use solved AC I.
    loss0=base.branch(:,3).*seed.branch(:,14).^2/base.baseMVA;
    budget=p.loss_ownership*accumarray(p.parent,loss0,[size(p.loss_ownership,2) 1]);
    scale=min([1;.8*p.group_gross_PD(1:11)./max(budget(1:11),eps)]);
    for g=12:14
        use=p.external_gen_group==g;scale=min(scale,.8*sum(p.Pmax(use)-p.baseline_PG(use))/max(budget(g),eps));
    end
    budget=budget*scale;V=seed.bus(:,8).*exp(1j*deg2rad(seed.bus(:,9)));
end
last_input=base;last_applied=struct();budget_detail=struct();actual_budget=nan(14,1);
good_budget=[];good_actual=[];good_V=[];zero_retried=false;
for outer=1:options.max_loss_iterations
    try
        if strcmp(options.loss_mode,'boundary_consistent')
            [m,applied]=ac_loss_apply_budget(base,p,budget);
        else
            m=base;applied=struct('applied_budget_MW',zeros(14,1),'NY_served_to_gross_ratio',ones(11,1), ...
                'allocated_generator_increment_MW',zeros(size(base.gen,1),1));
        end
    catch err
        if ~startsWith(err.identifier,'acLoss:'),rethrow(err);end
        status=err.identifier;
        trace=[trace;trace_entry(outer,0,false,NaN,NaN,NaN,budget,p,alpha,status)]; %#ok<AGROW>
        [retry,budget,V,alpha,zero_retried]=retry_step(good_budget,good_actual,good_V,alpha,options,zero_retried);
        if retry,continue;else,break;end
    end
    if strcmp(options.backend,'compact')
        [r,V,inner]=ac_loss_inner_pf(m,c,V,opt);
    else
        if ~isempty(V),m.bus(:,8)=abs(V);m.bus(:,9)=rad2deg(angle(V));end
        r=runpf(m,opt);V=r.bus(:,8).*exp(1j*deg2rad(r.bus(:,9)));
        inner=struct('success',r.success,'iterations',r.iterations,'retained_bus_count',size(m.bus,1), ...
            'full_network_Newton_used',true,'elapsed_seconds',r.et);
    end
    last_input=m;last_applied=applied;NR_iterations=NR_iterations+inner.iterations;
    if ~r.success
        status='AC_NR_failed';
        trace=[trace;trace_entry(outer,inner.iterations,false,NaN,NaN,NaN,budget,p,alpha,status)]; %#ok<AGROW>
        [retry,budget,V,alpha,zero_retried]=retry_step(good_budget,good_actual,good_V,alpha,options,zero_retried);
        if retry,continue;else,break;end
    end
    [actual_budget,budget_detail]=ac_loss_budget(m,r,p);
    residual=max(abs(actual_budget-budget));reference_residual=r.gen(p.reference,2)-p.baseline_PG(p.reference);
    t=trace_entry(outer,inner.iterations,true,residual,reference_residual,sum(actual_budget),budget,p,alpha,'iterate');
    trace=[trace;t]; %#ok<AGROW>
    if strcmp(options.loss_mode,'legacy_single_slack'),complete=true;status='legacy_comparison_only';break;end
    if residual<options.loss_tolerance_MW&&abs(reference_residual)<1e-7
        complete=true;status='loss_accounting_converged';break;
    end
    good_budget=budget;good_actual=actual_budget;good_V=V;
    if residual>1.15*last_residual,alpha=max(min(.15,options.damping),alpha/2);else,alpha=min(options.damping,alpha*1.2);end
    budget=budget+alpha*(actual_budget-budget);last_residual=residual;
end
assert(exist('r','var')==1,'acLoss:NoSolvedIterate','Loss initialization produced no PF iterate.');
[result,audit,r,allocation]=ac_loss_finalize(base,last_input,r,p,c,options,complete,status,trace,actual_budget,budget_detail,last_applied,NR_iterations,toc(clock));
end

function [retry,budget,V,alpha,zero_retried]=retry_step(good_budget,good_actual,good_V,alpha,options,zero_retried)
% Source-only continuation: retry a smaller accounting update from the last
% converged point. Never clip the final loss budget or alter source targets.
retry=false;budget=[];V=[];
if ~strcmp(options.loss_mode,'boundary_consistent'),return;end
if isempty(good_budget)
    if ~zero_retried
        budget=zeros(14,1);zero_retried=true;retry=true;
    end
else
    alpha=alpha/2;
    if alpha>=1e-4
        budget=good_budget+alpha*(good_actual-good_budget);V=good_V;retry=true;
    end
end
end

function t=trace_entry(outer,it,success,residual,ref,loss,budget,p,alpha,reason)
t=struct('loss_iteration',outer,'NR_iterations',it,'NR_success',logical(success),'budget_residual_MW',residual, ...
    'reference_PG_change_MW',ref,'actual_total_loss_MW',loss,'applied_NY_loss_MW',sum(budget(1:11)), ...
    'applied_external_loss_MW',sum(budget(12:14)), ...
    'minimum_NY_served_fraction',min(1-budget(1:11)./p.group_gross_PD(1:11)), ...
    'damping',alpha,'termination_reason',reason);
end
