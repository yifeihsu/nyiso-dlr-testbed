function out=solve_dlr_steady_operating_point(reference,realizations,weather,options)
%SOLVE_DLR_STEADY_OPERATING_POINT Bounded AC dispatch with consistent R(T).
% Keeps observed demand/boundary injections fixed. Exact series-current
% inequalities enforce assumed ampacity; original equipment MVA ceilings
% remain separate. Objective penalizes movement from the supplied dispatch;
% it is not an observed economic cost. Temperature iteration uses the same
% conductor current and resistance as the electrical network.
if nargin<4,options=struct();end
if ~isfield(options,'max_iterations'),options.max_iterations=40;end
if ~isfield(options,'temperature_tolerance_c'),options.temperature_tolerance_c=.005;end
if ~isfield(options,'solver'),options.solver='MIPS';end
assert(isscalar(options.max_iterations)&&isfinite(options.max_iterations)&&options.max_iterations>=1 ...
    &&options.max_iterations<=200&&options.max_iterations==fix(options.max_iterations) ...
    &&isscalar(options.temperature_tolerance_c)&&isfinite(options.temperature_tolerance_c) ...
    &&options.temperature_tolerance_c>0&&options.temperature_tolerance_c<=.01, ...
    'dlr:Options','Use1..200 iterations and a temperature tolerance in(0,.01]C.');
assert(height(realizations)>0&&all(realizations.research_thermal_eligible)&&~any(realizations.length_requires_review), ...
    'dlr:UnqualifiedRealization','Resolve all realization review flags before a thermal operating solve.');
lib=dlr_conductor_library;n=height(realizations);[ok,ci]=ismember(realizations.conductor_code,lib.conductor_code);assert(all(ok));
assert(istable(weather)&&(height(weather)==1||height(weather)==n));
amps=zeros(n,1);
for j=1:n
    a=dlr_steady_ampacity(lib(ci(j),:),weather(min(j,height(weather)),:));
    assert(a.zero_current_thermally_feasible&&a.ampacity_amp>0,'dlr:WeatherInfeasible','Weather alone exceeds the assumed thermal limit.');
    amps(j)=a.ampacity_amp;
end
temperature=lib.temperature_limit_c(ci);iterations=table();converged=false;
m=reference;ng=size(m.gen,1);p=m.gen(:,2);scale=max(100,.25*(m.gen(:,9)-m.gen(:,10)));
% A finite Q-dispatch penalty removes unconstrained sharing directions among
% colocated equivalent generators without changing any capability bounds.
q=m.gen(:,3);qscale=max(100,.25*(m.gen(:,4)-m.gen(:,5)));
m.gencost=[2*ones(ng,1),zeros(ng,2),3*ones(ng,1),1./scale.^2,-2*p./scale.^2,(p./scale).^2; ...
    2*ones(ng,1),zeros(ng,2),3*ones(ng,1),.01./qscale.^2,-.02*q./qscale.^2,.01*(q./qscale).^2];
last=m;last.success=false;current=table();audit=[];solver_error="";last_temperature=temperature;
for k=1:options.max_iterations
    m=apply_dlr_temperature_resistance(m,realizations,temperature);
    m.branch(realizations.branch_row,6)=min(realizations.inherited_rating_a_mva,realizations.equipment_limit_mva);
    trial=add_dlr_series_current_constraints(m,realizations,amps);
    try
        opts=mpoption('verbose',0,'out.all',0,'opf.ac.solver',options.solver,'opf.start',0, ...
            'opf.violation',1e-8,'mips.feastol',1e-9,'mips.max_it',500);opts.mips.cost_mult=1;
        result=runopf(trial,opts);
    catch e,solver_error=string(e.identifier)+": "+string(e.message);break;end
    result=plain(result);audit=audit_ny_ac_reference(result);last=result;last_temperature=temperature;
    if ~audit.passed,solver_error="bounded_AC_audit_failed";break;end
    current=dlr_series_current_audit(result,realizations,temperature);
    equilibrium=zeros(n,1);heat=zeros(n,1);
    for j=1:n
        w=weather(min(j,height(weather)),:);c=lib(ci(j),:);i=current.subconductor_current_amp(j);
        equilibrium(j)=fzero(@(t)net(t,i,c,w),[w.ambient_c-1 200]);
        heat(j)=net(temperature(j),i,c,w);
    end
    error_c=max(abs(equilibrium-temperature));ratio=max(current.subconductor_current_amp./amps);
    iterations=[iterations;table(k,error_c,max(equilibrium),max(abs(heat)),ratio,audit.passed, ...
        'VariableNames',{'iteration','max_temperature_fixed_point_error_c','max_equilibrium_temperature_c', ...
        'max_heat_balance_residual_w_m','max_series_ampacity_fraction','bounded_AC_pass'})]; %#ok<AGROW>
    if error_c<options.temperature_tolerance_c&&ratio<=1+1e-6
        converged=true;break;
    end
    temperature=.5*temperature+.5*equilibrium;m=result;
end
temperature=last_temperature;
pf=last;pf_audit=[];current_pf=table();thermal_audit=table();replay_pass=false;
if converged
    pf=plain(runpf(last,mpoption('verbose',0,'out.all',0,'pf.enforce_q_lims',1,'pf.tol',1e-10)));
    pf_audit=audit_ny_ac_reference(pf);current_pf=dlr_series_current_audit(pf,realizations,temperature);
    replay_pass=pf_audit.passed&&max(abs(pf.gen(:,2)-last.gen(:,2)))<1e-3 ...
        &&max(abs(pf.bus(:,8)-last.bus(:,8)))<1e-4&&max(current_pf.subconductor_current_amp./amps)<=1+1e-6;
    heat=zeros(n,1);eq=zeros(n,1);
    for j=1:n
        w=weather(min(j,height(weather)),:);c=lib(ci(j),:);i=current_pf.subconductor_current_amp(j);
        heat(j)=net(temperature(j),i,c,w);eq(j)=fzero(@(t)net(t,i,c,w),[w.ambient_c-1 200]);
    end
    thermpass=abs(heat)<=.025&abs(eq-temperature)<=options.temperature_tolerance_c ...
        &temperature<=lib.temperature_limit_c(ci)+options.temperature_tolerance_c;
    thermal_audit=table(realizations.branch_key,temperature,eq,heat,lib.temperature_limit_c(ci),thermpass, ...
        'VariableNames',{'branch_key','temperature_c','independent_PF_equilibrium_c','heat_residual_w_m','temperature_limit_c','passed'});
    replay_pass=replay_pass&&all(thermpass);
end
out=struct('result',pf,'bounded_result',last,'bounded_audit',audit,'replay_audit',pf_audit, ...
    'current_audit',current_pf,'temperature_c',temperature,'ampacity_subconductor_amp',amps, ...
    'thermal_audit',thermal_audit, ...
    'weather',weather,'iterations',iterations,'converged',converged,'independent_PF_pass',replay_pass, ...
    'synthetic_electrothermal_qualified',converged&&replay_pass,'solver_error',solver_error, ...
    'dispatch_L1_change_mw',sum(abs(pf.gen(:,2)-reference.gen(:,2))), ...
    'physical_asset_thermal_validation',false,'weather_is_observed',false);
end
function y=net(t,i,c,w),h=dlr_heat_balance(t,i,c,w);y=h.net_w_m;end
function m=plain(m)
keep=intersect(fieldnames(m),{'version','baseMVA','bus','gen','branch','gencost','bus_name','success','userdata'});
m=rmfield(m,setdiff(fieldnames(m),keep));
end
