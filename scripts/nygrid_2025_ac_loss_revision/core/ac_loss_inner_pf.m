function [r,V,info]=ac_loss_inner_pf(m,c,V0,opt)
%AC_LOSS_INNER_PF Fixed-control polar AC PF on the retained148 voltages.
% MATPOWER newtonpf/pfsoln control initialization follows the validated compact
% kernel. See scripts/nygrid_2025_compact_ac/THIRD_PARTY_NOTICES.md.
% Only injections/capability boxes may vary while these operators are reused.
assert(opt.pf.enforce_q_lims==0&&strcmpi(opt.model,'AC')&&strcmpi(opt.pf.alg,'NR') ...
    &&opt.pf.current_balance==0&&opt.pf.v_cartesian==0,'acLoss:PFOptions','Use fixed-control polar NR for this policy.');
b=c.detailed_mpc;
assert(all(m.bus(c.eliminated_full_rows,3:4)==0,'all'), ...
    'acLoss:InteriorInjection','Rebuild and promote any newly loaded interior bus.');
assert(isequal(m.branch(:,1:13),b.branch(:,1:13))&&m.baseMVA==b.baseMVA ...
    &&isequal(m.bus(:,[1 2 5:7 10:13]),b.bus(:,[1 2 5:7 10:13])) ...
    &&isequal(m.gen(:,[1 6 8]),b.gen(:,[1 6 8]))&&isequal(m.dcline,b.dcline), ...
    'acLoss:ChangedNetwork','Rebuild the reduction after changing network, status or voltage/transfer controls.');
if size(m.branch,2)<17,m.branch(:,17)=0;end
mi=ext2int(m,opt);bus=mi.bus;gen=mi.gen;branch=mi.branch;nk=numel(c.retained_bus_ids);
[ok,full_rows]=ismember(mi.order.bus.i2e,c.full_bus_ids);assert(all(ok));
[ok,k]=ismember(c.retained_bus_ids,mi.order.bus.i2e);assert(all(ok));
[ok,gk]=ismember(gen(:,1),k);assert(all(ok));
[ref,pv,pq]=bustypes(bus,gen);assert(all(ismember([ref;pv],k)));
if isempty(V0),V0=bus(:,8).*exp(1j*deg2rad(bus(:,9)));else,V0=V0(full_rows);end
on=find(gen(:,8)>0);gb=gen(on,1);controlled=ones(size(bus,1),1);controlled(pq)=0;v=find(controlled(gb));
V0(gb(v))=gen(on(v),6)./abs(V0(gb(v))).*V0(gb(v));
bc=bus(k,:);bc(:,1)=(1:nk)';gc=gen;gc(:,1)=gk;[rc,pc,qc]=bustypes(bc,gc);
Sbus=@(Vm)makeSbus(mi.baseMVA,bc,gc,opt,Vm);
started=tic;[Vk,success,iterations]=newtonpf(c.Yred,Sbus,V0(k),rc,pc,qc,opt);
V=c.voltage_lift(full_rows,:)*Vk;active=mi.order.branch.status.on;
[bus,gen,branch]=pfsoln(mi.baseMVA,bus,gen,branch,c.Yfull(full_rows,full_rows), ...
    c.Yf_full(active,full_rows),c.Yt_full(active,full_rows),V,ref,pv,pq,opt);
mi.bus=bus;mi.gen=gen;mi.branch=branch;mi.success=logical(success);mi.iterations=iterations;mi.et=toc(started);
r=int2ext(mi);
if ~isempty(r.order.gen.status.off),r.gen(r.order.gen.status.off,[2 3])=0;end
if ~isempty(r.order.branch.status.off),r.branch(r.order.branch.status.off,14:17)=0;end
V=r.bus(:,8).*exp(1j*deg2rad(r.bus(:,9)));
info=struct('success',logical(success),'iterations',iterations,'retained_bus_count',nk, ...
    'full_network_Newton_used',false,'elapsed_seconds',mi.et);
end
