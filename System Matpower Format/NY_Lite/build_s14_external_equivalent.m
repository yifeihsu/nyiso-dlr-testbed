function out = build_s14_external_equivalent(source, options)
%BUILD_S14_EXTERNAL_EQUIVALENT Passive NPCC external reduction at a solved state.
% The NY network and physical ties are copied. All external loads/generators
% (including first-terminal devices) are removed exactly once and represented
% by registered fixed P/Q sources. These are reconstructed snapshot injections,
% not observed generation or unlimited balancing/voltage controls. A source
% state is mandatory; this function never solves or calibrates that source.
% Frozen-network scenario update: pass options.frozen_equivalent from an
% earlier output. Any network change is rejected; the same retained ports,
% passive matrix and injection mapping are reused. Outage studies require a
% separately declared topology, not automatic recalibration of the baseline.
if nargin < 2, options = struct(); end
options = defaults(options, 'max_condition',1e12, 'matrix_tolerance',1e-8, ...
    'state_tolerance',1e-6,'retention_options',struct(), ...
    'allow_full_external_fallback',true);
assert(isfield(source,'success') && source.success==1, ...
    's14:UnsolvedSource','A successfully solved source state is required; qualification is a separate gate.');
if isfield(source,'userdata')
    u = source.userdata;
    assert(~isfield(u,'s12_retained_source_bus') && ~isfield(u,'s11'), ...
        's14:ForbiddenSource','S12 reductions and S11 boundary injections are not S14 sources.');
end
assert(isfield(source,'userdata') && isfield(source.userdata,'s13'), ...
    's14:SourceLineage','Source must carry the S13 NPCC construction lineage.');
if isfield(source,'dcline') && ~isempty(source.dcline)
    assert(~any(source.dcline(:,3)>0),'s14:ControlledFacilityRequiresMapping', ...
        'Active DC facilities require explicit retained device mapping, not passive AC reduction.');
end
retention = build_s14_nyiso_retention_set(source,options.retention_options);
ids = source.bus(:,1); n = numel(ids); ny = ismember(ids,retention.ny_bus_ids);
[~,f] = ismember(source.branch(:,1),ids); [~,t] = ismember(source.branch(:,2),ids);
extbranch = ~ny(f)&~ny(t); keepbranch = ~extbranch;
v = source.bus(:,8).*exp(1j*source.bus(:,9)*pi/180);
assert(all(isfinite(v)&abs(v)>0),'s14:InvalidVoltage','Source voltages must be finite and positive.');
% Convert IDs explicitly to MATPOWER internal indexing, preserving row maps.
bus = source.bus; bus(:,1) = (1:n)';
branch = source.branch(:,1:13); branch(:,1)=f; branch(:,2)=t;
Yfull = makeYbus(source.baseMVA,bus,branch);
sext = zeros(n,1); sall = -(source.bus(:,3)+1j*source.bus(:,4))/source.baseMVA;
for k=1:size(source.gen,1)
    if source.gen(k,8)<=0, continue; end
    r = find(ids==source.gen(k,1),1);
    sall(r) = sall(r)+(source.gen(k,2)+1j*source.gen(k,3))/source.baseMVA;
end
state_error = max(abs(v.*conj(Yfull*v)-sall));
assert(state_error<=options.state_tolerance,'s14:StateMismatch', ...
    'Claimed solved source violates AC nodal balance (%.3g pu).',state_error);
sext(~ny)=sall(~ny); iext = conj(sext./v);
bus_ext = bus; bus_ext(ny,5:6)=0;
Yext = makeYbus(source.baseMVA,bus_ext,branch(extbranch,:));
active = source.branch(:,11)>0;
assert(all(source.branch(extbranch&active,3)>=0) && all(source.bus(~ny,5)>=0), ...
    's14:NonpassiveSource','External source contains negative resistance or conductance.');
