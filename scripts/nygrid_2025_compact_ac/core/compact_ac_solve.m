function [result,audit,full_result]=compact_ac_solve(c,mpopt)
%COMPACT_AC_SOLVE Newton PF on retained voltages, followed by exact recovery.
% Uses MATPOWER newtonpf/pfsoln and its dcline conversion callbacks. The Q-limit
% policy follows MATPOWER8.1 legacy runpf; no full-network Newton solve occurs.
% MATPOWER: Copyright1996-2025 PSERC/contributors, BSD3-clause.
% See ../THIRD_PARTY_NOTICES.md for the notice and license terms.
if nargin<2||isempty(mpopt)
    mpopt=mpoption('model','AC','pf.alg','NR','pf.tol',1e-10,'pf.nr.max_it',50, ...
        'pf.enforce_q_lims',0,'exp.use_legacy_core',1,'verbose',0,'out.all',0);
end
assert(strcmp(c.model_kind,'compact_complex_admittance_AC')&&c.validation.passed);
assert(strcmpi(mpopt.model,'AC')&&strcmpi(mpopt.pf.alg,'NR') ...
    &&mpopt.pf.current_balance==0&&mpopt.pf.v_cartesian==0, ...
    'compactAC:SolverOptions','This solver implements AC power/polar Newton PF.');
assert(ismember(mpopt.pf.enforce_q_lims,[0 1 2]));
assert(strcmp(c.source_fingerprint,compact_ac_source_fingerprint(c.detailed_mpc,c.retained_bus_ids)), ...
    'compactAC:StaleNetwork','Detailed data changed. Rebuild with compact_ac_build before solving.');
assert(strcmp(c.operator_fingerprint,compact_ac_operator_fingerprint(c)), ...
    'compactAC:EditedOperator','Reduction or recovery data changed. Rebuild with compact_ac_build before solving.');
m=c.detailed_mpc;
assert(isequal(c.bus,m.bus(c.retained_full_rows,:))&&isequal(c.gen,m.gen), ...
    'compactAC:EditedView','Edit the detailed input and rebuild; compact bus/gen fields are immutable views.');
if isfield(m,'dcline'),assert(isequal(c.dcline,m.dcline),'compactAC:EditedView','Rebuild after converter edits.');end
if size(m.branch,2)<17,m.branch(:,17)=0;end
mi=ext2int(m,mpopt);bus=mi.bus;gen=mi.gen;branch=mi.branch;nb=size(bus,1);nk=numel(c.retained_bus_ids);
[ok,full_rows]=ismember(mi.order.bus.i2e,c.full_bus_ids);assert(all(ok)&&nb==numel(c.full_bus_ids));
[ok,k]=ismember(c.retained_bus_ids,mi.order.bus.i2e);assert(all(ok));
[ok,gen_k]=ismember(gen(:,1),k);assert(all(ok),'compactAC:ControlPort','A converted generator/converter lies outside retained buses.');
Y=c.Yfull(full_rows,full_rows);L=c.voltage_lift(full_rows,:);
br_rows=mi.order.branch.status.on;Yf=c.Yf_full(br_rows,full_rows);Yt=c.Yt_full(br_rows,full_rows);
[ref,pv,pq]=bustypes(bus,gen);assert(all(ismember([ref;pv],k)));
on=find(gen(:,8)>0);gbus=gen(on,1);
V0=bus(:,8).*exp(1j*pi/180*bus(:,9));vcb=ones(nb,1);vcb(pq)=0;
vg_rows=find(vcb(gbus));
% Preserve MATPOWER's exact generator order, including last dcline VG at a shared bus.
V0(gbus(vg_rows))=gen(on(vg_rows),6)./abs(V0(gbus(vg_rows))).*V0(gbus(vg_rows));
Vk=V0(k);ref0=ref;reference_angle0=bus(ref0,9);qlim=mpopt.pf.enforce_q_lims;
iterations=0;outer=0;limited=[];trace=struct([]);t0=tic;
initial_control=struct('bus_type',bus(:,2),'generator_bus',gen(:,1), ...
    'generator_PG',gen(:,2),'generator_QG',gen(:,3),'generator_VG',gen(:,6), ...
    'full_internal_bus_ids',mi.order.bus.i2e,'retained_initial_voltage',Vk, ...
    'converted_generator_count',size(gen,1),'reference_bus_ids',mi.order.bus.i2e(ref));
