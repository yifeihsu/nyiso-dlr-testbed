function out=run_compact_ny_generation_reconstruction(options)
%RUN_COMPACT_NY_GENERATION_RECONSTRUCTION Source-only bounded AC experiment.
% Internal target columns must be NaN. Observed interface scoring is a later,
% separate operation after input, prior-allocation and solver rules freeze.
% run_operating=false builds and audits allocation without calling an optimizer.
if nargin<1,options=struct();end
root=fileparts(mfilename('fullpath'));h=fullfile(root,'System Matpower Format','NY_Lite');
addpath(h);addpath(fullfile(root,'System Matpower Format'));
defaults=struct('input_dir',fullfile(root,'output','compact_ny_2025','generation_sources','hourly_inputs'), ...
    'prior_file',fullfile(root,'output','compact_ny_2025','generation_sources','combined','zonal_generation_priors.csv'), ...
    'named_prior_file',fullfile(root,'output','compact_ny_2025','generation_sources','combined','named_generator_priors.csv'), ...
    'source_protocol_file',fullfile(root,'output','compact_ny_2025','generation_sources','generation_reconstruction_protocol.json'), ...
    'output_dir',fullfile(root,'output','compact_ny_2025','generation_reconstruction'), ...
    'scenario_ids',strings(0,1),'write_outputs',true,'run_tests',true,'run_operating',true,'allow_ipopt_fallback',true);
for name=string(fieldnames(defaults))',if ~isfield(options,name),options.(name)=defaults.(name);end,end
protect_frozen(options.output_dir,root);
inputs=struct();for name=["snapshots","loads","boundaries","external_records","interfaces"]
    inputs.(name)=read_input(fullfile(options.input_dir,name+".csv"));
end
priors=read_input(options.prior_file);assert(~isempty(priors),'generation_campaign:PriorFile','Source priors are empty.');
named_priors=table();if strlength(string(options.named_prior_file))>0,named_priors=read_input(options.named_prior_file);end
assert(all(isnan(inputs.interfaces.target_flow_mw))&&all(isnan(inputs.interfaces.actual_flow_mw)) ...
    &&~any(inputs.interfaces.used_in_prior)&&~any(inputs.interfaces.used_in_optimizer), ...
    'generation_campaign:TargetUnblinded','Internal-interface observations must remain absent until the method and results are frozen.');
assert(numel(unique(inputs.snapshots.scenario_id))==height(inputs.snapshots) ...
    &&~any(inputs.snapshots.default_campaign_interface_fit_allowed), ...
    'generation_campaign:Partition','Unique target-free snapshot definitions required.');
assert(all(~cellfun('isempty',regexp(cellstr(inputs.snapshots.scenario_id),'^[A-Za-z0-9_]+$','once'))), ...
    'generation_campaign:ScenarioId','Scenario IDs must be safe directory identifiers.');
if ~isempty(options.scenario_ids)
    wanted=string(options.scenario_ids(:));assert(numel(unique(wanted))==numel(wanted)&&all(ismember(wanted,inputs.snapshots.scenario_id)));
    for name=string(fieldnames(inputs))',inputs.(name)=inputs.(name)(ismember(inputs.(name).scenario_id,wanted),:);end
end
protocol=struct('prior_allocation',"reserve_named_source_subsets_then_generic_zone_PMIN_plus_residual_excess_times_headroom_share_then_clip", ...
    'zone_sigma_floor_mw',50,'zone_sigma_fraction',.15,'generator_sigma_floor_mw',1, ...
    'prior_weight',1,'fit_interfaces',false,'operator_variant',"nygrid_informed_partition_v1", ...
    'primary_solver',"MIPS",'fallback_solver',"IPOPT_only_after_failed_physical_qualification_if_available", ...
    'opf_start',0,'mips_cost_multiplier',1,'opf_violation',1e-8,'mips_feastol',1e-9,'mips_max_it',500, ...
    'independent_pf_tolerance',1e-10,'independent_pf_enforce_Q_limits',true, ...
    'cross_zone_prior_reallocation',false,'source_prior_loss_rescaling',false,'capacity_changes',false, ...
    'named_source_estimates_reserved_as_zonal_subsets',true,'sigma_uses_all_online_headroom_before_named_reservation',true, ...
    'matpower_version',string(mpver),'matlab_version',string(version));
