function out=fit_compact_partial_spc_operating_snapshot(snapshot,options)
%FIT_COMPACT_PARTIAL_SPC_OPERATING_SNAPSHOT Strict IPOPT numerical variant.
% Training hours may fit declared interface proxies. Heldout hours use only
% independent/frozen training generation priors plus matched load/boundary P.
if nargin<2,options=struct();end
if ismember('dataset_split',snapshot.snapshot.Properties.VariableNames),split=snapshot.snapshot.dataset_split;
else,split=snapshot.snapshot.split;end
train=ismember(lower(string(split)),["train","training"]);
if ismember('default_campaign_interface_fit_allowed',snapshot.snapshot.Properties.VariableNames)
    train=train&&snapshot.snapshot.default_campaign_interface_fit_allowed;
end
assert(isscalar(train));
if ~isfield(options,'fit_interfaces'),options.fit_interfaces=train;end
assert(~options.fit_interfaces||train,'compact_fit:HeldoutLeakage','Heldout interface targets cannot enter the optimizer.');
if ~isfield(options,'solver'),options.solver='MIPS';end
if ~isfield(options,'opf_start'),options.opf_start=0;end
if ~isfield(options,'interface_scale_mw'),options.interface_scale_mw=500;end
if ~isfield(options,'mips_cost_multiplier'),options.mips_cost_multiplier=1;end
assert(isscalar(options.mips_cost_multiplier)&&isfinite(options.mips_cost_multiplier)&&options.mips_cost_multiplier>0);
if ~isfield(options,'prior_weight'),options.prior_weight=1;if options.fit_interfaces,options.prior_weight=.001;end,end
assert(isscalar(options.prior_weight)&&isfinite(options.prior_weight)&&options.prior_weight>0);
define_constants;m=snapshot.candidate;p=snapshot.Pg_prior_mw;s=snapshot.Pg_sigma_mw;ng=numel(p);w=options.prior_weight;
m.gencost=[2*ones(ng,1),zeros(ng,2),3*ones(ng,1),w./s.^2,-2*w*p./s.^2,w*(p./s).^2];
if options.fit_interfaces,m=add_compact_interface_cost(m,snapshot.operators,snapshot.interface_targets,options.interface_scale_mw);end
audit_options=struct('generator_keys',snapshot.generator_keys,'branch_keys',snapshot.branch_keys);
solver_error="";strict_ipopt_options=struct();r=m;r.success=false;r.branch(:,PF:QT)=0;
try
    opts=mpoption('verbose',0,'out.all',0,'opf.ac.solver',options.solver, ...
        'opf.start',options.opf_start,'opf.violation',1e-8,'mips.feastol',1e-9,'mips.max_it',500);
    opts.mips.cost_mult=options.mips_cost_multiplier;
    % Preserve the frozen objective, MIPS settings and physical audit gates.
    % Explicit strict IPOPT tolerances prevent acceptable-status termination
    % with a nodal residual above the unchanged physical-unit audit threshold.
    strict_ipopt_options=struct();
    if strcmpi(string(options.solver),"IPOPT")
        strict_ipopt_options=struct('tol',1e-11,'constr_viol_tol',1e-11, ...
            'dual_inf_tol',1e-11,'compl_inf_tol',1e-11,'acceptable_tol',1e-11, ...
            'acceptable_constr_viol_tol',1e-11,'acceptable_dual_inf_tol',1e-11, ...
            'acceptable_compl_inf_tol',1e-11,'acceptable_obj_change_tol',1e-11, ...
            'acceptable_iter',0,'max_iter',1000,'bound_relax_factor',0);
        opts.ipopt.opts=strict_ipopt_options;
    end
    r=runopf(m,opts);
