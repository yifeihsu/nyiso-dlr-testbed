function [result, diagnostics] = solve_s11_dispatch_hour(base, pd, qd, external_pg, options)
%SOLVE_S11_DISPATCH_HOUR Modeled aggregate commitment and hard AC dispatch.
%   This is an independent hourly operating point, not economic dispatch or
%   historical unit commitment. Source aggregate P/Q capability is preserved
%   for each online row. Large-PMIN non-regulating aggregates may be offline
%   to accommodate low net demand. Seven mapped regulating locations and all
%   independent zero-P controls remain available. Network/shunts are frozen.
%   The normalized squared-PG objective uses the saved S11 dispatch as a prior.
%   Only explicitly trusted physical branch ratings constrain the OPF; other
%   reduced-equivalent ratings are reported as diagnostics, as in S11.
%   Success requires ordinary and Q-limit PF replays, AC balance, capability,
%   bus-voltage, physical-branch, external-schedule, and reference checks.

if nargin < 5, options = struct(); end
if ~isfield(options,'trusted_branch_mask')
    error('solve_s11_dispatch_hour:TrustedBranches','Supply trusted_branch_mask.');
end
if ~isfield(options,'max_iterations'), options.max_iterations = 500; end
if ~isfield(options,'power_tolerance'), options.power_tolerance = 1e-3; end
if ~isfield(options,'voltage_tolerance'), options.voltage_tolerance = 1e-6; end
if ~isfield(options,'primary_solver'), options.primary_solver = 'IPOPT'; end
define_constants;
t0 = tic;
ng = size(base.gen,1); nb = size(base.bus,1);
ext = find(string(base.genfuel(:)) == "external_schedule");
internal = setdiff((1:ng)',ext);
trusted = logical(options.trusted_branch_mask(:));
validateattributes(pd,{'numeric'},{'real','finite','vector','numel',nb,'nonnegative'});
validateattributes(qd,{'numeric'},{'real','finite','vector','numel',nb});
validateattributes(external_pg,{'numeric'},{'real','finite','vector','numel',numel(ext)});
validateattributes(trusted,{'logical'},{'vector','numel',size(base.branch,1)});
pd = double(pd(:)); qd = double(qd(:)); external_pg = double(external_pg(:));
assert(numel(ext)==8,'The saved S11 case must contain eight external schedules.');
reference_ids = base.bus(base.bus(:,BUS_TYPE)==REF,BUS_I);
assert(isscalar(reference_ids) && reference_ids==73,'S11 reference must be bus 73.');
allowed_regulating_buses = [37 38 39 41 73 76 81];
assert(all(ismember(base.bus(ismember(base.bus(:,BUS_TYPE),[PV REF]),BUS_I), ...
    allowed_regulating_buses)),'Unexpected baseline regulating bus.');

m = base;
m.bus(:,PD) = pd; m.bus(:,QD) = qd;
m.gen(ext,PG) = external_pg;
m.gen(ext,PMIN) = external_pg; m.gen(ext,PMAX) = external_pg;
m.gen(ext,QG) = 0; m.gen(ext,QMIN) = 0; m.gen(ext,QMAX) = 0;
m.gen(ext,GEN_STATUS) = 1;
net_load = sum(pd)-sum(external_pg);
diagnostics = struct('success',false,'status','unverified', ...
    'reason','','solve_seconds',NaN,'net_load_mw',net_load, ...
    'total_pd_mw',sum(pd),'total_external_import_mw',sum(external_pg), ...
    'offline_rows',[],'solver','','attempt_count',0, ...
    'standard_pf_success',false,'q_limit_pf_success',false, ...
    'maximum_p_violation_mw',Inf,'maximum_q_violation_mvar',Inf, ...
    'maximum_voltage_violation_pu',Inf,'maximum_trusted_branch_violation_mva',Inf, ...
    'maximum_ac_mismatch_mva',Inf,'maximum_external_error_mw',Inf, ...
    'reference_preserved',false,'maximum_legacy_branch_loading_ratio',NaN, ...
    'active_generation_mw',NaN,'total_active_network_loss_mw',NaN, ...
    'ac_branch_loss_mw',NaN,'shunt_active_demand_mw',NaN, ...
    'maximum_pg_movement_from_prior_mw',NaN);

% Each candidate is a whole retained aggregate block. Keep the mapped PV/REF
% locations and fixed-Q aggregate records online. Source remote-Q row 21 is
% linked to active row 20 by identity if that active block is ever disabled.
candidate_mask = base.gen(internal,PMIN)>0 & ...
    base.gen(internal,QMAX)>base.gen(internal,QMIN) & ...
    ~ismember(base.gen(internal,GEN_BUS),allowed_regulating_buses) & ...
    base.gen(internal,GEN_STATUS)>0;
candidates = internal(candidate_mask);
[~,order] = sortrows([-base.gen(candidates,PMIN), candidates],[1 2]);
candidates = candidates(order);
offline = [];
for g = candidates'
    if sum(m.gen(internal,PMIN).*m.gen(internal,GEN_STATUS)) <= net_load
        break;
    end
    m = disable_block(m,g); offline(end+1) = g; %#ok<AGROW>
end
online = internal(m.gen(internal,GEN_STATUS)>0);
if sum(m.gen(online,PMIN)) > net_load + sum(max(m.bus(:,GS),0))+500 || ...
        sum(m.gen(online,PMAX)) < net_load
    result = m;
    diagnostics.status = 'capacity_infeasible';
    diagnostics.reason = 'Retained commitment cannot span the required active demand.';
    diagnostics.offline_rows = offline;
    diagnostics.solve_seconds = toc(t0);
    return;
end

solver_names = unique([string(options.primary_solver), "MIPS"],'stable');
messages = strings(0,1);
result = m;
% Normally one IPOPT solve suffices. On failure, try MIPS for the initial
% commitment and at most two cumulative candidate removals with the primary
% solver, without widening any physical capability. Failure is unverified,
% not a mathematical certificate of infeasibility.
for commitment_attempt = 1:3
    target_pg = make_prior(m,base,internal,net_load);
    m.gen(internal,PG) = target_pg(internal);
    opf_case = m;
    opf_case.branch(~trusted,[RATE_A RATE_B RATE_C]) = 0;
    span = max(100,base.gen(:,PMAX)-base.gen(:,PMIN));
    c2 = 1./span.^2;
    opf_case.gencost = [2*ones(ng,1),zeros(ng,2),3*ones(ng,1), ...
        c2,-2*c2.*target_pg,c2.*target_pg.^2];
    for solver = solver_names
        if commitment_attempt>1 && solver~=string(options.primary_solver)
            continue;
        end
        diagnostics.attempt_count = diagnostics.attempt_count+1;
        diagnostics.solver = char(solver);
        try
            opt = mpoption('verbose',0,'out.all',0,'opf.ac.solver',char(solver), ...
                'opf.flow_lim','S','opf.violation',1e-6,'opf.use_vg',0, ...
                'opf.ignore_angle_lim',0,'opf.start',2);
            if upper(solver)=="IPOPT"
                opt.ipopt.opts = struct('max_iter',options.max_iterations, ...
                    'tol',1e-10,'acceptable_tol',1e-10, ...
                    'constr_viol_tol',1e-10,'acceptable_constr_viol_tol',1e-10, ...
                    'bound_relax_factor',0);
            else
                opt = mpoption(opt,'mips.max_it',options.max_iterations);
            end
            solved = runopf(opf_case,opt);
            if ~solved.success
                info = "";
                if isfield(solved,'raw') && isfield(solved.raw,'output') && ...
                        isfield(solved.raw.output,'status')
                    info = ", solver_status="+string(solved.raw.output.status);
                end
                messages(end+1) = solver+": ACOPF success=0"+info+ ...
                    ", offline="+string(mat2str(offline)); %#ok<AGROW>
                continue;
            end
            replay_case = m;
            replay_case.bus(:,[VM VA]) = solved.bus(:,[VM VA]);
            replay_case.gen(:,[PG QG VG]) = solved.gen(:,[PG QG VG]);
            pfopt = mpoption('verbose',0,'out.all',0,'pf.tol',1e-10, ...
                'pf.enforce_q_lims',0);
            [qpf,q_ok] = runpf(replay_case,mpoption(pfopt,'pf.enforce_q_lims',1));
            % Enforcing reactive capability can legitimately switch a PV
            % bus to PQ. Verify ordinary PF on that final control state,
            % rather than rejecting a valid Q-limited state because the
            % superseded PV state requests Q outside its capability.
            [standard,standard_ok] = runpf(qpf,pfopt);
            diagnostics.standard_pf_success = logical(standard_ok);
            diagnostics.q_limit_pf_success = logical(q_ok);
            [ok1,check1] = verify_result(standard,replay_case,base,ext,trusted,options);
            [ok2,check2] = verify_result(qpf,replay_case,base,ext,trusted,options);
            names = fieldnames(check2);
            for k=1:numel(names), diagnostics.(names{k}) = check2.(names{k}); end
            if ~(standard_ok && q_ok && ok1 && ok2)
                messages(end+1) = solver+": PF verification failed; "+ ...
                    string(jsonencode(struct('standard',check1,'q_limit',check2))); %#ok<AGROW>
                continue;
            end
            result = qpf;
            % Both runpf replays use original ratings and all frozen network
            % data. This is the delivered case rather than the OPF wrapper.
            diagnostics.success = true;
            diagnostics.status = 'ac_verified';
            diagnostics.reason = 'Hard ACOPF and both PF replays passed.';
            diagnostics.offline_rows = offline;
            diagnostics.solve_seconds = toc(t0);
            diagnostics.maximum_pg_movement_from_prior_mw = ...
                max(abs(result.gen(internal,PG)-target_pg(internal)));
            return;
        catch err
            messages(end+1) = solver+": "+string(err.message); %#ok<AGROW>
        end
    end
    if commitment_attempt==3, break; end
    remaining = setdiff(candidates,offline,'stable');
    if isempty(remaining), break; end
    g = remaining(1);
    next = disable_block(m,g);
    online = internal(next.gen(internal,GEN_STATUS)>0);
    if sum(next.gen(online,PMAX)) < net_load+1000, break; end
    m = next; offline(end+1) = g; %#ok<AGROW>
end
diagnostics.status = 'ac_unverified';
diagnostics.reason = char(strjoin(messages,' | '));
diagnostics.offline_rows = offline;
diagnostics.solve_seconds = toc(t0);
result = m;
end

function m = disable_block(m,g)
define_constants;
m.gen(g,GEN_STATUS) = 0; m.gen(g,[PG QG]) = 0;
if string(m.genfuel{g})=="aggregate_pv_generator_p_injection" && m.gen(g,GEN_BUS)==56
    remote = find(string(m.genfuel(:))=="aggregate_pv_generator_remote_q_control" & ...
        m.gen(:,GEN_BUS)==61);
    m.gen(remote,GEN_STATUS) = 0; m.gen(remote,[PG QG]) = 0;
end
end

function target = make_prior(m,base,internal,net_load)
define_constants;
target = m.gen(:,PG);
on = internal(m.gen(internal,GEN_STATUS)>0 & m.gen(internal,PMAX)>0);
off = internal(m.gen(internal,GEN_STATUS)<=0);
target(off) = 0;
% A smooth load-squared branch-loss estimate only establishes the prior;
% exact losses are determined by AC constraints, never forced as an input.
base_branch_loss = max(0,sum(base.gen(:,PG))-sum(base.bus(:,PD))-sum(base.bus(:,GS)));
ratio = sum(m.bus(:,PD))/sum(base.bus(:,PD));
required = net_load+sum(m.bus(:,GS))+base_branch_loss*ratio^2;
required = min(sum(m.gen(on,PMAX)),max(sum(m.gen(on,PMIN)),required));
shares = max(base.gen(on,PG),0);
if sum(shares)==0, shares = m.gen(on,PMAX); end
p = required*shares/sum(shares);
p = min(m.gen(on,PMAX),max(m.gen(on,PMIN),p));
for k=1:4
    delta = required-sum(p);
    if abs(delta)<1e-8, break; end
    if delta>0, headroom=m.gen(on,PMAX)-p; else, headroom=p-m.gen(on,PMIN); end
    if sum(headroom)<=0, break; end
    p = p+delta*headroom/sum(headroom);
    p = min(m.gen(on,PMAX),max(m.gen(on,PMIN),p));
end
target(on) = p;
end

function [ok,c] = verify_result(r,m,base,ext,trusted,options)
define_constants;
on = r.gen(:,GEN_STATUS)>0; off = ~on;
c = struct();
c.maximum_p_violation_mw = max([0; r.gen(on,PG)-m.gen(on,PMAX); m.gen(on,PMIN)-r.gen(on,PG); abs(r.gen(off,PG))]);
c.maximum_q_violation_mvar = max([0; r.gen(on,QG)-m.gen(on,QMAX); m.gen(on,QMIN)-r.gen(on,QG); abs(r.gen(off,QG))]);
c.maximum_voltage_violation_pu = max([0; r.bus(:,VM)-m.bus(:,VMAX); m.bus(:,VMIN)-r.bus(:,VM)]);
smax = max(hypot(r.branch(:,PF),r.branch(:,QF)),hypot(r.branch(:,PT),r.branch(:,QT)));
rated = trusted & r.branch(:,BR_STATUS)>0 & r.branch(:,RATE_A)>0;
c.maximum_trusted_branch_violation_mva = max([0; smax(rated)-r.branch(rated,RATE_A)]);
legacy = ~trusted & r.branch(:,BR_STATUS)>0 & r.branch(:,RATE_A)>0;
c.maximum_legacy_branch_loading_ratio = max([0; smax(legacy)./r.branch(legacy,RATE_A)]);
c.maximum_external_error_mw = max(abs(r.gen(ext,PG)-m.gen(ext,PG)));
refs = r.bus(r.bus(:,BUS_TYPE)==REF,BUS_I);
regs = r.bus(ismember(r.bus(:,BUS_TYPE),[PV REF]),BUS_I);
c.reference_preserved = isequal(refs,73) && all(ismember(regs,[37 38 39 41 73 76 81]));
ri = ext2int(r);
Y = makeYbus(ri.baseMVA,ri.bus,ri.branch);
V = ri.bus(:,VM).*exp(1j*pi/180*ri.bus(:,VA));
mis = (V.*conj(Y*V)-makeSbus(ri.baseMVA,ri.bus,ri.gen))*ri.baseMVA;
c.maximum_ac_mismatch_mva = max(abs(mis));
c.active_generation_mw = sum(r.gen(:,PG))-sum(r.gen(ext,PG));
c.total_active_network_loss_mw = sum(r.gen(:,PG))-sum(r.bus(:,PD));
c.ac_branch_loss_mw = sum(r.branch(:,PF)+r.branch(:,PT));
c.shunt_active_demand_mw = sum(r.bus(:,GS).*r.bus(:,VM).^2);
network_same = isequal(r.bus(:,[BUS_I GS BS BASE_KV VMAX VMIN]),base.bus(:,[BUS_I GS BS BASE_KV VMAX VMIN])) && ...
    isequal(r.branch(:,1:13),base.branch(:,1:13));
finite = all(isfinite([r.bus(:);r.gen(:);r.branch(:);mis(:)]));
ok = logical(r.success) && finite && network_same && c.reference_preserved && ...
    c.maximum_p_violation_mw<=options.power_tolerance && ...
    c.maximum_q_violation_mvar<=options.power_tolerance && ...
    c.maximum_voltage_violation_pu<=options.voltage_tolerance && ...
    c.maximum_trusted_branch_violation_mva<=options.power_tolerance && ...
    c.maximum_ac_mismatch_mva<=options.power_tolerance && ...
    c.maximum_external_error_mw<=options.power_tolerance;
end
