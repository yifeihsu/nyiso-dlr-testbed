function c=compact_ac_build(m,anchor_ids)
%COMPACT_AC_BUILD Exact complex-admittance reduction of passive zero-injection nodes.
% The output is a matrix network, not a MATPOWER physical-branch case.
% Fixed shunts, line charging and complex taps remain in Y. Currents refer to
% the original branches through recovery operators, never fictitious edges.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
if nargin<2||isempty(anchor_ids)
    registry=readtable(fullfile(root,'output','nygrid_2025_slim','network','bus_register.csv'));
    anchor_ids=double(registry.model_bus(:));assert(numel(anchor_ids)==148);
end
ids=double(m.bus(:,1));anchor_ids=double(anchor_ids(:));nb=numel(ids);nl=size(m.branch,1);
assert(numel(unique(ids))==nb&&numel(unique(anchor_ids))==numel(anchor_ids),'compactAC:DuplicateBus','Bus IDs must be unique.');
assert(all(ismember(anchor_ids,ids)),'compactAC:MissingAnchor','A requested retained bus is absent from the detailed case.');
assert(all(m.bus(:,2)~=4),'compactAC:OfflineBus','Remove explicit NONE buses before constructing this matrix model.');
assert(all(isfinite(m.bus),'all')&&all(isfinite(m.branch(:,1:13)),'all'));
is_anchor=ismember(ids,anchor_ids);
load_port=m.bus(:,3)~=0|m.bus(:,4)~=0;
generator_port=ismember(ids,m.gen(:,1));
dc_port=false(nb,1);
if isfield(m,'dcline')&&~isempty(m.dcline),dc_port=ismember(ids,reshape(m.dcline(:,1:2),[],1));end
control_port=ismember(m.bus(:,2),[2 3]);
required=load_port|generator_port|dc_port|control_port;
extra_ids=ids(required&~is_anchor);
retained_ids=[anchor_ids;extra_ids];
[ok,k]=ismember(retained_ids,ids);assert(all(ok));
e=find(~ismember(ids,retained_ids));nk=numel(k);
assert(all(m.bus(e,3:4)==0,'all')&&~any(generator_port(e)|dc_port(e)|control_port(e)), ...
    'compactAC:NonPassiveElimination','An eliminated node has a prescribed injection or voltage control.');
bus_i=m.bus;bus_i(:,1)=(1:nb)';branch_i=m.branch;
[ok,f]=ismember(m.branch(:,1),ids);assert(all(ok));[ok,t]=ismember(m.branch(:,2),ids);assert(all(ok));
branch_i(:,1)=f;branch_i(:,2)=t;
active=m.branch(:,11)>0;
adjacency=sparse([f(active);t(active)],[t(active);f(active)],1,nb,nb);
component=conncomp(graph(adjacency));
assert(all(ismember(component(e),unique(component(k)))), ...
    'compactAC:UnanchoredInterior','An eliminated island has no retained terminal; define its de-energized/island state explicitly.');
[Y,Yf,Yt]=makeYbus(m.baseMVA,bus_i,branch_i);
L=sparse(k,(1:nk)',ones(nk,1),nb,nk);
if isempty(e)
    reciprocal_condition=1;elimination_error=0;
else
    Yee=Y(e,e);Yek=Y(e,k);reciprocal_condition=rcond(full(Yee));
    assert(isfinite(reciprocal_condition)&&reciprocal_condition>1e-12, ...
        'compactAC:SingularInterior','Eliminated network is singular or ill-conditioned; inspect islands/retention before proceeding.');
    K=-(Yee\Yek);L(e,:)=K;
    elimination_error=norm(Yee*K+Yek,inf)/max(1,norm(Yek,inf));
end
Yr=Y(k,:)*L;
lift_error=norm(Y*L-sparse(k,(1:nk)',ones(nk,1),nb,nk)*Yr,inf)/max(1,norm(Y,inf)*norm(L,inf));
assert(elimination_error<1e-10&&lift_error<1e-10,'compactAC:Algebra','Complex-admittance elimination identity failed.');
ys=zeros(nl,1);z=complex(m.branch(:,3),m.branch(:,4));
assert(all(abs(z(active))>0),'compactAC:ZeroImpedance','Active zero-impedance branch must be resolved explicitly.');
ys(active)=1./z(active);tap=m.branch(:,9);tap(tap==0)=1;tap=tap.*exp(1j*deg2rad(m.branch(:,10)));
Ys=sparse((1:nl)',f,ys./tap,nl,nb)-sparse((1:nl)',t,ys,nl,nb);
G=(Yr+Yr')/2;minimum_conductance_eigenvalue=min(real(eig(full(G))));
passive=minimum_conductance_eigenvalue>=-1e-9*max(1,norm(full(G),2));
assert(passive,'compactAC:NonPassive','Reduced network failed the Hermitian real-power dissipation screen.');
c=struct('model_kind','compact_complex_admittance_AC','model_version',1,'baseMVA',m.baseMVA, ...
    'bus',m.bus(k,:),'gen',m.gen,'retained_bus_ids',retained_ids,'anchor_bus_ids',anchor_ids, ...
    'promoted_bus_ids',extra_ids,'full_bus_ids',ids,'retained_full_rows',k,'eliminated_full_rows',e, ...
    'Yred',Yr,'voltage_lift',L,'Yfull',Y,'Yf_full',Yf,'Yt_full',Yt,'Yseries_full',Ys, ...
    'YfL',Yf*L,'YtL',Yt*L,'YseriesL',Ys*L,'detailed_mpc',m, ...
    'branch_from_bus',m.branch(:,1),'branch_to_bus',m.branch(:,2), ...
    'from_current_base_A',m.baseMVA*1000./(sqrt(3)*m.bus(f,10)), ...
    'to_current_base_A',m.baseMVA*1000./(sqrt(3)*m.bus(t,10)));
if isfield(m,'dcline'),c.dcline=m.dcline;else,c.dcline=[];end
if isfield(m,'bus_name'),c.bus_name=m.bus_name(k);end
if isfield(m,'userdata')&&isfield(m.userdata,'ac_system')
    c.branch_keys=m.userdata.ac_system.branch_keys;
    c.branch_parent_row=m.userdata.ac_system.branch_parent_row;
end
c.retention=table(ids,is_anchor,load_port,generator_port,dc_port,control_port, ...
    ismember(ids,retained_ids),m.bus(:,5),m.bus(:,6), ...
    'VariableNames',{'bus_id','anchor_148','nonzero_load','generator_terminal','DC_terminal','voltage_control', ...
    'retained','GS_MW_at_1pu','BS_MVAr_at_1pu'});
c.source_fingerprint=compact_ac_source_fingerprint(m,retained_ids);
c.validation=struct('passed',true,'anchor_bus_count',numel(anchor_ids),'retained_bus_count',nk, ...
    'promoted_necessary_bus_count',numel(extra_ids),'eliminated_bus_count',numel(e), ...
    'interior_reciprocal_condition',reciprocal_condition,'relative_interior_identity_error',elimination_error, ...
    'relative_full_lift_identity_error',lift_error,'minimum_Hermitian_conductance_eigenvalue',minimum_conductance_eigenvalue, ...
    'all_eliminated_components_connected_to_retained',true, ...
    'complex_shunts_and_phase_taps_preserved',true,'no_magnitude_threshold_pruning',true, ...
    'equivalent_edges_are_physical_conductors',false,'requires_rebuild_after_network_or_control_change',true);
c.operator_fingerprint=compact_ac_operator_fingerprint(c);
end