hash = s14_network_fingerprint(source);
if isfield(options,'frozen_equivalent')
    frozen=options.frozen_equivalent;
    assert(strcmp(hash,frozen.source_network_hash),'s14:FrozenNetworkChanged', ...
        'Frozen external model cannot be refitted after source network changes.');
    assert(isequal(retention.ny_bus_ids,frozen.ny_bus_ids),'s14:FrozenRetentionChanged', ...
        'Frozen NY retention changed.');
    [~,ports]=ismember(frozen.port_bus_ids,ids);
    assert(all(ports>0),'s14:FrozenPorts','Frozen ports are absent from the source.');
    eliminated=find(~ny & ~ismember(ids,frozen.port_bus_ids));
    yeq=frozen.multiport_y; W=frozen.injection_map; conditioning=frozen.condition_estimate;
    method=string(frozen.synthesis_method);
    eqbranch=frozen.equivalent_branches; gs=frozen.shunt_g; bs=frozen.shunt_b;
    matrix_error=frozen.matrix_error;
    % Verify frozen evidence against source equations instead of trusting
    % serialized matrices, conditioning values or previous pass flags.
    [check_y,check_W,check_e,conditioning]=reduce(Yext,ports,ny,options.max_condition);
    assert(isequal(eliminated,check_e) && isequal(size(W),size(check_W)) && ...
        norm(yeq-check_y,Inf)<=options.matrix_tolerance && ...
        norm(W-check_W,Inf)<=options.matrix_tolerance, ...
        's14:FrozenEquivalentChanged','Frozen multiport or injection mapping was modified.');
else
    ports=find(ismember(ids,retention.boundary_bus_ids));
    [yeq,W,eliminated,conditioning] = reduce(Yext,ports,ny,options.max_condition);
    [ok,eqbranch,gs,bs,matrix_error] = synthesize(yeq,ids(ports),options.matrix_tolerance);
    method="passive_real_tap_multiport";
    if ~ok
        % Transformer taps commonly prevent passive unit-tap plus shunt
        % realization. Preserve their native terminals and try again.
        tap=source.branch(:,9); tap(tap==0)=1;
        special=extbranch & active & (abs(tap-1)>1e-12 | abs(source.branch(:,10))>1e-12);
        ports=unique([ports;f(special);t(special)]);
        [yeq,W,eliminated,conditioning] = reduce(Yext,ports,ny,options.max_condition);
        [ok,eqbranch,gs,bs,matrix_error] = synthesize(yeq,ids(ports),options.matrix_tolerance);
        method="passive_multiport_retained_transformer_terminals";
    end
    if ~ok
        assert(options.allow_full_external_fallback,'s14:NoPassiveRealization', ...
            'Multiport requires negative conductance; more external detail must be retained.');
        ports=find(~ny); eliminated=zeros(0,1); yeq=Yext(ports,ports);
        W=sparse(numel(ports),0); conditioning=1;
        eqbranch=source.branch(extbranch,1:13);
        gs=source.bus(ports,5)/source.baseMVA; bs=source.bus(ports,6)/source.baseMVA;
        matrix_error=0; method="passive_native_external_mesh_fallback";
    end
