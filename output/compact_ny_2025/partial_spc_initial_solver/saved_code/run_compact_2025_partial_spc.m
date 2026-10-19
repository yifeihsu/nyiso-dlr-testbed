function out=run_compact_2025_partial_spc(options)
%RUN_COMPACT_2025_PARTIAL_SPC Fixed year-end topology, source-only dispatch.
% Earlier 2025 operating inputs are counterfactual stresses on the year-end
% topology, not reconstructions of equipment in service on those dates.
% All interface observations have already been examined; comparisons are
% revisited diagnostics and never enter construction or dispatch objectives.
if nargin<1,options=struct();end
root=fileparts(mfilename('fullpath'));addpath(fullfile(root,'System Matpower Format','NY_Lite'));
defaults=struct('output_dir',fullfile(root,'output','compact_ny_2025','partial_spc'), ...
    'run_tests',true,'run_sensitivities',true,'allow_ipopt_fallback',true);
assert(all(ismember(fieldnames(options),fieldnames(defaults))),'partial_spc_run:Options','Unknown option.');
for name=string(fieldnames(defaults))',if ~isfield(options,name),options.(name)=defaults.(name);end,end
folder=char(options.output_dir);protect(folder,root);
assert(~isfile(fullfile(folder,'campaign.mat')),'partial_spc_run:FrozenOutput','Choose a new output directory; saved campaigns are not overwritten.');
parent_folder=fullfile(root,'output','compact_ny_2025','generation_reconstruction');
parent_path=fullfile(parent_folder,'campaign.mat');
parent_manifest=readtable(fullfile(parent_folder,'campaign_manifest.csv'),'TextType','string');
assert(height(parent_manifest)==1&&parent_manifest.artifact=="campaign.mat" ...
    &&ny_reference_file_sha256(parent_path)==parent_manifest.sha256);
replay=replay_compact_generation_reconstruction(parent_folder);assert(replay.passed);
loaded=load(parent_path,'out');parent=loaded.out;
assert(~parent.internal_interface_targets_used&&all(isnan(parent.inputs.interfaces.target_flow_mw)) ...
    &&all(isnan(parent.inputs.interfaces.actual_flow_mw)),'partial_spc_run:Targets','Parent inputs must be target-free.');
tests=table();if options.run_tests,checked=test_compact_2025_partial_spc;tests=checked.gates;assert(checked.pass&&all(tests.passed));end
variants=table(["nominal";"impedance_075";"impedance_125";"charging_000";"charging_150";"rating_080";"rating_120"], ...
    [1;.75;1.25;1;1;1;1],[1;1;1;0;1.5;1;1],[1;1;1;1;1;.8;1.2], ...
    'VariableNames',{'variant_id','impedance_scale','charging_scale','rating_scale'});
if ~options.run_sensitivities,variants=variants(1,:);end
eligible=parent.case_summary.vintage==2025&parent.case_summary.input_coverage_qualified;
ids=parent.case_summary.scenario_id(eligible);assert(numel(ids)==9);
skipped=parent.case_summary(parent.case_summary.vintage==2025&~parent.case_summary.input_coverage_qualified,:);
code=parent.code_manifest;source=parent.source_manifest;
for file=["output/compact_ny_2025/sources/infrastructure_cutoff_status_audit.csv"; ...
        "output/compact_ny_2025/sources/infrastructure_status_source_manifest.csv"]'
    source=[source;table(file,sha_lf(fullfile(root,file)),"LF_normalized_text", ...
        'VariableNames',source.Properties.VariableNames)]; %#ok<AGROW>
end
for file=["run_compact_2025_partial_spc.m";"replay_compact_2025_partial_spc.m"; ...
        "replay_compact_generation_reconstruction.m"; ...
        "System Matpower Format/NY_Lite/dlr_conductor_library.m"; ...
        "System Matpower Format/NY_Lite/apply_compact_2025_partial_spc.m"; ...
        "System Matpower Format/NY_Lite/test_compact_2025_partial_spc.m"]'
    row=code(1,:);row.relative_path=file;row.sha256_lf_normalized=sha_lf(fullfile(root,file));code=[code;row]; %#ok<AGROW>
