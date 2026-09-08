function replay=replay_restored_fleet_ac_checkpoint(folder)
%REPLAY_RESTORED_FLEET_AC_CHECKPOINT Fresh frozen-dispatch AC check, no OPF.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(root,'System Matpower Format','NY_Lite'));define_constants;
if nargin<1,folder=fullfile(root,'output','nygrid_compact_2019','ac_checkpoint');end
file=fullfile(folder,'restored_fleet_ac_checkpoint.mat');
manifest=readtable(fullfile(folder,'output_manifest.csv'),'TextType','string','Delimiter',',');
ix=manifest.relative_path=="restored_fleet_ac_checkpoint.mat";
assert(nnz(ix)==1&&string(manifest.sha256(ix))==ny_reference_file_sha256(file), ...
    'compact_2019_ac:InputFingerprint','Checkpoint differs from its frozen manifest.');
d=load(file,'out');out=d.out;source_file=fullfile(root,'output','nygrid_compact_2019','compact','current_input_snapshots.mat');
assert(ny_reference_file_sha256(source_file)==out.input_sha256,'compact_2019_ac:SourceFingerprint','Source-prior input changed.');
source=load(source_file,'selected_inputs');
for k=1:height(out.code_manifest)
    p=which(out.code_manifest.function_name(k));assert(~isempty(p)&&ny_reference_file_sha256(p)==out.code_manifest.sha256(k), ...
        'compact_2019_ac:CodeFingerprint','Executing code differs from checkpoint.');
end
expected=["S2_2019_WINTER_PEAK_PUBLIC";"S3_2019_SHOULDER_LIGHT_LOAD_PUBLIC";"S1_2019_SUMMER_PEAK_PUBLIC"];
assert(isequal(out.summary.scenario_id,expected)&&numel(out.cases)==3&&~out.policy.fit_interfaces ...
    &&~out.Marcy_DC_topology_AC_qualified,'compact_2019_ac:Scope','Unregistered scenario/objective/topology claim.');
replay=table();
for k=1:3
    e=out.cases{k};j=e.selected_attempt;f=e.fit;
    match=cellfun(@(s)string(s.scenario_id)==expected(k),source.selected_inputs);assert(nnz(match)==1);
    s=source.selected_inputs{find(match,1)}.paper74;
    assert(isequaln(e.snapshot,s),'compact_2019_ac:SourceInputs','Saved snapshot differs from original source adapter.');
    assert(j==numel(e.attempts)&&isequaln(f,e.attempts{j})&&string(e.attempts{1}.solver)=="MIPS", ...
        'compact_2019_ac:Selection','Saved chosen fit violates first-success solver sequence.');
    if j==2
        assert(~e.attempts{1}.electrical_baseline_qualified&&string(f.solver)=="IPOPT", ...
            'compact_2019_ac:Selection','Fallback may follow only failed MIPS qualification.');
    else,assert(j==1);end
    assert(~f.internal_interface_fit_used&&~f.bounds_relaxed&&all(isnan(s.interface_targets.target_flow_mw)) ...
        &&~s.snapshot.default_campaign_interface_fit_allowed&&~s.source_dispatch_clipped, ...
        'compact_2019_ac:InterfaceLeakage','Target-free raw-prior policy changed.');
    m=s.candidate;n=size(m.gen,1);sigma=s.Pg_sigma_mw;p=s.Pg_prior_mw;
    cost=[2*ones(n,1),zeros(n,2),3*ones(n,1),1./sigma.^2,-2*p./sigma.^2,(p./sigma).^2];
    assert(isequal(f.input.bus,m.bus)&&isequal(f.input.gen,m.gen)&&isequal(f.input.branch,m.branch) ...
        &&isequal(f.input.gencost,cost),'compact_2019_ac:Objective','Source case or quadratic prior objective changed.');
    hardware(f.bounded_result,m);hardware(f.result,m);
    assert(f.bounded_result.bus(f.bounded_result.bus(:,BUS_TYPE)==REF,BUS_I)==42);
    r=runpf(f.bounded_result,mpoption('verbose',0,'out.all',0,'pf.enforce_q_lims',1,'pf.tol',1e-10));
    hardware(r,m);a=audit_ny_ac_reference(r,struct('branch_keys',s.branch_keys,'generator_keys',s.generator_keys));
    dp=max(abs(r.gen(:,PG)-f.bounded_result.gen(:,PG)));dv=max(abs(r.bus(:,VM)-f.bounded_result.bus(:,VM)));
    flow=s.operators.from_coefficients*r.branch(:,PF)+s.operators.to_coefficients*r.branch(:,PT);
    saved=s.operators.from_coefficients*f.result.branch(:,PF)+s.operators.to_coefficients*f.result.branch(:,PT);
    df=max(abs(flow-saved));passed=a.passed&&dp<1e-3&&dv<1e-4&&df<1e-7;
    assert(passed==logical(out.summary.bounded_AC_qualified(k)),'compact_2019_ac:Qualification','Fresh replay disagrees with qualification.');
    replay=[replay;table(expected(k),passed,a.summary.max_nodal_p_mismatch_mw,a.summary.max_nodal_q_mismatch_mvar, ...
        dp,dv,df,true,false,'VariableNames',{'scenario_id','passed','max_P_mismatch_mw','max_Q_mismatch_mvar', ...
        'Pg_adjustment_from_bounded_mw','VM_adjustment_from_bounded_pu','max_interface_flow_replay_difference_mw', ...
        'original_hardware_and_source_inputs_verified','optimizer_run'})]; %#ok<AGROW>
end
assert(out.all_three_qualified==all(replay.passed));
ny_lite_writetable_lf(replay,fullfile(folder,'independent_replay.csv'));
replay_file=mfilename('fullpath')+".m";
ny_lite_writetable_lf(table("scripts/nygrid_compact_2019/replay_restored_fleet_ac_checkpoint.m", ...
    ny_reference_file_sha256(replay_file),'VariableNames',{'relative_path','sha256'}),fullfile(folder,'replay_code_manifest.csv'));
files=dir(fullfile(folder,'**','*'));files=files(~[files.isdir]);paths=strings(numel(files),1);hashes=paths;
for k=1:numel(files),f=fullfile(files(k).folder,files(k).name);paths(k)=strrep(erase(f,[folder filesep]),'\','/');hashes(k)=ny_reference_file_sha256(f);end
keep=paths~="output_manifest.csv";
ny_lite_writetable_lf(table(paths(keep),hashes(keep),'VariableNames',{'relative_path','sha256'}),fullfile(folder,'output_manifest.csv'));
end
function hardware(r,m)
assert(isequal(r.baseMVA,m.baseMVA)&&isequal(r.bus(:,[1 3:6 10 12:13]),m.bus(:,[1 3:6 10 12:13])) ...
    &&isequal(r.branch(:,1:13),m.branch(:,1:13))&&isequal(r.gen(:,[1 4:5 8:10]),m.gen(:,[1 4:5 8:10])), ...
    'compact_2019_ac:FrozenHardware','Network, load, boundary encoding or capability changed.');
end
