function report=test_loss_policy_contract()
% Independent allocation/guard checks; no annual or loss-iteration replay.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
addpath(fullfile(root,'scripts','nygrid_2025_ac_loss_revision','core'));
addpath(fullfile(root,'scripts','nygrid_2025_compact_ac','core'));
out=fullfile(root,'output','nygrid_2025_ac_loss_revision','validation','policy_contract');if ~isfolder(out),mkdir(out);end
baseline=npcc_nygrid_2025_ac(8508);m=ac_loss_prepare_case(baseline,'released_equivalent');p=ac_loss_prepare_policy(m);
c=compact_ac_build(m);assert(numel(c.retained_bus_ids)==148&&isempty(c.promoted_bus_ids));
opt=mpoption('model','AC','pf.alg','NR','pf.tol',1e-10,'pf.nr.max_it',50,'pf.enforce_q_lims',0,'exp.use_legacy_core',1,'verbose',0,'out.all',0);
checks=struct('name',{},'passed',{},'error_identifier',{},'error_message',{});budget=zeros(14,1);[zero,a]=ac_loss_apply_budget(m,p,budget);
checks(end+1)=check('zero_budget_preserves_PD_QD_PG',isequal(zero.bus,m.bus)&&isequal(zero.gen(:,2),m.gen(:,2))&&a.native_and_HQ_PG_unchanged);
budget(1:11)=.1*p.group_gross_PD(1:11);budget(12:14)=[50;70;90];[scaled,a]=ac_loss_apply_budget(m,p,budget);
ny=p.bus_group>=1&p.bus_group<=11;outside=p.bus_group>11;
checks(end+1)=check('NY_fraction_preserves_each_bus_power_factor',max(abs(scaled.bus(ny,3:4)-.9*m.bus(ny,3:4)),[],'all')<1e-10);
checks(end+1)=check('outside_delivered_load_and_native_HQ_profiles_preserved',isequal(scaled.bus(outside,3:4),m.bus(outside,3:4))&&a.native_and_HQ_PG_unchanged);
checks(end+1)=check('network_and_six_DC_controls_preserved',isequal(scaled.branch,m.branch)&&isequal(scaled.dcline,m.dcline)&&isequal(scaled.gen(:,[1 6 8]),m.gen(:,[1 6 8])));
checks(end+1)=check('passive_interiors_keep_zero_PQ',all(scaled.bus(c.eliminated_full_rows,3:4)==0,'all'));
for g=12:14
    use=find(p.external_gen_group==g);ps=p;test_budget=zeros(14,1);test_budget(g)=50;
    ps.Pmax(use(1))=ps.baseline_PG(use(1))+.01;
    [sat,a]=ac_loss_apply_budget(m,ps,test_budget);increment=sat.gen(use,2)-p.baseline_PG(use);
    expected=independent_capped_share(50,p.generator_share(use),ps.Pmax(use)-p.baseline_PG(use));
    checks(end+1)=check(sprintf('region%d_single_saturation_exact_budget_and_independent_projection',g), ...
        abs(increment(1)-.01)<1e-8&&abs(sum(increment)-50)<1e-7&&max(abs(increment-expected))<1e-7);
    ps.Pmax(use)=ps.baseline_PG(use)+(1:numel(use))';test_budget(g)=sum(1:numel(use));
    [sat,a]=ac_loss_apply_budget(m,ps,test_budget);increment=sat.gen(use,2)-p.baseline_PG(use);
    checks(end+1)=check(sprintf('region%d_all_saturated_at_exact_capacity',g),max(abs(increment-(1:numel(use))'))<1e-7);
    test_budget(g)=test_budget(g)+1;
    checks(end+1)=rejection(sprintf('region%d_capacity_exhaustion_rejected',g),@()ac_loss_apply_budget(m,ps,test_budget),'acLoss:ExternalCapacity');
end
bad=zeros(14,1);bad(6)=p.group_gross_PD(6);
checks(end+1)=rejection('nonpositive_NY_served_load_rejected',@()ac_loss_apply_budget(m,p,bad),'acLoss:NegativeServedDemand');
bad=zeros(14,1);bad(1)=-1;
checks(end+1)=rejection('negative_budget_rejected',@()ac_loss_apply_budget(m,p,bad),'');
bad=zeros(14,1);bad(1)=NaN;
checks(end+1)=rejection('nonfinite_budget_rejected',@()ac_loss_apply_budget(m,p,bad),'');
changed=m;changed.bus(1,5)=1;
checks(end+1)=rejection('unowned_bus_conductance_rejected',@()ac_loss_prepare_policy(changed),'acLoss:Conductance');
changed=m;changed.dcline(1,16)=1;
checks(end+1)=rejection('nonzero_DC_losses_rejected',@()ac_loss_prepare_policy(changed),'acLoss:DCLoss');
changed=m;changed.branch(1,4)=changed.branch(1,4)*1.01;
checks(end+1)=rejection('stale_network_operator_reuse_rejected',@()ac_loss_inner_pf(changed,c,[],opt),'acLoss:ChangedNetwork');
changed=m;changed.gen(1,6)=changed.gen(1,6)+.001;
checks(end+1)=rejection('stale_VG_control_reuse_rejected',@()ac_loss_inner_pf(changed,c,[],opt),'acLoss:ChangedNetwork');
changed=m;changed.dcline(1,4)=changed.dcline(1,4)+1;
checks(end+1)=rejection('stale_DC_control_reuse_rejected',@()ac_loss_inner_pf(changed,c,[],opt),'acLoss:ChangedNetwork');
changed=m;changed.bus(c.eliminated_full_rows(1),3)=1;
checks(end+1)=rejection('new_passive_interior_PQ_rejected',@()ac_loss_inner_pf(changed,c,[],opt),'');
checks(end+1)=rejection('double_impedance_revision_rejected',@()ac_loss_prepare_case(m,'released_equivalent'),'acLoss:AlreadyApplied');
report=struct('completed',true,'passed',all([checks.passed]),'checks',checks,'count',numel(checks), ...
    'fixture_hour',8508,'synthetic_capacity_fixtures_are_tests_not_production_changes',true,'annual_replay_run',false);
writetable(struct2table(checks),fullfile(out,'policy_contract_checks.csv'));
fid=fopen(fullfile(out,'policy_contract_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
save(fullfile(out,'policy_contract_fixture.mat'),'baseline','m','p','c','checks','report');
disp(struct2table(checks));
end

function x=independent_capped_share(target,w,room)
% Scalar monotone root, independent of the production repeated saturation.
left=0;right=max(room./w);
for k=1:100
    mid=(left+right)/2;
    if sum(min(room,mid*w))<target,left=mid;else,right=mid;end
end
x=min(room,((left+right)/2)*w);
end
function a=check(name,passed)
a=struct('name',name,'passed',logical(passed),'error_identifier','','error_message','');
end
function a=rejection(name,fn,expected)
a=check(name,false);
try,fn();catch err
    a.error_identifier=err.identifier;a.error_message=err.message;
    a.passed=isempty(expected)||strcmp(err.identifier,expected);
end
end
