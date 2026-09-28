function replay=replay_compact_ny_2025_electrical(folder)
%REPLAY_COMPACT_NY_2025_ELECTRICAL Rebuild inputs and replay without optimizer.
% Checks source/code provenance, all load/boundary/control/branch accounting,
% training-only participation, heldout separation and fresh bounded AC PFs.
root=fileparts(mfilename('fullpath'));addpath(fullfile(root,'System Matpower Format','NY_Lite'));
addpath(fullfile(root,'System Matpower Format'));
if nargin<1,folder=fullfile(root,'output','compact_ny_2025','electrical_fixed_peak');end
file=fullfile(folder,'compact_ny_2025_electrical_campaign.mat');
manifest=readtable(fullfile(folder,'electrical_campaign_manifest.csv'),'TextType','string');
assert(height(manifest)==1&&manifest.artifact=="compact_ny_2025_electrical_campaign.mat" ...
    && manifest.sha256==ny_reference_file_sha256(file),'compact_replay:Fingerprint','Saved campaign fingerprint changed.');
d=load(file,'out');o=d.out;
assert(isequal(o.electrical_baseline_qualified,true)&&isequal(o.training_complete,true),'compact_replay:Unqualified','Campaign is not electrically qualified.');
assert(isfield(o,'code_manifest')&&isequal(o.code_manifest,compact_ny_2025_code_manifest), ...
    'compact_replay:CodeManifest','Executable electrical definitions changed.');
protocol=struct('opf_start',0,'mips_cost_multiplier',1,'opf_violation',1e-8,'mips_feastol',1e-9, ...
    'mips_max_it',500,'fixed_PF_tolerance',1e-10,'fixed_PF_enforce_Q_limits',true, ...
    'training_prior_weight',.001,'prediction_prior_weight',1,'interface_scale_mw',500);
for name=string(fieldnames(protocol))'
    assert(isfield(o.solver_protocol,name)&&isequal(o.solver_protocol.(name),protocol.(name)), ...
        'compact_replay:SolverProtocol','Saved numerical/control protocol changed.');
end
inputs=build_compact_nyiso_snapshot_inputs(struct('scale_policy',o.options.scale_policy,'expected_source_manifest',o.inputs.source_manifest));
assert(isequaln(inputs,o.inputs),'compact_replay:PublicInputs','Public observations, scaling or partition changed.');
base=build_compact_npcc_corridors;modern=apply_compact_2025_infrastructure(base,o.options.infrastructure_options);
if o.options.apply_generation_updates,modern=apply_compact_2025_generation(modern);end
check_build(base,o.base_build);check_build(modern,o.modern_build);
train=find(inputs.snapshots.vintage==2025&inputs.snapshots.default_campaign_interface_fit_allowed);
assert(numel(train)==4&&numel(o.cases)==height(inputs.snapshots),'compact_replay:Partition','Incorrect campaign partition.');
shares=cellfun(@(v)max(v.result.gen(:,2),0)/sum(max(v.result.gen(:,2),0)),o.cases(train),'UniformOutput',false);
participation=mean(cat(2,shares{:}),2);
assert(isequal(participation,o.training_generation_participation),'compact_replay:TrainingRule','Frozen training participation differs from four training states.');
records=table();results=cell(height(inputs.snapshots),1);
for k=1:height(inputs.snapshots)
    sc=inputs.snapshots(k,:);b=modern;aopts=struct();
    if sc.vintage==2019,b=base;end
    if sc.vintage==2025&&sc.dataset_split=="heldout",aopts.generation_participation=participation;end
    expected=build_compact_nyiso_operating_snapshot(b,inputs,sc.scenario_id,aopts);saved=o.cases{k};
    assert(isequaln(saved.snapshot,expected),'compact_replay:SnapshotAccounting','Saved snapshot accounting or priors changed.');
    assert(saved.internal_interface_fit_used==sc.default_campaign_interface_fit_allowed&&~saved.heldout_interface_leakage, ...
        'compact_replay:TargetLeakage','Historical/heldout target leaked into declared objective.');
    validate_objective(saved,expected);
    [r,a,dp,dv]=replay_case(saved.result,expected);
    assert(saved.electrical_baseline_qualified&&saved.network_and_injections_frozen, ...
        'compact_replay:CaseQualification','A saved case was not qualified.');
    op=expected.operators;p=op.from_coefficients*r.branch(:,14)+op.to_coefficients*r.branch(:,16);
    [ok,j]=ismember(op.names,expected.interface_targets.interface_name);assert(all(ok));target=expected.interface_targets.target_flow_mw(j);
    assert(isequal(saved.residuals.interface_name,op.names)&&max(abs(saved.residuals.target_flow_mw-target))<1e-9 ...
        && max(abs(saved.residuals.model_flow_mw-p))<1e-3,'compact_replay:FlowScoring','Saved proxy flows or observations changed.');
    row=table(sc.scenario_id,true,dp,dv,max(abs(p-target)),expected.accounting_error_mw, ...
        sc.default_campaign_interface_fit_allowed,'VariableNames',{'scenario_id','passed','fresh_P_adjustment_mw', ...
        'fresh_VM_adjustment_pu','maximum_proxy_error_mw','accounting_error_mw','interface_fit_used'});
    records=[records;row];results{k}=r; %#ok<AGROW>
end
% Independently reconstruct the nonadditive HQ interpretation sensitivity.
id="S1_2025_SUMMER_PEAK_PUBLIC";
hs=build_compact_nyiso_operating_snapshot(modern,inputs,id,struct('hq_boundary_policy','net_market_proxy_with_separate_Cedars','generation_participation',participation));
hs.snapshot.default_campaign_interface_fit_allowed=false;
assert(isequaln(hs,o.hq_sensitivity.snapshot)&&~o.hq_sensitivity.internal_interface_fit_used, ...
    'compact_replay:HQSensitivity','HQ swap or frozen prediction rule changed.');
