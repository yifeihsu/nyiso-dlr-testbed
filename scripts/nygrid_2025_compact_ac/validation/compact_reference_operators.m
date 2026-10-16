function ref=compact_reference_operators(m,retained_bus_ids)
% Independent passive-network operators, assembled without makeYbus.
% All conductances, shunts, charging, tap magnitudes and phase factors enter.
nb=size(m.bus,1);nl=size(m.branch,1);base=m.baseMVA;
ids=m.bus(:,1);retained_bus_ids=retained_bus_ids(:);
[ok,K]=ismember(retained_bus_ids,ids);assert(all(ok)&&numel(unique(K))==numel(K));
E=setdiff((1:nb)',K,'stable');
assert(all(m.bus(E,3:4)==0,'all'),'compactReference:NonzeroLoad','Elimination contains specified constant power.');
assert(~any(ismember(m.gen(:,1),ids(E))),'compactReference:Generator','Elimination contains a generator/control bus.');
assert(~any(ismember(m.dcline(:,1:2),ids(E)),'all'),'compactReference:DCControl','Elimination contains a DC/PAR-control endpoint.');
[ok,f]=ismember(m.branch(:,1),ids);assert(all(ok));[ok,t]=ismember(m.branch(:,2),ids);assert(all(ok));
on=m.branch(:,11)>0;z=complex(m.branch(:,3),m.branch(:,4));y=zeros(nl,1);y(on)=1./z(on);
tau=m.branch(:,9);tau(tau==0)=1;tap=tau.*exp(1j*deg2rad(m.branch(:,10)));
bc=1j*m.branch(:,5)/2;bc(~on)=0;
yff=(y+bc)./abs(tap).^2;yft=-y./conj(tap);ytf=-y./tap;ytt=y+bc;
Yf=sparse([(1:nl)';(1:nl)'],[f;t],[yff;yft],nl,nb);
Yt=sparse([(1:nl)';(1:nl)'],[f;t],[ytf;ytt],nl,nb);
Ys=sparse([(1:nl)';(1:nl)'],[f;t],[y./tap;-y],nl,nb);
Cf=sparse((1:nl)',f,1,nl,nb);Ct=sparse((1:nl)',t,1,nl,nb);
Y=Cf'*Yf+Ct'*Yt+spdiags(complex(m.bus(:,5),m.bus(:,6))/base,0,nb,nb);
L=zeros(nb,numel(K));L(K,:)=eye(numel(K));L(E,:)=-Y(E,E)\Y(E,K);
Yr=Y(K,:)*L;
scale=max(1,norm(Y,inf));residual=norm(Y(E,:)*L,inf)/scale;
G=(Yr+Yr')/2;minimum_passivity_eigenvalue=min(real(eig(full(G))));
assert(all(isfinite(L),'all')&&residual<1e-10,'compactReference:Elimination','Independent zero-current recovery failed.');
assert(minimum_passivity_eigenvalue>=-1e-9*max(1,norm(G,2)), ...
    'compactReference:Passivity','Reduced port network fails the passive conductance screen.');
ref=struct('full_bus_ids',ids,'retained_bus_ids',retained_bus_ids,'retained_full_rows',K,'eliminated_full_rows',E, ...
    'Yfull',Y,'Yred',Yr,'voltage_lift',L,'Yfrom',Yf,'Yto',Yt,'Yseries',Ys, ...
    'from_bus_rows',f,'to_bus_rows',t,'zero_current_lift_relative_residual',residual, ...
    'minimum_passivity_eigenvalue',minimum_passivity_eigenvalue,'eliminated_block_condition_estimate',condest(Y(E,E)), ...
    'all_eliminated_constant_PQ_zero',true,'all_generator_and_DC_control_buses_retained',true, ...
    'shunts_are_inside_Y_not_erased',true,'physical_currents_refer_to_original_branches',true);
end