catch err,solver_error=string(err.identifier)+": "+string(err.message);end
r=plain(r);a=audit_ny_ac_reference(r,audit_options);pf=r;pf.success=false;replay_error="bounded_audit_failed";
if a.passed
    try
        pf=runpf(r,mpoption('verbose',0,'out.all',0,'pf.enforce_q_lims',1,'pf.tol',1e-10));
        replay_error="";
    catch err,replay_error=string(err.identifier)+": "+string(err.message);end
end
pf=plain(pf);pa=audit_ny_ac_reference(pf,audit_options);
hardware=isequal(r.baseMVA,m.baseMVA)&&isequal(r.bus(:,[BUS_I PD QD GS BS BASE_KV VMIN VMAX]),m.bus(:,[BUS_I PD QD GS BS BASE_KV VMIN VMAX]))&& ...
    isequal(r.branch(:,1:13),m.branch(:,1:13))&&isequal(r.gen(:,[GEN_BUS GEN_STATUS PMIN PMAX QMIN QMAX]),m.gen(:,[GEN_BUS GEN_STATUS PMIN PMAX QMIN QMAX]));
hardware=hardware&&isequal(pf.baseMVA,m.baseMVA)&& ...
    isequal(pf.bus(:,[BUS_I PD QD GS BS BASE_KV VMIN VMAX]),m.bus(:,[BUS_I PD QD GS BS BASE_KV VMIN VMAX]))&& ...
    isequal(pf.branch(:,1:13),m.branch(:,1:13))&& ...
    isequal(pf.gen(:,[GEN_BUS GEN_STATUS PMIN PMAX QMIN QMAX]),m.gen(:,[GEN_BUS GEN_STATUS PMIN PMAX QMIN QMAX]));
on=m.gen(:,GEN_STATUS)>0;dp=max(abs(pf.gen(on,PG)-r.gen(on,PG)));dv=max(abs(pf.bus(:,VM)-r.bus(:,VM)));
qualified=a.passed&&pa.passed&&hardware&&dp<1e-3&&dv<1e-4&&snapshot.accounting_error_mw<1e-7;
op=snapshot.operators;flow=op.from_coefficients*pf.branch(:,PF)+op.to_coefficients*pf.branch(:,PT);
[ok,ix]=ismember(op.names,string(snapshot.interface_targets.interface_name));assert(all(ok));target=snapshot.interface_targets.target_flow_mw(ix);
residuals=table(op.names,flow,target,flow-target,abs(flow-target), ...
    repmat(logical(options.fit_interfaces),numel(flow),1),false(numel(flow),1), ...
    'VariableNames',{'interface_name','model_flow_mw','target_flow_mw','residual_mw','absolute_residual_mw','used_in_optimizer','exact_public_operator'});
out=struct('snapshot',snapshot,'input',plain(m),'bounded_result',r,'bounded_audit',a, ...
    'result',pf,'audit',pa,'residuals',residuals,'solver_error',solver_error,'replay_error',replay_error, ...
    'solver',string(options.solver),'opf_start',options.opf_start,'network_and_injections_frozen',hardware, ...
    'independent_replay_dispatch_adjustment_mw',dp,'independent_replay_voltage_adjustment_pu',dv, ...
    'internal_interface_fit_used',logical(options.fit_interfaces),'heldout_interface_leakage',false, ...
    'prior_weight',w,'interface_scale_mw',options.interface_scale_mw,'mips_cost_multiplier',options.mips_cost_multiplier, ...
    'electrical_baseline_qualified',qualified,'public_operator_exact',false,'dlr_ready',false, ...
    'mean_absolute_proxy_error_mw',mean(abs(flow-target)),'max_absolute_proxy_error_mw',max(abs(flow-target)), ...
    'bounds_relaxed',false,'fictitious_active_injection_mw',0, ...
    'strict_ipopt_options',strict_ipopt_options,'frozen_objective_and_physical_audit_preserved',true);
end
function m=plain(m)
keep=intersect(fieldnames(m),{'version','baseMVA','bus','gen','branch','gencost','bus_name','success','userdata'});
m=rmfield(m,setdiff(fieldnames(m),keep));
end