code_manifest=code_fingerprints(root);source_manifest=source_fingerprints(options,root);
tests=table();if options.run_tests
    tests=[test_compact_independent_generation_prior;test_compact_nyiso_interface_operator_variant; ...
        test_compact_ny_generation_reconstruction];assert(all(tests.passed));
end
base=build_compact_npcc_corridors;modern=apply_compact_2025_generation(apply_compact_2025_infrastructure(base));
ns=height(inputs.snapshots);cases=cell(ns,1);snapshots=cell(ns,1);attempts=table();summary=table();
zone_deviations=table();generator_deviations=table();blind_predictions=table();folder=options.output_dir;
if options.write_outputs&&~isfolder(folder),mkdir(folder);end
for k=1:ns
    sc=inputs.snapshots(k,:);[eligible,reason]=coverage(sc,inputs,priors,named_priors,strlength(string(options.named_prior_file))>0);
    q=false;nattempt=0;status="skipped_missing_source_or_boundary_coverage";snapshot=[];chosen=[];
    if eligible
        b=base;if sc.vintage==2025,b=modern;end
        snapshot=build_compact_nyiso_operating_snapshot(b,inputs,sc.scenario_id);
        snapshot.operators=compact_nyiso_interface_operator_variant(snapshot.candidate,snapshot.branch_keys);
        snapshot=apply_compact_independent_generation_prior(snapshot,priors,named_priors);snapshots{k}=snapshot;
        expected_ng=35;if sc.vintage==2025,expected_ng=37;end
        assert(size(snapshot.candidate.gen,1)==expected_ng&&size(snapshot.candidate.bus,1)<=200 ...
            &&all(ismember((37:82)',snapshot.candidate.bus(:,1))), ...
            'generation_campaign:Identity','Unexpected compact generator or bus inventory.');
        status="assembled_without_operating_solve";
        if options.run_operating
            [chosen,row]=attempt(snapshot,"MIPS",1);attempts=[attempts;row];nattempt=1; %#ok<AGROW>
            save_attempt(folder,sc.scenario_id,chosen,row,1,options.write_outputs);
            q=~isempty(chosen)&&chosen.electrical_baseline_qualified;
            if ~q&&options.allow_ipopt_fallback&&have_feature('ipopt')
                [second,row]=attempt(snapshot,"IPOPT",2);attempts=[attempts;row];nattempt=2; %#ok<AGROW>
                save_attempt(folder,sc.scenario_id,second,row,2,options.write_outputs);
                if ~isempty(second),chosen=second;end
                q=~isempty(chosen)&&chosen.electrical_baseline_qualified;
            end
            status="operating_solve_failed_not_infeasibility_certificate";if q,status="bounded_source_prior_reconstruction_passed";end
        end
        cases{k}=chosen;
        [zd,gd]=deviations(snapshot,chosen,q);zone_deviations=[zone_deviations;zd];generator_deviations=[generator_deviations;gd]; %#ok<AGROW>
        if options.write_outputs
            sf=fullfile(folder,char(sc.scenario_id));if ~isfolder(sf),mkdir(sf);end
            fit=chosen;save(fullfile(sf,'source_prior_evidence.mat'),'snapshot','fit','-v7');
            write(sf,'zone_generation_deviations',zd);write(sf,'generator_generation_deviations',gd);
            write(sf,'named_source_prior_ledger',snapshot.independent_named_prior_ledger);
            write(sf,'bus_injection_ledger',snapshot.bus_injection_ledger);write(sf,'boundary_register',snapshot.boundary_register);
            write(sf,'generator_map',snapshot.generator_map);write(sf,'branch_map',snapshot.branch_map);
            write(sf,'operator_members',snapshot.operators.members);write(sf,'operator_gaps',snapshot.operators.coverage_gaps);
            if ~isempty(chosen)
                write(sf,'bounded_audit_summary',chosen.bounded_audit.summary);write(sf,'replay_audit_summary',chosen.audit.summary);
                write(sf,'replay_audit_bus',chosen.audit.bus);write(sf,'replay_audit_generator',chosen.audit.generator);
                write(sf,'replay_audit_branch',chosen.audit.branch);write(sf,'target_free_proxy_flows',chosen.residuals);
            end
        end
    end
    opnames=inputs.interfaces.interface_name(inputs.interfaces.scenario_id==sc.scenario_id);
    flow=NaN(numel(opnames),1);previous=flow;
    if ~isempty(chosen)
        old=compact_nyiso_interface_operators(chosen.result,snapshot.branch_keys);
        a=snapshot.operators.from_coefficients*chosen.result.branch(:,14)+snapshot.operators.to_coefficients*chosen.result.branch(:,16);
        b=old.from_coefficients*chosen.result.branch(:,14)+old.to_coefficients*chosen.result.branch(:,16);
        [ok,ix]=ismember(opnames,snapshot.operators.names);assert(all(ok));flow=a(ix);
        [ok,ix]=ismember(opnames,old.names);assert(all(ok));previous=b(ix);
    end
    nn=numel(opnames);blind_predictions=[blind_predictions;table(repmat(sc.scenario_id,nn,1),opnames,flow,previous, ...
        repmat(string(sc.campaign_role),nn,1),repmat(sc.vintage,nn,1),repmat(q,nn,1),false(nn,1), ...
        'VariableNames',{'scenario_id','interface_name','model_flow_mw','previous_operator_model_flow_mw', ...
        'campaign_role','vintage','electrical_baseline_qualified','internal_interface_targets_used'})]; %#ok<AGROW>
    source_total=NaN;unrepresented=NaN;nb=NaN;ng=NaN;accounting=NaN;gross_load=NaN;boundary_import=NaN;
    if ~isempty(snapshot)
        source_total=sum(snapshot.independent_prior_zone_ledger.source_prior_benchmark_mw);
        unrepresented=sum(snapshot.independent_prior_zone_ledger.total_unrepresented_prior_mw);
        nb=size(snapshot.candidate.bus,1);ng=size(snapshot.candidate.gen,1);accounting=snapshot.accounting_error_mw;
        gross_load=sum(snapshot.bus_injection_ledger.pd_gross_mw);boundary_import=sum(snapshot.boundary_register.p_injection_mw);
    end
    summary=[summary;table(sc.scenario_id,sc.vintage,string(sc.campaign_role),string(sc.dataset_split), ...
        string(sc.timestamp),string(sc.timestamp_utc),eligible,status,reason,nattempt,q,nb,ng, ...
        source_total,unrepresented,accounting,gross_load,boundary_import,false,false,false, ...
        'VariableNames',{'scenario_id','vintage','campaign_role','dataset_split','timestamp','timestamp_utc', ...
        'input_coverage_qualified','status','skip_reason','solver_attempt_count','electrical_baseline_qualified', ...
        'ny_bus_count','generator_record_count','source_prior_total_benchmark_mw','unrepresented_prior_total_mw', ...
        'load_boundary_accounting_error_mw','gross_load_benchmark_mw','scheduled_import_benchmark_mw', ...
        'internal_interface_targets_used','observed_zonal_generation_validated','dlr_ready'})]; %#ok<AGROW>
    fprintf('%s: %s; coverage=%d attempts=%d physical_pass=%d\n',sc.scenario_id,status,eligible,nattempt,q);
end
assert(isequal(code_manifest,code_fingerprints(root))&&isequal(source_manifest,source_fingerprints(options,root)), ...
    'generation_campaign:InputsChanged','Code or source inputs changed during the run.');
all_registered=~isempty(summary)&&all(summary.electrical_baseline_qualified);
all_eligible=any(summary.input_coverage_qualified)&&all(summary.electrical_baseline_qualified(summary.input_coverage_qualified));
nmips=0;nipopt=0;if ~isempty(attempts),nmips=nnz(attempts.solver=="MIPS");nipopt=nnz(attempts.solver=="IPOPT");end
campaign_summary=table(height(summary),nnz(summary.input_coverage_qualified),nnz(~summary.input_coverage_qualified), ...
    nnz(summary.electrical_baseline_qualified),nmips,nipopt,all_eligible,all_registered,false,false,false, ...
    'VariableNames',{'registered_scenarios','eligible_scenarios','skipped_scenarios','electrically_qualified_scenarios', ...
    'MIPS_attempts','IPOPT_attempts','all_eligible_snapshots_electrically_qualified', ...
    'all_registered_snapshots_electrically_qualified','internal_interface_targets_used','observed_zonal_generation_validated','dlr_ready'});
out=struct('inputs',inputs,'source_priors',priors,'named_source_priors',named_priors,'base_build',base,'modern_build',modern, ...
    'snapshots',{snapshots},'cases',{cases},'case_summary',summary,'attempts',attempts, ...
    'zone_generation_deviations',zone_deviations,'generator_generation_deviations',generator_deviations, ...
    'blind_interface_predictions',blind_predictions,'campaign_summary',campaign_summary, ...
    'tests',tests,'solver_protocol',protocol,'code_manifest',code_manifest,'source_manifest',source_manifest, ...
    'electrical_baseline_qualified',all_registered, ...
    'all_registered_snapshots_electrically_qualified',all_registered,'all_eligible_snapshots_electrically_qualified',all_eligible, ...
    'internal_interface_targets_used',false,'interface_scoring_performed',false, ...
    'observed_zonal_generation_validated',false,'exact_public_interface_operators',false,'dlr_ready',false, ...
    'options',options,'output_dir',string(folder));
if options.write_outputs
    campaign=fullfile(folder,'campaign.mat');save(campaign,'out','-v7');
    write(folder,'campaign_manifest',table("campaign.mat",string(ny_reference_file_sha256(campaign)), ...
        'VariableNames',{'artifact','sha256'}));
    write(folder,'code_manifest',code_manifest);write(folder,'source_manifest',source_manifest);
    write(folder,'case_summary',summary);write(folder,'operating_attempts',attempts);write(folder,'implementation_tests',tests);
    write(folder,'campaign_summary',campaign_summary);
    write(folder,'blind_interface_predictions',blind_predictions);
    write(folder,'zone_generation_deviations',zone_deviations);write(folder,'generator_generation_deviations',generator_deviations);
end
end

function t=read_input(file)
assert(isfile(file),'generation_campaign:MissingInput','Missing input %s.',file);
opts=detectImportOptions(file,'TextType','string');
strings_={'scenario_id','zone','generator_key','interface_name','public_interface_name','external_region','dataset_split', ...
    'campaign_role','timestamp','timestamp_utc','source_time_zone','source_method','coverage_failure','boundary_coverage_failure'};
for f=intersect(strings_,opts.VariableNames),opts=setvartype(opts,f,'string');end
numeric={'target_flow_mw','actual_flow_mw','target_load_mw','actual_load_mw','target_import_mw','actual_import_mw', ...
    'prior_public_mw','prior_benchmark_mw','scale_factor_gamma','vintage'};
for f=intersect(numeric,opts.VariableNames),opts=setvartype(opts,f,'double');end
t=readtable(file,opts);
logical_={'default_campaign_interface_fit_allowed','boundary_coverage_qualified','coverage_qualified', ...
    'default_primary_scope','default_channel_include','used_in_prior','used_in_optimizer'};
for f=intersect(logical_,t.Properties.VariableNames)
    v=t.(f{1});if ~islogical(v)
        s=lower(string(v));assert(all(ismember(s,["true","false","1","0"])), ...
            'generation_campaign:Boolean','Explicit boolean values required for %s.',f{1});
        t.(f{1})=ismember(s,["true","1"]);
    end
end
end

function [pass,reason]=coverage(sc,inputs,priors,named_priors,named_enabled)
id=sc.scenario_id;p=priors(priors.scenario_id==id,:);l=inputs.loads(inputs.loads.scenario_id==id,:);
e=inputs.external_records(inputs.external_records.scenario_id==id,:);fail=strings(0,1);
if ~sc.boundary_coverage_qualified,fail(end+1)="snapshot_boundary_coverage_unqualified";end
if height(p)~=11||~isequal(sort(string(p.zone)),string(('A':'K')'))
    fail(end+1)="missing_or_duplicate_source_generation_zone";
elseif ~all(p.coverage_qualified)||~all(isfinite(p.prior_public_mw)&p.prior_public_mw>=0&isfinite(p.prior_benchmark_mw)&p.prior_benchmark_mw>=0)
    fail(end+1)="source_generation_coverage_unqualified_or_nonfinite";
elseif max(abs(p.prior_benchmark_mw-p.prior_public_mw*sc.scale_factor_gamma))>=1e-6
    fail(end+1)="generation_power_scale_mismatch";
end
if named_enabled
    n=named_priors(named_priors.scenario_id==id,:);
    expected_named=["NY2025:GEN:CRICKET_VALLEY:PV73";"NY2025:GEN:SOUTH_FORK:K9003"];
    if (sc.vintage==2025&&(height(n)~=2||~isequal(sort(n.generator_key),sort(expected_named)))) ...
            ||(sc.vintage==2019&&~isempty(n))
        fail(end+1)="missing_duplicate_or_unregistered_named_generator_source";
    elseif ~all(n.coverage_qualified)||~all(isfinite(n.prior_public_mw)&n.prior_public_mw>=0&isfinite(n.prior_benchmark_mw)&n.prior_benchmark_mw>=0)
        fail(end+1)="named_source_generation_coverage_unqualified_or_nonfinite";
    elseif any(abs(n.prior_benchmark_mw-n.prior_public_mw*sc.scale_factor_gamma)>=1e-6)
        fail(end+1)="named_generation_power_scale_mismatch";
    end
end
selected=e(e.default_channel_include,:);
expected=["SCH - HQ - NY";"SCH - OH - NY";"SCH - NE - NY";"SCH - PJ - NY";"SCH - NPX_CSC"; ...
    "SCH - NPX_1385";"SCH - PJM_NEPTUNE";"SCH - PJM_VFT";"SCH - PJM_HTP";"SCH - HQ_CEDARS"];
if height(selected)~=10||~isequal(sort(selected.public_interface_name),sort(expected)) ...
        ||~all(selected.coverage_qualified)||~all(isfinite(selected.target_import_mw)&isfinite(selected.actual_import_mw)) ...
        ||any(abs(selected.target_import_mw-sc.scale_factor_gamma*selected.actual_import_mw)>=1e-6)
    fail(end+1)="ten_nonoverlapping_boundary_channels_not_fully_covered";
end
if height(l)~=11||~isequal(sort(string(l.zone)),string(('A':'K')')) ...
        ||~all(isfinite(l.target_load_mw)&l.target_load_mw>=0&isfinite(l.actual_load_mw)&l.actual_load_mw>=0) ...
        ||any(abs(l.target_load_mw-sc.scale_factor_gamma*l.actual_load_mw)>=1e-6)
    fail(end+1)="zonal_load_coverage_invalid";
end
pass=isempty(fail);reason=strjoin(fail,"; ");
end

function [fit,row]=attempt(snapshot,solver,index)
fit=[];exception="";
try
    fit=fit_compact_nyiso_operating_snapshot(snapshot,struct('fit_interfaces',false,'solver',char(solver), ...
        'opf_start',0,'mips_cost_multiplier',1,'prior_weight',1));
    assert(~fit.internal_interface_fit_used&&all(isnan(fit.residuals.target_flow_mw)), ...
        'generation_campaign:TargetLeakage','Target-free operating objective was violated.');
catch e,exception=string(e.identifier)+": "+string(e.message);fit=[];end
qualified=false;bounded=false;pf=false;hardware=false;
if ~isempty(fit)
    qualified=fit.electrical_baseline_qualified;bounded=fit.bounded_audit.passed;pf=fit.audit.passed;hardware=fit.network_and_injections_frozen;
    exception=strjoin([exception,fit.solver_error,fit.replay_error]," | ");
end
row=table(snapshot.scenario_id,index,solver,0,true,bounded,pf,hardware,qualified,exception,false,false, ...
    'VariableNames',{'scenario_id','attempt_index','solver','opf_start','optimizer_called','bounded_audit_pass', ...
    'independent_pf_audit_pass','hardware_frozen','electrical_baseline_qualified','solver_or_replay_error', ...
    'internal_interface_targets_used','bounds_relaxed'});
end

function [z,g]=deviations(snapshot,fit,qualified)
z=snapshot.independent_prior_zone_ledger;g=snapshot.independent_prior_generator_ledger;
pg=NaN(height(g),1);if ~isempty(fit),pg=fit.result.gen(:,2);end
g.solved_pg_mw=pg;g.deviation_from_bounded_prior_mw=pg-g.bounded_prior_mw;
g.deviation_from_raw_source_assignment_mw=pg-g.raw_prior_mw;g.electrical_baseline_qualified=repmat(qualified,height(g),1);
z.solved_generation_mw=NaN(height(z),1);
if ~isempty(fit),for k=1:height(z),z.solved_generation_mw(k)=sum(pg(g.zone==z.zone(k)&g.online));end,end
z.deviation_from_source_prior_mw=z.solved_generation_mw-z.source_prior_benchmark_mw;
z.deviation_from_bounded_prior_mw=z.solved_generation_mw-z.bounded_generator_prior_mw;
z.gross_load_benchmark_mw=zeros(height(z),1);z.scheduled_import_benchmark_mw=zeros(height(z),1);
for k=1:height(z)
    bus=snapshot.bus_injection_ledger.zone==z.zone(k);
    z.gross_load_benchmark_mw(k)=sum(snapshot.bus_injection_ledger.pd_gross_mw(bus));
    z.scheduled_import_benchmark_mw(k)=sum(snapshot.bus_injection_ledger.p_boundary_mw(bus));
end
z.solved_generation_public_scale_mw=z.solved_generation_mw/snapshot.snapshot.scale_factor_gamma;
z.electrical_baseline_qualified=repmat(qualified,height(z),1);
end

function save_attempt(folder,id,fit,row,index,enabled)
if enabled
    sf=fullfile(folder,char(id));if ~isfolder(sf),mkdir(sf);end
    save(fullfile(sf,sprintf('attempt_%d_%s.mat',index,row.solver)),'fit','row','-v7');
end
end

function manifest=code_fingerprints(root)
files=["run_compact_ny_generation_reconstruction.m"; ...
    "System Matpower Format/NY_Lite/apply_compact_independent_generation_prior.m"; ...
    "System Matpower Format/NY_Lite/test_compact_independent_generation_prior.m"; ...
    "System Matpower Format/NY_Lite/test_compact_ny_generation_reconstruction.m"; ...
    "System Matpower Format/NY_Lite/compact_nyiso_interface_operator_variant.m"; ...
    "System Matpower Format/NY_Lite/test_compact_nyiso_interface_operator_variant.m"];
manifest=compact_ny_2025_code_manifest;
for k=1:numel(files)
    row=manifest(1,:);row.relative_path=files(k);row.sha256_lf_normalized=sha_lf(fullfile(root,files(k)));manifest=[manifest;row]; %#ok<AGROW>
end
manifest=sortrows(manifest,'relative_path');
end

function manifest=source_fingerprints(options,root)
files=[string(fullfile(options.input_dir,'snapshots.csv'));string(fullfile(options.input_dir,'loads.csv')); ...
    string(fullfile(options.input_dir,'boundaries.csv'));string(fullfile(options.input_dir,'external_records.csv')); ...
    string(fullfile(options.input_dir,'interfaces.csv'));string(options.prior_file);string(options.source_protocol_file)];
if strlength(string(options.named_prior_file))>0,files(end+1,1)=string(options.named_prior_file);end
for f=["source_manifest.json","source_manifest.csv","source_protocol.json","named_source_manifest.json"]
    for dir=[string(options.input_dir),string(fileparts(options.prior_file))]
        path=fullfile(dir,f);if isfile(path),files(end+1,1)=path;end %#ok<AGROW>
    end
end
hash=strings(numel(files),1);path=hash;
for k=1:numel(files)
    assert(isfile(files(k)),'generation_campaign:MissingSource','Missing declared source %s.',files(k));
    hash(k)=sha_lf(files(k));path(k)=replace(string(files(k)),string(root)+filesep,"");path(k)=replace(path(k),'\','/');
end
manifest=table(path,hash,repmat("LF_normalized_text",numel(files),1), ...
    'VariableNames',{'source_path','sha256_lf_normalized','hash_policy'});
end

function hash=sha_lf(file)
fid=fopen(file,'rb');assert(fid>=0);guard=onCleanup(@()fclose(fid));bytes=fread(fid,Inf,'*uint8'); %#ok<NASGU>
text=native2unicode(bytes','UTF-8');text=strrep(text,sprintf('\r\n'),sprintf('\n'));
md=java.security.MessageDigest.getInstance('SHA-256');md.update(unicode2native(text,'UTF-8'));
hash=string(lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2)',1,[])));
end

function protect_frozen(folder,root)
target=string(char(java.io.File(folder).getCanonicalPath()));
names=["ny_only_package_a","ny_only_package_b","compact_npcc_ny", ...
    "compact_ny_2025/electrical","compact_ny_2025/electrical_fixed_peak", ...
    "compact_ny_2025/electrical_constant_total_diagnostic","compact_ny_2025/thermal", ...
    "compact_ny_2025/generation_sources"];
for k=1:numel(names)
    blocked=string(char(java.io.File(fullfile(root,'output',names(k))).getCanonicalPath()));
    assert(~strcmpi(target,blocked)&&~startsWith(lower(target),lower(blocked)+filesep), ...
        'generation_campaign:FrozenOutput','Output folder would overwrite a source or frozen experiment.');
end
end

function write(folder,name,t)
if istable(t)&&~isempty(t.Properties.VariableNames),ny_lite_writetable_lf(t,fullfile(folder,string(name)+".csv"));end
end