validate_objective(o.hq_sensitivity,hs);[hq_result,hq_audit]=replay_case(o.hq_sensitivity.result,hs);
replay=struct('passed',true,'records',records,'results',{results},'hq_result',hq_result,'hq_audit',hq_audit, ...
    'source_accounting_verified',true,'code_manifest_verified',true,'frozen_training_rule_verified',true, ...
    'heldout_targets_used',false,'optimizer_called',false,'dlr_ready',false, ...
    'qualification_scope',"bounded_calibrated_or_predicted_electrical_snapshots_only_public_operators_remain_proxies");
end
function check_build(fresh,saved)
fields={'source_manifest','candidate','full_candidate','bus_map','branch_keys','generator_keys','ny_bus_ids', ...
    'source_branch_map','parent_branch_disposition','infrastructure_branch_register','infrastructure_source_manifest', ...
    'assumption_register','generation_change_register','generation_prior_register','generation_scope_register'};
for k=1:numel(fields)
    f=fields{k};assert(isfield(fresh,f)==isfield(saved,f),'compact_replay:Build','Construction schema differs.');
    if isfield(fresh,f)
        if ismember(string(f),["candidate","full_candidate"])
            % Historical userdata can hold transient solver/function caches.
            % Compare every electrical matrix and the operative zone map.
            for cf=["version","baseMVA","bus","gen","branch","gencost","bus_name"]
                assert(isequaln(fresh.(f).(cf),saved.(f).(cf)),'compact_replay:Build','Construction electrical field differs: %s.',cf);
            end
            assert(isequal(fresh.(f).userdata.nyiso_physical_zone,saved.(f).userdata.nyiso_physical_zone), ...
                'compact_replay:Build','Construction zone metadata differs.');
        else,assert(isequaln(fresh.(f),saved.(f)),'compact_replay:Build','Construction or registered assumption differs: %s.',f);end
    end
end
end
function validate_objective(saved,expected)
assert(saved.prior_weight>0&&saved.interface_scale_mw==500&&saved.mips_cost_multiplier==1, ...
    'compact_replay:Objective','Objective or numerical protocol changed.');
w=1;if saved.internal_interface_fit_used,w=.001;end
p=expected.Pg_prior_mw;s=expected.Pg_sigma_mw;ng=numel(p);
cost=[2*ones(ng,1),zeros(ng,2),3*ones(ng,1),w./s.^2,-2*w*p./s.^2,w*(p./s).^2];
assert(saved.prior_weight==w&&isequal(saved.input.gencost,cost)&&isequal(saved.result.gencost,cost), ...
    'compact_replay:Objective','Generation-prior objective differs from declared training/heldout policy.');
check_hardware(saved.input,expected.candidate);
assert(isequal(saved.input.bus(:,1:13),expected.candidate.bus)&&isequal(saved.input.gen(:,1:21),expected.candidate.gen), ...
    'compact_replay:InitialState','Initial generation prior or electrical state changed.');
end
function [r,a,dp,dv]=replay_case(m,expected)
check_hardware(m,expected.candidate);ao=struct('generator_keys',expected.generator_keys,'branch_keys',expected.branch_keys);
a=audit_ny_ac_reference(m,ao);assert(a.passed,'compact_replay:SavedPhysics','Saved operating point fails physical equations or limits.');
r=runpf(m,mpoption('verbose',0,'out.all',0,'pf.enforce_q_lims',1,'pf.tol',1e-10));
check_hardware(r,m);a=audit_ny_ac_reference(r,ao);
on=m.gen(:,8)>0;dp=max(abs(r.gen(on,2)-m.gen(on,2)));dv=max(abs(r.bus(:,8)-m.bus(:,8)));
assert(a.passed&&dp<1e-3&&dv<1e-4,'compact_replay:FreshPhysics','Independent PF failed or changed dispatch materially.');
end
function check_hardware(m,expected)
assert(~any(isfield(m,{'userfcn','A','dcline','N','H'})),'compact_replay:CustomInputs','Unregistered electrical extension.');
bc=[1 3 4 5 6 7 10 11 12 13];gc=setdiff(1:21,[2 3 6]);
assert(isequal(m.baseMVA,expected.baseMVA)&&isequal(m.bus(:,bc),expected.bus(:,bc)) ...
    && isequal(m.gen(:,gc),expected.gen(:,gc))&&isequal(m.branch(:,1:13),expected.branch(:,1:13)) ...
    && isequal(m.userdata.nyiso_physical_zone,expected.userdata.nyiso_physical_zone), ...
    'compact_replay:Hardware','Fixed loads, shunts, topology, status, capability, voltage base or zones changed.');
assert(isequal(m.bus(m.bus(:,2)==3,1),expected.bus(expected.bus(:,2)==3,1)), ...
    'compact_replay:Reference','Reference bus policy changed.');
types=m.bus(:,2)==expected.bus(:,2);
for k=find(~types)'
    at=m.gen(:,1)==m.bus(k,1)&m.gen(:,8)>0;
    at_bound=abs(m.gen(at,3)-m.gen(at,4))<1e-3|abs(m.gen(at,3)-m.gen(at,5))<1e-3;
    types(k)=expected.bus(k,2)==2&&m.bus(k,2)==1&&any(at)&&all(at_bound);
end
assert(all(types),'compact_replay:BusType','Bus types changed outside declared reactive-limit switching.');
end
