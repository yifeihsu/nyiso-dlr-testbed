function ctx=nylatest_coupled_context(base,backend)
% Set up the fixed electrical operators and explicit accounting derivatives.
if nargin<2,backend='compact';end
p=nylatest_prepare_policy(base);c=nylatest_compact_build(base);
assert(numel(c.retained_bus_ids)==148&&isempty(c.promoted_bus_ids));
opt=mpoption('model','AC','pf.alg','NR','pf.tol',1e-10,'pf.nr.max_it',80,'pf.enforce_q_lims',0, ...
    'exp.use_legacy_core',1,'verbose',0,'out.all',0);
m=base;if size(m.branch,2)<17,m.branch(:,17)=0;end
mi=ext2int(m,opt);[ref,pv,pq]=bustypes(mi.bus,mi.gen);
[ok,full_rows]=ismember(mi.order.bus.i2e,base.bus(:,1));assert(all(ok));
V0=mi.bus(:,8).*exp(1j*deg2rad(mi.bus(:,9)));
on=find(mi.gen(:,8)>0);gb=mi.gen(on,1);vc=ones(size(mi.bus,1),1);vc(pq)=0;take=find(vc(gb));
V0(gb(take))=mi.gen(on(take),6)./abs(V0(gb(take))).*V0(gb(take));
S0=makeSbus(mi.baseMVA,mi.bus,mi.gen,opt);
if strcmp(backend,'compact')
    ids=c.retained_bus_ids;[ok,k]=ismember(ids,mi.order.bus.i2e);assert(all(ok));
    Y=c.Yred;L=c.voltage_lift;A=c.YseriesL;
elseif strcmp(backend,'detailed')
    ids=mi.order.bus.i2e;k=(1:numel(ids))';
    Y=c.Yfull(full_rows,full_rows);A=c.Yseries_full(:,full_rows);
    L=sparse(full_rows,(1:numel(ids))',1,numel(ids),numel(ids));
else,error('acLoss:Backend','Use compact or detailed.');end
[ok,r]=ismember(ref,k);assert(all(ok));[ok,v]=ismember(pv,k);assert(all(ok));[ok,q]=ismember(pq,k);
if strcmp(backend,'compact'),q=q(ok);else,assert(all(ok));end
n=numel(ids);[ok,source_rows]=ismember(ids,base.bus(:,1));assert(all(ok));
load_response=complex(zeros(n,14));
for g=1:11
    use=p.bus_group(source_rows)==g;
    load_response(use,g)=complex(p.gross_PD(source_rows(use)),p.gross_QD(source_rows(use)))/p.group_gross_PD(g)/base.baseMVA;
end
[ok,generator_rows]=ismember(base.gen(:,1),ids);assert(all(ok));
Cg=sparse(generator_rows,(1:size(base.gen,1))',1,n,size(base.gen,1));
ctx=struct('base',base,'policy',p,'compact',c,'backend',backend,'opt',opt,'mi',mi, ...
    'full_rows',full_rows,'mode_bus_ids',ids,'source_rows',source_rows,'Y',Y,'voltage_lift',L,'series_operator',A, ...
    'ownership',p.loss_ownership(:,p.parent),'base_S',S0(k),'load_response',load_response,'generator_map',Cg, ...
    'ref',r,'pv',v,'pq',q,'V0',V0(k),'pvpq',[v;q]);
end
