function results = replay_selected_candidates(root)
% Independent MATPOWER DC numerical replay; no physical generator claim.
if nargin<1, root=pwd; end
folder=fullfile(root,'output','nygrid_compact_2019');
d=load(fullfile(folder,'selected_dc_candidates.mat'),'candidates');
cases=d.candidates; n=numel(cases);
timestamp=strings(n,1); pf_success=false(n,1); branch_rows=zeros(n,1);
max_branch_error_mw=zeros(n,1); max_interface_error_mw=zeros(n,1);
max_angle_error_deg=zeros(n,1); virtual_balance_pg_mw=zeros(n,1);
row_identity_preserved=false(n,1);
opt=mpoption('verbose',0,'out.all',0,'exp.use_legacy_core',1);
for k=1:n
    if iscell(cases), c=cases{k}; else, c=cases(k); end
    timestamp(k)=string(c.timestamp);
    % Encode all native generation, renewable net load and fixed boundaries
    % as signed nodal withdrawal. GS is included once before setting it zero.
    p=c.native_solved_pg_bus_mw(:)-c.net_pd_mw(:)+c.boundary_p_mw(:)-c.bus(:,5);
    m=struct('version','2','baseMVA',c.baseMVA,'bus',c.bus(:,1:13), ...
        'branch',c.branch(:,1:13),'gen',zeros(1,21));
    m.bus(:,2)=1; ref=find(m.bus(:,1)==74); assert(isscalar(ref));
    m.bus(ref,2)=3; m.bus(:,3)=-p; m.bus(:,[4 5 6 9])=0; m.bus(:,8)=1;
    % This numerical slack is not a plant, a new capacity, or an AC model.
    m.gen([1 2 3 4 5 6 7 8 9 10])=[74 0 0 1e6 -1e6 1 c.baseMVA 1 1e6 -1e6];
    r=rundcpf(m,opt);
    assert(r.success==1,'Independent MATPOWER DC solve failed');
    pf_success(k)=r.success; branch_rows(k)=size(r.branch,1);
    row_identity_preserved(k)=isequal(r.branch(:,[1:13]),m.branch);
    assert(row_identity_preserved(k),'MATPOWER branch hardware/order changed');
    max_branch_error_mw(k)=max(abs(r.branch(:,14)-c.dc_flow(:)));
    max_interface_error_mw(k)=max(abs(c.operator_coefficients*r.branch(:,14)-c.predicted_benchmark_mw(:)));
    max_angle_error_deg(k)=max(abs(r.bus(:,9)-c.dc_angle_deg(:)));
    virtual_balance_pg_mw(k)=r.gen(1,2);
    assert(max_branch_error_mw(k)<1e-7 && max_interface_error_mw(k)<1e-7);
    assert(max_angle_error_deg(k)<1e-7 && abs(virtual_balance_pg_mw(k))<1e-7);
end
results=table(timestamp,pf_success,branch_rows,row_identity_preserved, ...
    max_branch_error_mw,max_interface_error_mw,max_angle_error_deg,virtual_balance_pg_mw);
writetable(results,fullfile(folder,'verification','matpower_selected_dc_replay.csv'));
save(fullfile(folder,'verification','matpower_selected_dc_replay.mat'),'results');
disp(results);
end