end
code=sortrows(code,'relative_path');
if ~isfolder(folder),mkdir(folder);end
cases={};attempt_results={};builds=cell(height(variants),1);summary=table();attempts=table();flows=table();zone_deviations=table();
for v=1:height(variants)
    parameter=table2struct(variants(v,2:end));build=apply_compact_2025_partial_spc(parent.modern_build,parameter);builds{v}=build;
    study_ids=ids;if v>1,study_ids="S1_2025_SUMMER_PEAK_PUBLIC";end
    for k=1:numel(study_ids)
        id=study_ids(k);snapshot=build_compact_nyiso_operating_snapshot(build,parent.inputs,id);
        snapshot.operators=compact_nyiso_interface_operator_variant(snapshot.candidate,snapshot.branch_keys);
        snapshot=apply_compact_independent_generation_prior(snapshot,parent.source_priors,parent.named_source_priors);
        previous=find(parent.case_summary.scenario_id==id);assert(isscalar(previous));
        prior_unchanged=isequal(snapshot.generator_keys,parent.cases{previous}.snapshot.generator_keys) ...
            &&isequal(snapshot.Pg_prior_mw,parent.cases{previous}.snapshot.Pg_prior_mw) ...
            &&isequal(snapshot.Pg_sigma_mw,parent.cases{previous}.snapshot.Pg_sigma_mw);
        assert(prior_unchanged,'partial_spc_run:PriorChanged','Topology variant changed the registered source-prior allocation.');
        snapshot.topology_as_of="2025-12-31";
        snapshot.temporal_scope="earlier_2025_dispatch_inputs_applied_as_counterfactual_year_end_topology_stress";
        snapshot.snapshot.campaign_role="revisited_counterfactual_diagnostic";
        snapshot.snapshot.dataset_split="source_only_counterfactual_prediction";
        fit=[];exception="";q=false;
        solvers="MIPS";if options.allow_ipopt_fallback&&have_feature('ipopt'),solvers=[solvers;"IPOPT"];end
        for s=1:numel(solvers)
            try
                fit=fit_compact_nyiso_operating_snapshot(snapshot,struct('fit_interfaces',false, ...
                    'solver',char(solvers(s)),'opf_start',0,'mips_cost_multiplier',1,'prior_weight',1));
                assert(~fit.internal_interface_fit_used&&all(isnan(fit.residuals.target_flow_mw)));
                q=fit.electrical_baseline_qualified;exception=strjoin([fit.solver_error fit.replay_error]," | ");
            catch err,fit=[];exception=string(err.identifier)+": "+string(err.message);q=false;end
            attempts=[attempts;table(variants.variant_id(v),id,s,solvers(s),q,exception,false, ...
                'VariableNames',{'variant_id','scenario_id','attempt','solver','electrically_qualified','error','bounds_relaxed'})]; %#ok<AGROW>
            attempt_results{end+1,1}=fit; %#ok<AGROW>
            attempt_row=attempts(end,:);attempt_folder=fullfile(folder,'operating_attempts');
            if ~isfolder(attempt_folder),mkdir(attempt_folder);end
            save(fullfile(attempt_folder,sprintf('attempt_%03d.mat',height(attempts))),'fit','attempt_row','-v7');
            if q,break;end
        end
        cases{end+1,1}=fit; %#ok<AGROW>
        z=snapshot.independent_prior_zone_ledger;z.variant_id=repmat(variants.variant_id(v),height(z),1);
        z.solved_generation_mw=NaN(height(z),1);
        if ~isempty(fit)
            gz=snapshot.independent_prior_generator_ledger.zone;
            for n=1:height(z),z.solved_generation_mw(n)=sum(fit.result.gen(gz==z.zone(n),2));end
            f=fit.residuals;f.variant_id=repmat(variants.variant_id(v),height(f),1);f.scenario_id=repmat(id,height(f),1);
            f.electrically_qualified=repmat(q,height(f),1);flows=[flows;f]; %#ok<AGROW>
            case_folder=fullfile(folder,char(variants.variant_id(v)),char(id));if ~isfolder(case_folder),mkdir(case_folder);end
            write(case_folder,'bounded_audit_summary',fit.bounded_audit.summary);
            write(case_folder,'replay_audit_summary',fit.audit.summary);
            write(case_folder,'replay_audit_generator',fit.audit.generator);
            write(case_folder,'replay_audit_branch',fit.audit.branch);
        end
        z.deviation_from_source_prior_mw=z.solved_generation_mw-z.source_prior_benchmark_mw;
        z.electrically_qualified=repmat(q,height(z),1);zone_deviations=[zone_deviations;z]; %#ok<AGROW>
        summary=[summary;table(variants.variant_id(v),id,q,size(snapshot.candidate.bus,1), ...
            size(snapshot.candidate.branch,1),nnz(snapshot.candidate.branch(:,11)>0),size(snapshot.candidate.gen,1), ...
            snapshot.accounting_error_mw,sum(snapshot.bus_injection_ledger.pd_gross_mw), ...
            sum(snapshot.boundary_register.p_injection_mw),prior_unchanged,"revisited_counterfactual_diagnostic",false,false, ...
            'VariableNames',{'variant_id','scenario_id','electrically_qualified','ny_bus_count','branch_records', ...
            'active_branches','generator_records','load_boundary_accounting_error_mw','gross_load_mw','boundary_import_mw', ...
            'source_prior_vectors_unchanged','campaign_role','interface_targets_used','historical_as_operated_reconstruction'})]; %#ok<AGROW>
        fprintf('%s %s: physical_pass=%d buses=%d\n',variants.variant_id(v),id,q,size(snapshot.candidate.bus,1));
    end
