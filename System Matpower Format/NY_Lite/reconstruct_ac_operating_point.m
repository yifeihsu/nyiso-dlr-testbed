function out = reconstruct_ac_operating_point(source, controls, options)
%RECONSTRUCT_AC_OPERATING_POINT Bounded AC reconstruction with fixed network.
% controls.Pg_prior_mw and Pg_sigma_mw distinguish priors from observations.
% Optional operator_from/operator_to matrices meter explicit branch terminals;
% target_mw and tolerance_mw constrain their aggregate, never individual ties.
% All generators (including the angle-reference bus) obey finite P/Q limits.
% No economic objective, network fit, added support, or load shedding occurs.
if nargin < 2, controls = struct(); end
if nargin < 3, options = struct(); end
options = defaults(options, 'max_iterations', 500, 'verbose', false, ...
    'tolerance', 1e-6, 'voltage_sigma', 0.05, 'reactive_sigma_mvar', 100);
[~,~,REF,~,~,BUS_TYPE,PD,QD,GS,~,~,VM,VA,~,~,VMAX,VMIN]=idx_bus;
[GEN_BUS,PG,QG,QMAX,QMIN,VG,~,GEN_STATUS,PMAX,PMIN]=idx_gen;
[F_BUS,T_BUS,~,~,~,RATE_A,~,~,~,~,~,PF,QF,PT,QT,~,~,ANGMIN,ANGMAX]=idx_brch;
assert(~isfield(source, 'A') && ~isfield(source, 'userfcn') && ...
    ~isfield(source, 'dcline'), 'reconstruct_ac_operating_point:Unsupported', ...
    'Explicitly map custom constraints and DC devices before reconstruction.');
assert(all(isfinite(source.gen(:, [PMIN PMAX QMIN QMAX])), 'all'), ...
    'reconstruct_ac_operating_point:Unbounded', 'Finite P/Q bounds required.');
assert(all(source.gen(:, PMIN) <= source.gen(:, PMAX)) && ...
    all(source.gen(:, QMIN) <= source.gen(:, QMAX)), ...
    'reconstruct_ac_operating_point:Bounds', 'Inverted generator bounds.');
if size(source.gen,2)>=16
    assert(~any(source.gen(:,11:16),'all'), ...
        'reconstruct_ac_operating_point:CapabilityCurve', ...
        'Convert machine capability curves to the documented conservative P/Q envelope first.');
end
external = source;
m = ext2int(source); n = size(m.bus,1); g = size(m.gen,1);
assert(~any(source.bus(m.order.bus.status.off,[PD QD GS]),'all'), ...
    'reconstruct_ac_operating_point:ExcludedInjection', ...
    'An excluded bus carries load or conductance; account for it explicitly.');
assert(g > 0, 'No online generators.');
on_gen = m.order.gen.status.on(m.order.gen.i2e);
controls = defaults(controls, 'Pg_prior_mw', source.gen(:,PG), ...
    'Pg_sigma_mw', max(50, 0.25*(source.gen(:,PMAX)-source.gen(:,PMIN))));
controls.Pg_prior_mw=controls.Pg_prior_mw(:);
controls.Pg_sigma_mw=controls.Pg_sigma_mw(:);
assert(numel(controls.Pg_prior_mw)==size(source.gen,1) && ...
    numel(controls.Pg_sigma_mw)==size(source.gen,1) && ...
    all(isfinite(controls.Pg_prior_mw)) && ...
    all(isfinite(controls.Pg_sigma_mw) & controls.Pg_sigma_mw>0), ...
    'Invalid generation priors or uncertainties.');
base = m.baseMVA;
prior = controls.Pg_prior_mw(on_gen)/base;
sigma = controls.Pg_sigma_mw(on_gen)/base;
[Y,Yf,Yt] = makeYbus(m);
Cg = sparse(m.gen(:,GEN_BUS),1:g,1,n,g);
load_pq = (m.bus(:,PD)+1i*m.bus(:,QD))/base;
refs = find(m.bus(:,BUS_TYPE)==REF);
assert(numel(refs)==1, 'Exactly one connected-network angle reference required.');
va0 = m.bus(:,VA)*pi/180; va0 = va0-va0(refs);
vm0 = min(m.bus(:,VMAX),max(m.bus(:,VMIN),m.bus(:,VM)));
x0 = [va0;vm0;min(m.gen(:,PMAX)/base,max(m.gen(:,PMIN)/base,prior)); ...
    min(m.gen(:,QMAX)/base,max(m.gen(:,QMIN)/base,m.gen(:,QG)/base))];