while true
    outer=outer+1;assert(outer<=2*size(gen,1)+1,'compactAC:QControlLoop','Reactive-control loop exceeded finite switching bound.');
    bc=bus(k,:);bc(:,1)=(1:nk)';gc=gen;gc(:,1)=gen_k;
    [rc,pc,qc]=bustypes(bc,gc);
    assert(isequal(k(rc),ref)&&isequal(sort(k(pc)),sort(pv)));
    Sbus=@(Vm)makeSbus(mi.baseMVA,bc,gc,mpopt,Vm);
    [Vk,success,it]=newtonpf(c.Yred,Sbus,Vk,rc,pc,qc,mpopt);
    V=L*Vk;
    [bus,gen,branch]=pfsoln(mi.baseMVA,bus,gen,branch,Y,Yf,Yt,V,ref,pv,pq,mpopt);
    iterations=iterations+it;
    mx=find(gen(:,8)>0&gen(:,3)>gen(:,4)+mpopt.opf.violation);
    mn=find(gen(:,8)>0&gen(:,3)<gen(:,5)-mpopt.opf.violation);
    trace=[trace struct('outer_iteration',outer,'NR_iterations',it,'NR_converged',logical(success), ...
        'upper_Q_violations',numel(mx),'lower_Q_violations',numel(mn),'retained_buses',nk, ...
        'Newton_unknowns',numel(pc)+2*numel(qc))]; %#ok<AGROW>
    if ~success||~qlim||isempty([mx;mn]),break;end
    infeas=union(mx,mn);remaining=find(gen(:,8)>0&ismember(bus(gen(:,1),2),[2 3]));
    if isequal(infeas,remaining)&&(isempty(mx)||isempty(mn)),success=false;break;end
    if qlim==2
        [~,largest]=max([gen(mx,3)-gen(mx,4);gen(mn,5)-gen(mn,3)]);
        if largest>numel(mx),mn=mn(largest-numel(mx));mx=[];else,mx=mx(largest);mn=[];end
    end
    gen(mx,3)=gen(mx,4);gen(mn,3)=gen(mn,5);hit=[mx;mn];
    assert(numel(ref)==1||~any(bus(gen(hit,1),2)==3), ...
        'compactAC:MultipleReferences','Q-limit switching of multiple reference buses is unsupported.');
    bus(gen(hit,1),2)=1;oldref=ref;[ref,pv,pq]=bustypes(bus,gen);
    if ~isequal(ref,oldref),bus(ref,2)=3;bus(pv,2)=2;end
    limited=[limited;hit]; %#ok<AGROW>
end
if qlim&&~isempty(limited)&&~isequal(ref,ref0)
    assert(isscalar(ref0));bus(:,9)=bus(:,9)-bus(ref0,9)+reference_angle0;
end
mi.bus=bus;mi.gen=gen;mi.branch=branch;mi.success=logical(success);mi.iterations=iterations;mi.et=toc(t0);
full_result=int2ext(mi);
if ~isempty(full_result.order.gen.status.off),full_result.gen(full_result.order.gen.status.off,[2 3])=0;end
if ~isempty(full_result.order.branch.status.off),full_result.branch(full_result.order.branch.status.off,14:17)=0;end
Vfull=full_result.bus(:,8).*exp(1j*deg2rad(full_result.bus(:,9)));Vk=Vfull(c.retained_full_rows);
currents=[abs(c.YfL*Vk).*c.from_current_base_A,abs(c.YtL*Vk).*c.to_current_base_A, ...
    abs(c.YseriesL*Vk).*c.to_current_base_A];
persistent helpers_configured
if isempty(helpers_configured)
    root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
    addpath(fullfile(root,'scripts','nygrid_2025_acpf_profile_audit','acpf'));
    addpath(fullfile(root,'scripts','nygrid_2025_ac_system','thermal'));
    helpers_configured=true;
end
[audit,detail]=audit_profile_pf(c.detailed_mpc,full_result);
audit.PF_backend='MATPOWER_newtonpf_compact_complex_admittance';audit.pf_enforce_q_lims=qlim;
audit.compact_retained_bus_count=nk;audit.eliminated_bus_count=numel(c.eliminated_full_rows);
audit.no_full_network_Newton_solve=true;audit.reactive_control_outer_iterations=outer;
audit.recovery_voltage_identity_error_pu=max(abs(Vfull-c.voltage_lift*Vk));
audit.recovered_current_operator_crosscheck_A=max(abs(currents-[detail.from_terminal_current_amp, ...
    detail.to_terminal_current_amp,detail.series_current_amp]),[],'all');
audit.eliminated_current_residual_pu=max([0;abs(c.Yfull(c.eliminated_full_rows,:)*Vfull)]);
audit.reduction_and_equation_gate=audit.AC_equation_gate&&c.validation.passed ...
    &&audit.recovery_voltage_identity_error_pu<1e-8&&audit.recovered_current_operator_crosscheck_A<1e-5;
audit.reduction_does_not_repair_operating_or_asset_assumptions=true;
full_result.userdata.compact_ac=struct('solved_bus_count',nk,'full_Newton_solve_used',false, ...
    'source_fingerprint',c.source_fingerprint,'retained_bus_ids',c.retained_bus_ids);
result=struct('model_kind',c.model_kind,'baseMVA',c.baseMVA,'bus',full_result.bus(c.retained_full_rows,:), ...
    'gen',full_result.gen,'dcline',full_result.dcline,'success',logical(success),'iterations',iterations,'et',mi.et, ...
    'retained_bus_ids',c.retained_bus_ids,'recovered_full_voltage',Vfull, ...
    'recovered_line_current_A',currents,'line_current_columns',{{'from_terminal_A','to_terminal_A','series_A'}}, ...
    'source_fingerprint',c.source_fingerprint,'control_trace',trace,'initial_control',initial_control);
if isfield(c,'bus_name'),result.bus_name=c.bus_name;end
end