end
passivity=min(real(eig(full((yeq+yeq')/2))));
if isempty(passivity), passivity=0; end
assert(passivity>=-options.matrix_tolerance,'s14:NonpassiveMultiport', ...
    'External multiport has negative real-power dissipation.');
retained=find(ny|ismember((1:n)',ports));
extra=setdiff(retained,retention.register.source_row,'stable');
if ~isempty(extra)
    extra_names="BUS_"+string(ids(extra));
    if isfield(source,'bus_name'),extra_names=upper(strtrim(string(source.bus_name(extra))));end
    extra_register=table(ids(extra),extra_names(:),strings(numel(extra),1),source.bus(extra,10), ...
        repmat("passive_realization_external_terminal",numel(extra),1), ...
        repmat("EXTERNAL_COUPLED_MULTI_PORT",numel(extra),1), ...
        repmat("external_equivalent_terminal",numel(extra),1),extra, ...
        repmat("derived_passive_realization",numel(extra),1), ...
        'VariableNames',retention.register.Properties.VariableNames);
    retention.register=sortrows([retention.register;extra_register],'source_row');
end
retention.retained_bus_ids=ids(retained);
retention.passive_port_bus_ids=ids(ports);
mapped=iext(ports)+W*iext(eliminated);
mapped_s=v(ports).*conj(mapped)*source.baseMVA;
source_external_s=sum(v.*conj(Yext*v))*source.baseMVA;
equivalent_external_s=sum(v(ports).*conj(yeq*v(ports)))*source.baseMVA;
native_external_injection=sum(sext)*source.baseMVA;
mapped_external_injection=sum(mapped_s);
eliminated_loss_adjustment=source_external_s-equivalent_external_s;
loss_mapping_error=abs(native_external_injection-mapped_external_injection-eliminated_loss_adjustment);
assert(loss_mapping_error<=options.state_tolerance*source.baseMVA, ...
    's14:ExternalLossAccounting','External passive losses were not mapped exactly once.');
candidate=struct('version','2','baseMVA',source.baseMVA, ...
    'bus',source.bus(retained,:), 'branch',[source.branch(keepbranch,1:13);eqbranch]);
if isfield(source,'bus_name'), candidate.bus_name=source.bus_name(retained); end
nygen=ismember(source.gen(:,1),ids(ny)); candidate.gen=source.gen(nygen,:);
[~,pr]=ismember(ids(ports),candidate.bus(:,1));
candidate.bus(pr,2)=1; candidate.bus(pr,3:6)=0;
candidate.bus(pr,5)=gs*source.baseMVA; candidate.bus(pr,6)=bs*source.baseMVA;
ng=size(candidate.gen,1); equivalent_gen=zeros(numel(ports),size(source.gen,2));
equivalent_gen(:,1)=ids(ports); equivalent_gen(:,2)=real(mapped_s);
equivalent_gen(:,3)=imag(mapped_s); equivalent_gen(:,4)=imag(mapped_s);
equivalent_gen(:,5)=imag(mapped_s); equivalent_gen(:,6)=abs(v(ports));
equivalent_gen(:,7)=source.baseMVA; equivalent_gen(:,8)=1;
equivalent_gen(:,9)=real(mapped_s); equivalent_gen(:,10)=real(mapped_s);
candidate.gen=[candidate.gen;equivalent_gen];
if isfield(source,'gencost')
    c=source.gencost; gcount=size(source.gen,1);
    gc=c(find(nygen),:); newc=zeros(numel(ports),size(c,2));
    newc(:,1)=2; newc(:,4)=2;
    if size(c,2)<6, newc(:,6)=0; gc(:,6)=0; end
    candidate.gencost=[gc;newc];
    if size(c,1)==2*gcount
        candidate.gencost=[candidate.gencost;c(gcount+find(nygen),:);newc];
    end
end
if ~any(candidate.bus(:,2)==3)
    ref=candidate.gen(find(candidate.gen(1:ng,8)>0,1),1);
    assert(~isempty(ref),'s14:NoNYReference','No NY generator available as angle reference.');
    candidate.bus(candidate.bus(:,1)==ref,2)=3;
end
candidate.userdata=struct('s14',struct('status','unpromoted_electrical_diagnostic', ...
    'source_network_hash',hash,'synthesis_method',method, ...
    'promotion_eligible',false,'dlr_delivery_eligible',false, ...
    'external_injection_semantics','fixed_bounded_reconstructed_snapshot_PQ', ...
    'ny_bus_ids',retention.ny_bus_ids,'retained_source_bus_ids',ids(retained)));
% Evaluate independent network equations at the retained source voltage;
% copying V is a same-state identity check, not a new AC convergence claim.
cbus=candidate.bus; cbus(:,1)=(1:numel(retained))';
cbranch=candidate.branch;
[~,cbranch(:,1)]=ismember(candidate.branch(:,1),candidate.bus(:,1));
[~,cbranch(:,2)]=ismember(candidate.branch(:,2),candidate.bus(:,1));
[Yc,Yf,Yt]=makeYbus(candidate.baseMVA,cbus,cbranch);
target_y=Yfull(retained,retained);
if ~isempty(eliminated)
    target_y=target_y-Yfull(retained,eliminated)*(Yfull(eliminated,eliminated)\Yfull(eliminated,retained));
end
matrix_error=full(max(abs(Yc-target_y),[],'all'));
assert(matrix_error<=options.matrix_tolerance,'s14:RealizationMismatch', ...
    'Assembled candidate does not match the frozen/source network matrix.');
vc=v(retained); sc=-(candidate.bus(:,3)+1j*candidate.bus(:,4))/candidate.baseMVA;
for k=1:size(candidate.gen,1)
    if candidate.gen(k,8)>0
        r=find(candidate.bus(:,1)==candidate.gen(k,1),1);
        sc(r)=sc(r)+(candidate.gen(k,2)+1j*candidate.gen(k,3))/candidate.baseMVA;
    end
end
nodal_error=max(abs(vc.*conj(Yc*vc)-sc));
candidate.branch(:,14)=real(vc(cbranch(:,1)).*conj(Yf*vc))*candidate.baseMVA;
candidate.branch(:,15)=imag(vc(cbranch(:,1)).*conj(Yf*vc))*candidate.baseMVA;
candidate.branch(:,16)=real(vc(cbranch(:,2)).*conj(Yt*vc))*candidate.baseMVA;
candidate.branch(:,17)=imag(vc(cbranch(:,2)).*conj(Yt*vc))*candidate.baseMVA;
direct_pass=nodal_error<=options.state_tolerance && matrix_error<=options.matrix_tolerance;
direct=table(["source_nodal_balance_pu";"reduced_same_state_nodal_balance_pu"; ...
    "multiport_realization_max_admittance_error";"multiport_minimum_dissipation_eigenvalue"; ...
    "external_complex_loss_mapping_error_mva"], ...
    [state_error;nodal_error;matrix_error;passivity;loss_mapping_error], ...
    [options.state_tolerance;options.state_tolerance;options.matrix_tolerance;-options.matrix_tolerance; ...
    options.state_tolerance*source.baseMVA], ...
    [state_error<=options.state_tolerance;nodal_error<=options.state_tolerance; ...
    matrix_error<=options.matrix_tolerance;passivity>=-options.matrix_tolerance; ...
    loss_mapping_error<=options.state_tolerance*source.baseMVA], ...
    'VariableNames',{'metric','value','limit','passed'});
group=repmat("EXTERNAL_COUPLED_MULTI_PORT",numel(ports),1);
for k=1:numel(ports)
    r=find(retention.register.bus_id==ids(ports(k)),1);
    if ~isempty(r)&&strlength(retention.register.boundary_group(r))>0
        group(k)=retention.register.boundary_group(r);
    end
end
injections=table(ids(ports),group,(ng+1:ng+numel(ports))',real(mapped_s),imag(mapped_s), ...
    real(mapped_s),real(mapped_s),imag(mapped_s),imag(mapped_s), ...
    repmat("reconstructed_from_solved_npcc_state",numel(ports),1), ...
    'VariableNames',{'bus_id','boundary_group','candidate_gen_row','reference_p_mw', ...
    'reference_q_mvar','p_min_mw','p_max_mw','q_min_mvar','q_max_mvar','evidence_class'});
[ii,jj,yy]=find(yeq);
external_register=table(ids(ports(ii)),ids(ports(jj)),real(yy),imag(yy), ...
    repmat(string(hash),numel(yy),1),'VariableNames', ...
    {'from_bus_id','to_bus_id','y_real_pu','y_imag_pu','source_network_hash'});
nb=size(eqbranch,1);np=numel(ports);
parameter_register=table([repmat("external_equivalent_branch",nb,1);repmat("external_equivalent_shunt",np,1)], ...
    [(sum(keepbranch)+1:sum(keepbranch)+nb)';pr], ...
    [eqbranch(:,1);ids(ports)],[eqbranch(:,2);nan(np,1)], ...
    [eqbranch(:,3);nan(np,1)],[eqbranch(:,4);nan(np,1)], ...
    [eqbranch(:,5);nan(np,1)],[eqbranch(:,9);nan(np,1)], ...
    [eqbranch(:,10);nan(np,1)],[nan(nb,1);gs*source.baseMVA], ...
    [nan(nb,1);bs*source.baseMVA],repmat(method,nb+np,1), ...
    repmat(string(hash),nb+np,1),false(nb+np,1), ...
    'VariableNames',{'element_class','candidate_row','from_bus_id','to_bus_id', ...
    'r_pu','x_pu','b_pu','tap_ratio','phase_shift_deg','gs_mw','bs_mvar', ...
    'synthesis_method','source_network_hash','dlr_eligible'});
accounting=table(["native_external_net_device_injection";"mapped_boundary_PQ_injection"; ...
    "source_external_passive_absorption";"equivalent_external_passive_absorption"; ...
    "eliminated_passive_absorption_in_injection_mapping"], ...
    real([native_external_injection;mapped_external_injection;source_external_s; ...
    equivalent_external_s;eliminated_loss_adjustment]), ...
    imag([native_external_injection;mapped_external_injection;source_external_s; ...
    equivalent_external_s;eliminated_loss_adjustment]), ...
    'VariableNames',{'quantity','p_mw','q_mvar'});
frozen=struct('source_network_hash',hash,'ny_bus_ids',retention.ny_bus_ids, ...
    'port_bus_ids',ids(ports),'multiport_y',yeq,'injection_map',W, ...
    'condition_estimate',conditioning,'synthesis_method',method, ...
    'equivalent_branches',eqbranch,'shunt_g',gs,'shunt_b',bs,'matrix_error',matrix_error);
out=struct('candidate',candidate,'retention',retention,'external_register',external_register, ...
    'injection_register',injections,'parameter_register',parameter_register, ...
    'external_loss_accounting',accounting, ...
    'direct_validation',direct,'direct_passed',direct_pass, ...
    'source_network_hash',hash,'frozen_equivalent',frozen, ...
    'retained_source_bus_rows',retained,'source_keep_branch_rows',find(keepbranch), ...
    'eliminated_external_bus_ids',ids(eliminated),'condition_estimate',conditioning, ...
    'source_devices_removed_once',true,'public_target_fit_evaluated',false, ...
    'source_qualification_verified',false,'promotion_eligible',false);
end

function [yeq,W,e,c]=reduce(Y,p,ny,max_condition)
e=find(~ny & ~ismember((1:numel(ny))',p));
if isempty(e), yeq=Y(p,p); W=sparse(numel(p),0); c=1; return; end
c=condest(Y(e,e));
assert(isfinite(c)&&c<=max_condition,'s14:IllConditionedExternalBlock', ...
    'Eliminated external block is singular/ill-conditioned (condition %.3g).',c);
W=-(Y(e,e).'\Y(p,e).').';
yeq=Y(p,p)+W*Y(e,p);
end

function [ok,b,g,bs,err]=synthesize(Y,ids,tol)
n=numel(ids); b=zeros(0,13); g=zeros(n,1); bs=g; err=Inf; ok=false;
if norm(Y-Y.',Inf)>tol, return; end
% A reciprocal dissipative matrix need not have nonnegative unit-tap shunts.
% For a real conductance M-matrix, positive diagonal scaling G*u >= 0
% supplies a passive realization: tap_ij=u_i/u_j, yseries_ij=-Yij*tap_ij.
% This preserves every complex off-diagonal while redistributing diagonal
% series conductance. Remaining susceptance is a lossless shunt. It is an
% electrical equivalent; these synthetic taps are not physical equipment.
G=real(Y);off=G-spdiags(diag(G),0,n,n);
if any(nonzeros(off)>tol),return;end
scale=ones(n,1);
if any(full(sum(G,2)) < -tol)
    alpha=max(norm(G,Inf),1)*1e-12;
    scale=(G+alpha*speye(n))\ones(n,1);
    if any(~isfinite(scale)|scale<=0),return;end
    scale=scale/max(scale);
end
diagseries=zeros(n,1);
for i=1:n
    for j=i+1:n
        y=-Y(i,j);
        if abs(y)<=tol/10, continue; end
        tap=scale(i)/scale(j);z=1/(y*tap);
        if real(z)<-tol, return; end
        row=zeros(1,13); row([1 2 3 4 9 11 12 13])= ...
            [ids(i) ids(j) max(0,real(z)) imag(z) tap 1 -360 360];
        b(end+1,:)=row; %#ok<AGROW>
        ys=1/complex(row(3),row(4));
        diagseries(i)=diagseries(i)+ys/tap^2;diagseries(j)=diagseries(j)+ys;
    end
end
d=diag(Y)-diagseries;
if any(real(d)<-tol), return; end
g=max(0,real(d)); bs=imag(d);
bus=zeros(n,13); bus(:,1)=(1:n)';bus(:,2)=1;bus(:,5)=g;bus(:,6)=bs;
bb=b;[~,bb(:,1)]=ismember(b(:,1),ids);[~,bb(:,2)]=ismember(b(:,2),ids);
chk=makeYbus(1,bus,bb); err=full(max(abs(chk-Y),[],'all'));
if isempty(err),err=0;end
ok=err<=tol;
end

function s=defaults(s,varargin)
for k=1:2:numel(varargin)
    if ~isfield(s,varargin{k}),s.(varargin{k})=varargin{k+1};end
end
end