end
for k=1:height(code),assert(sha_lf(fullfile(root,code.relative_path(k)))==code.sha256_lf_normalized(k));end
for k=1:height(source),assert(sha_lf(fullfile(root,source.source_path(k)))==source.sha256_lf_normalized(k));end
assert(ny_reference_file_sha256(parent_path)==parent_manifest.sha256,'partial_spc_run:ParentChanged','Parent changed during the experiment.');
out=struct('modern_build',builds{1},'builds',{builds},'cases',{cases},'case_summary',summary, ...
    'attempts',attempts,'attempt_results',{attempt_results},'variants',variants,'target_free_interface_flows',flows,'zone_generation_deviations',zone_deviations, ...
    'skipped_source_scenarios',skipped,'tests',tests,'code_manifest',code,'source_manifest',source, ...
    'parent_relative_path',"output/compact_ny_2025/generation_reconstruction/campaign.mat", ...
    'parent_sha256',string(ny_reference_file_sha256(parent_path)), ...
    'parent_replay',replay,'source_priors',parent.source_priors,'named_source_priors',parent.named_source_priors, ...
    'electrical_baseline_qualified',~isempty(summary)&&all(summary.electrically_qualified),'topology_as_of',"2025-12-31", ...
    'internal_interface_targets_used',false,'interface_parameters_fitted',false,'fresh_holdout_validation',false, ...
    'historical_as_operated_reconstruction',false,'dlr_ready',false,'options',options);
save(fullfile(folder,'campaign.mat'),'out','-v7');
write(folder,'campaign_manifest',table("campaign.mat",string(ny_reference_file_sha256(fullfile(folder,'campaign.mat'))), ...
    'VariableNames',{'artifact','sha256'}));
for name=["case_summary","attempts","variants","target_free_interface_flows","zone_generation_deviations", ...
        "skipped_source_scenarios","tests","code_manifest","source_manifest"]
    write(folder,name,out.(name));
end
for name=string(fieldnames(out.modern_build))'
    if startsWith(name,"partial_spc_")&&istable(out.modern_build.(name)),write(folder,name,out.modern_build.(name));end
end
end

function protect(folder,root)
p=lower(string(char(java.io.File(folder).getCanonicalPath())));
allowed=lower(string(char(java.io.File(fullfile(root,'output','compact_ny_2025','partial_spc')).getCanonicalPath())));
scratch=lower(string(char(java.io.File(fullfile(root,'tmp','partial_spc')).getCanonicalPath())));
assert(p==allowed||startsWith(p,allowed+filesep)||p==scratch||startsWith(p,scratch+filesep), ...
    'partial_spc_run:Output','Output must stay in this variants dedicated output or scratch directory.');
end
function h=sha_lf(path)
fid=fopen(path,'rb');assert(fid>=0);guard=onCleanup(@()fclose(fid));b=fread(fid,Inf,'*uint8'); %#ok<NASGU>
b=uint8(strrep(strrep(char(b'),sprintf('\r\n'),sprintf('\n')),sprintf('\r'),sprintf('\n')));
md=java.security.MessageDigest.getInstance('SHA-256');md.update(b);
h=string(lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2)',1,[])));
end
function write(folder,name,t)
if istable(t)&&~isempty(t.Properties.VariableNames),ny_lite_writetable_lf(t,fullfile(folder,name+".csv"));end
end