% A bounded MATPOWER reconstruction seeds large cases before regional flow
% constraints are added. Its quadratic cost penalizes prior deviation only.
seed_success=false;
if n>30
    seed=m; seed=rmfield(seed,'order');
    seed.gencost=[2*ones(g,1),zeros(g,2),3*ones(g,1), ...
        1./(sigma*base).^2,-2*prior*base./(sigma*base).^2, ...
        (prior./sigma).^2];
    try
        seed=runopf(seed,mpoption('verbose',0,'out.all',0,'opf.ac.solver','MIPS'));
        seed_success=logical(seed.success);
        if seed_success
            angles=seed.bus(:,VA)*pi/180;
            x0=[angles-angles(refs);seed.bus(:,VM);seed.gen(:,PG)/base;seed.gen(:,QG)/base];
        end
    catch
        seed_success=false;
    end
end
lb = [-inf(n,1);m.bus(:,VMIN);m.gen(:,PMIN)/base;m.gen(:,QMIN)/base];
ub = [inf(n,1);m.bus(:,VMAX);m.gen(:,PMAX)/base;m.gen(:,QMAX)/base];
lb(refs)=0; ub(refs)=0;
nl=size(m.branch,1); rows=m.order.branch.status.on;
if isfield(controls,'operator_from')
    assert(isfield(controls,'operator_to') && ...
        size(controls.operator_from,2)==size(source.branch,1) && ...
        isequal(size(controls.operator_from),size(controls.operator_to)), ...
        'Operator must identify both branch terminal conventions.');
    Af=controls.operator_from(:,rows); At=controls.operator_to(:,rows);
    target=controls.target_mw(:)/base; band=controls.tolerance_mw(:)/base;
    assert(size(Af,1)==numel(target) && numel(band)==numel(target) && ...
        all(isfinite([target;band])) && all(band>=0) && ...
        all(isfinite([nonzeros(Af);nonzeros(At)])), 'Invalid operator targets.');
else
    Af=sparse(0,nl); At=Af; target=zeros(0,1); band=target;
end
limited=find(m.branch(:,RATE_A)>0 & m.branch(:,RATE_A)<1e10);
rate=m.branch(limited,RATE_A)/base;
% Use MATPOWER's zero/zero and one-sided angle-limit conventions exactly.
[D,angle_min,angle_max]=makeAang(base,m.branch,n,mpoption);
al=isfinite(angle_min);au=isfinite(angle_max);
vref=min(m.bus(:,VMAX),max(m.bus(:,VMIN),ones(n,1)));
qprior=m.gen(:,QG)/base; qs=options.reactive_sigma_mvar/base;
opts=optimoptions('fmincon','Algorithm','interior-point','Display','off', ...
    'SpecifyObjectiveGradient',true,'SpecifyConstraintGradient',true, ...
    'HessianApproximation','lbfgs','MaxIterations',options.max_iterations, ...
    'ConstraintTolerance',options.tolerance/10,'OptimalityTolerance',1e-6, ...
    'StepTolerance',1e-12);
[x,cost,exitflag,solver]=fmincon(@objective,x0,[],[],[],[],lb,ub,@constraints,opts);
[initial_ineq,initial_eq]=constraints(x0);
[ineq,eq]=constraints(x);
constraint_error=max([0;ineq;abs(eq);lb-x;x-ub]);
V=x(n+1:2*n).*exp(1i*x(1:n));
m.bus(:,VM)=abs(V); m.bus(:,VA)=angle(V)*180/pi;
m.gen(:,PG)=x(2*n+1:2*n+g)*base; m.gen(:,QG)=x(2*n+g+1:end)*base;
m.gen(:,VG)=m.bus(m.gen(:,GEN_BUS),VM);
Sf=V(m.branch(:,F_BUS)).*conj(Yf*V)*base;
St=V(m.branch(:,T_BUS)).*conj(Yt*V)*base;
m.branch(:,[PF QF PT QT])=[real(Sf) imag(Sf) real(St) imag(St)];
m.success=constraint_error<=options.tolerance && exitflag>0;
result=int2ext(m); result.success=m.success;
% A fixed-input PF independently checks the reconstructed P dispatch and V setpoints.
pf_error="";pf=result;pf.success=false;
if result.success
    try
        pf=runpf(result,mpoption('verbose',0,'out.all',0,'pf.enforce_q_lims',1));
    catch err
        pf_error=string(err.identifier)+": "+string(err.message);
    end
else
    pf_error="Not attempted: bounded AC reconstruction is infeasible or unconverged.";
end
fixed_pf_pass=pf.success && all(pf.bus(:,VM)>=pf.bus(:,VMIN)-1e-5) && ...
    all(pf.bus(:,VM)<=pf.bus(:,VMAX)+1e-5);
