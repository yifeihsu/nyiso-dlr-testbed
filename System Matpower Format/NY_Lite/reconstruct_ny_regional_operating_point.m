function out=reconstruct_ny_regional_operating_point(build,options)
%RECONSTRUCT_NY_REGIONAL_OPERATING_POINT Fixed-network bounded prior-only OPF.
% All source loads, fixed boundary P/Q, native capability, branch parameters
% and shunts are fixed. No voltage, reactive, thermal or balance relaxation.
% Retain failed optimizer iterates for diagnosis, never as qualified states.
if nargin<2,options=struct();end
if ~isfield(options,'solver'),options.solver='MIPS';end
if ~isfield(options,'opf_start'),options.opf_start=0;end
define_constants;c=build.candidate;
p=build.allocation.Pg_prior_mw;sigma=build.allocation.Pg_sigma_mw;ng=size(c.gen,1);
assert(all(isfinite(c.gen(:,[PMIN PMAX QMIN QMAX])),'all')&& ...
    numel(p)==ng&&all(isfinite(p))&&numel(sigma)==ng&&all(isfinite(sigma)&sigma>0), ...
    'ny_region:OperatingBounds','Finite generator bounds and valid priors are required.');
c.gencost=[2*ones(ng,1),zeros(ng,2),3*ones(ng,1),1./sigma.^2,-2*p./sigma.^2,(p./sigma).^2];
ao=struct('generator_keys',build.generator_keys,'branch_keys',build.branch_keys);
solver_error="";state_origin="returned_optimizer_state";
try
    opts=mpoption('verbose',0,'out.all',0,'opf.ac.solver',options.solver, ...
        'opf.start',options.opf_start,'opf.violation',1e-8,'mips.feastol',1e-9);
    r=runopf(c,opts);a=audit_ny_ac_reference(r,ao);
catch err
    solver_error=string(err.identifier)+": "+string(err.message);
    % This is explicitly an input-state diagnostic, not a solver iterate.
    r=c;r.branch(:,PF:QT)=0;r.success=false;
    a=audit_ny_ac_reference(r,ao);state_origin="initial_input_after_solver_exception";
end
pf=r;pf.success=false;replay_error="not_attempted_bounded_audit_failed";
if a.passed
    try
        pf=runpf(r,mpoption('verbose',0,'out.all',0,'pf.enforce_q_lims',1,'pf.tol',1e-10));
        replay_error="";
    catch err
        replay_error=string(err.identifier)+": "+string(err.message);
    end
end
pa=audit_ny_ac_reference(pf,ao);
on=c.gen(:,GEN_STATUS)>0;
dp=max(abs(pf.gen(on,PG)-r.gen(on,PG)));dv=max(abs(pf.bus(:,VM)-r.bus(:,VM)));
hardware=isequal(r.bus(:,[BUS_I PD QD GS BS BASE_KV VMIN VMAX]),c.bus(:,[BUS_I PD QD GS BS BASE_KV VMIN VMAX]))&& ...
    isequal(r.branch(:,1:13),c.branch(:,1:13))&& ...
    isequal(r.gen(:,[GEN_BUS GEN_STATUS PMIN PMAX QMIN QMAX]),c.gen(:,[GEN_BUS GEN_STATUS PMIN PMAX QMIN QMAX]));
passed=a.passed&&pa.passed&&hardware&&dp<1e-3&&dv<1e-4&& ...
    abs(pa.summary.active_balance_error_mw)<1e-3;
out=struct('result',r,'bounded_audit',a,'fixed_input_pf',pf,'replay_audit',pa, ...
    'replay_error',replay_error,'max_replay_dispatch_adjustment_mw',dp, ...
    'max_replay_voltage_adjustment_pu',dv,'network_and_injections_frozen',hardware, ...
    'solver',string(options.solver),'opf_start',options.opf_start, ...
    'solver_error',solver_error,'diagnostic_state_origin',state_origin, ...
    'electrical_baseline_qualified',passed,'minimum_relaxation_used',false, ...
    'fictitious_active_injection_mw',0,'internal_interface_fit_used',false, ...
    'qualification_scope','assumed_2019_NPCC_PERFORM_regional_candidate_only', ...
    'contemporary_validation_coverage','not_evaluated','dlr_ready',false);
end
