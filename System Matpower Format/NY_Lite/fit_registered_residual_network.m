function out=fit_registered_residual_network(candidate, registry, target, options)
%FIT_REGISTERED_RESIDUAL_NETWORK Regularized passive port-admittance fit.
% target.bus_ids and target.Y define a same-vintage retained-terminal target;
% target.source identifies its source. Only explicitly registered residual
% R/X/B may move. Physical rows, taps, controls and injections remain fixed.
% No impedance subtraction and no simultaneous dispatch fitting are used.
if nargin<4,options=struct();end
if ~isfield(options,'regularization'),options.regularization=1e-3;end
if ~isfield(options,'relative_tolerance'),options.relative_tolerance=0.05;end
assert(options.regularization>0 && isfinite(options.regularization));
required={'branch_row','classification','r_min','r_max','x_min','x_max','b_min','b_max'};
assert(istable(registry)&&all(ismember(required,registry.Properties.VariableNames)), ...
    'fit_registered_residual_network:Registry','Explicit residual bounds required.');
rows=registry.branch_row;
assert(~isempty(rows)&&numel(unique(rows))==numel(rows)&&all(rows>=1 & rows<=size(candidate.branch,1)));
assert(all(registry.classification=="registered_residual_equivalent"), ...
    'fit_registered_residual_network:PhysicalRow','Only registered residual equivalents may change.');
if isfield(candidate,'userdata') && isfield(candidate.userdata,'s13') && ...
        isfield(candidate.userdata.s13,'overlay_report')
    physical=candidate.userdata.s13.overlay_report.branch_map;
    if ismember('model_branch_row',physical.Properties.VariableNames)
        assert(~any(ismember(rows,physical.model_branch_row)), ...
            'fit_registered_residual_network:PhysicalRow','Source-backed circuits are immutable.');
    end
end
assert(isfield(target,'source')&&strlength(string(target.source))>0 && ...
    isfield(target,'bus_ids')&&isfield(target,'Y'), 'A source-backed port target is required.');
assert(isfield(target,'base_mva')&&isfield(target,'base_kv')&& ...
    isfield(target,'vintage')&&isfield(options,'candidate_vintage'), ...
    'fit_registered_residual_network:TargetBase','Target power/voltage bases and vintage are required.');
[found,port_rows]=ismember(target.bus_ids,candidate.bus(:,1));
assert(all(found)&&target.base_mva==candidate.baseMVA&& ...
    isequal(target.base_kv(:),candidate.bus(port_rows,10))&& ...
    string(target.vintage)==string(options.candidate_vintage), ...
    'fit_registered_residual_network:TargetBase','Port bases or vintages do not match.');
assert(numel(unique(target.bus_ids))==numel(target.bus_ids) && ...
    isequal(size(target.Y),[numel(target.bus_ids) numel(target.bus_ids)]) && ...
    all(isfinite(target.Y),'all'),'Invalid port target.');
lo=[registry.r_min registry.x_min registry.b_min];
hi=[registry.r_max registry.x_max registry.b_max];
assert(all(isfinite([lo;hi]),'all')&&all(lo<=hi,'all')&& ...
    all(lo(:,1)>=0)&&all(lo(:,2)>0)&&all(lo(:,3)>=0), ...
    'fit_registered_residual_network:PassiveBounds','Passive finite R/X/B bounds required.');
initial=candidate.branch(rows,3:5);assert(all(initial>=lo & initial<=hi,'all'));
scale=max(abs(initial),[1e-4 1e-3 1e-2]);
target_norm=max(norm(target.Y,'fro'),eps);
opts=optimoptions('lsqnonlin','Display','off','MaxIterations',200, ...
    'FunctionTolerance',1e-12,'StepTolerance',1e-12);
[v,~,~,flag,solver]=lsqnonlin(@residual,initial(:),lo(:),hi(:),opts);
fitted=candidate;fitted.branch(rows,3:5)=reshape(v,[],3);
Y=ports(fitted,target.bus_ids);
error=norm(Y-target.Y,'fro')/target_norm;
H=(Y+Y')/2;mineig=min(real(eig(full(H))));
accepted=flag>0 && error<=options.relative_tolerance && mineig>=-1e-9;
frozen=setdiff((1:size(candidate.branch,1))',rows);
assert(isequaln(candidate.branch(frozen,:),fitted.branch(frozen,:)));
report=registry;report.fitted_r=fitted.branch(rows,3);report.fitted_x=fitted.branch(rows,4);
report.fitted_b=fitted.branch(rows,5);report.fit_accepted=repmat(accepted,height(registry),1);
out=struct('candidate',candidate,'proposed_candidate',fitted,'registry',report, ...
    'accepted',accepted,'relative_port_error',error,'passivity_min_eigenvalue',mineig, ...
    'target_source',string(target.source),'solver_exitflag',flag,'solver',solver, ...
    'promotion_eligible',false,'initial_relative_port_error', ...
    norm(ports(candidate,target.bus_ids)-target.Y,'fro')/target_norm);
% Failed fits are reviewable but never installed into the returned candidate.
if accepted,out.candidate=fitted;end
    function r=residual(z)
        trial=candidate;trial.branch(rows,3:5)=reshape(z,[],3);
        d=(ports(trial,target.bus_ids)-target.Y)/target_norm;
        r=[real(d(:));imag(d(:));sqrt(options.regularization)*(z-initial(:))./scale(:)];
    end
end
function Yp=ports(m,ids)
i=ext2int(m);[tf,k]=ismember(ids,i.order.bus.i2e);
assert(all(tf),'Port absent or isolated.');
Y=makeYbus(i);e=setdiff((1:size(Y,1))',k);
if isempty(e),Yp=Y(k,k);else
    assert(condest(Y(e,e))<1e12,'Eliminated block is singular or ill conditioned.');
    Yp=Y(k,k)-Y(k,e)*(Y(e,e)\Y(e,k));
end
end