online=result.gen(:,GEN_STATUS)>0;
if fixed_pf_pass
    fixed_pf_pass=all(pf.gen(online,PG)>=result.gen(online,PMIN)-1e-3) && ...
        all(pf.gen(online,PG)<=result.gen(online,PMAX)+1e-3) && ...
        all(pf.gen(online,QG)>=result.gen(online,QMIN)-1e-3) && ...
        all(pf.gen(online,QG)<=result.gen(online,QMAX)+1e-3) && ...
        max(abs(pf.gen(online,PG)-result.gen(online,PG)))<1e-3 && ...
        max(abs(pf.bus(:,VM)-result.bus(:,VM)))<1e-4;
    checked=ext2int(pf);av=checked.bus(:,VA)*pi/180;
    xp=[av-av(refs);checked.bus(:,VM);checked.gen(:,PG)/base;checked.gen(:,QG)/base];
    [ci,ce]=constraints(xp);
    fixed_pf_pass=fixed_pf_pass && max([0;ci;abs(ce);lb-xp;xp-ub])<=1e-5;
end
out=struct('result',result,'fixed_input_pf',pf, ...
    'success',result.success && fixed_pf_pass,'solver_exitflag',exitflag, ...
    'solver',solver,'objective',cost,'max_constraint_error_pu',constraint_error, ...
    'bounded_seed_success',seed_success, ...
    'initial_constraint_error_pu',max([0;initial_ineq;abs(initial_eq)]), ...
    'initial_nodal_error_pu',max(abs(initial_eq)), ...
    'final_nodal_error_pu',max(abs(eq)), ...
    'initial_operator_mw',target*base+base*(initial_ineq(1:numel(target))+band), ...
    'fixed_input_pf_pass',fixed_pf_pass,'fixed_input_pf_error',pf_error,'promotion_eligible',false, ...
    'dispatch_movement_mw',sum(abs(result.gen(online,PG)-controls.Pg_prior_mw(online))), ...
    'network_parameters_frozen',isequaln(external.branch(:,1:13),result.branch(:,1:13)), ...
    'operator_mw',base*(Af*real(Sf/base)+At*real(St/base)), ...
    'network_loss_mw',sum(real(Sf+St)), ...
    'bus_shunt_loss_mw',sum(result.bus(:,GS).*result.bus(:,VM).^2));
out.accounting_error_mw=sum(result.gen(online,PG))-sum(result.bus(:,PD))- ...
    out.network_loss_mw-out.bus_shunt_loss_mw;
out.success=out.success && abs(out.accounting_error_mw)<=base*options.tolerance*n;
if options.verbose
    fprintf('AC reconstruction: feasible=%d PF=%d movement=%.3f MW mismatch=%.3g pu\n', ...
        result.success,fixed_pf_pass,out.dispatch_movement_mw,constraint_error);
end

    function [f,df]=objective(z)
        dv=(z(n+1:2*n)-vref)/options.voltage_sigma;
        dp=(z(2*n+1:2*n+g)-prior)./sigma;
        dq=(z(2*n+g+1:end)-qprior)/qs;
        f=sum(dp.^2)+0.01*sum(dq.^2)+0.01*sum(dv.^2);
        df=[zeros(n,1);0.02*dv/options.voltage_sigma;2*dp./sigma;0.02*dq/qs];
    end
    function [c,ceq,dc,dceq]=constraints(z)
        vv=z(n+1:2*n).*exp(1i*z(1:n));
        mismatch=vv.*conj(Y*vv)+load_pq-Cg*(z(2*n+1:2*n+g)+1i*z(2*n+g+1:end));
        ceq=[real(mismatch);imag(mismatch)];
        [fa,fm,ta,tm,sf,st]=dSbr_dV(m.branch,Yf,Yt,vv);
        flow=Af*real(sf)+At*real(st);
        ang=D*z(1:n);
        c=[flow-target-band;target-flow-band; ...
            abs(sf(limited)).^2-rate.^2;abs(st(limited)).^2-rate.^2; ...
            ang(au)-angle_max(au);angle_min(al)-ang(al)];
        if nargout>2
            [sa,sm]=dSbus_dV(Y,vv);
            dceq=[real(sa) real(sm) -Cg sparse(n,g); ...
                imag(sa) imag(sm) sparse(n,g) -Cg]';
            J=[Af*real(fa)+At*real(ta),Af*real(fm)+At*real(tm)];
            Js=2*real(spdiags(conj(sf(limited)),0,numel(limited),numel(limited))*[fa(limited,:) fm(limited,:)]);
            Jt=2*real(spdiags(conj(st(limited)),0,numel(limited),numel(limited))*[ta(limited,:) tm(limited,:)]);
            Jv=[J;-J;Js;Jt;D(au,:) sparse(nnz(au),n);-D(al,:) sparse(nnz(al),n)];
            dc=[Jv sparse(size(Jv,1),2*g)]';
        end
    end
end
function s=defaults(s,varargin)
for k=1:2:numel(varargin)
    if ~isfield(s,varargin{k}),s.(varargin{k})=varargin{k+1};end
end
end
