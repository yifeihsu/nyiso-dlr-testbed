function out=run_compact_ny_2025_calibration(options)
%RUN_COMPACT_NY_2025_CALIBRATION Matched public snapshots and heldout AC checks.
% Historical 2019 hours are evaluated without fitting their interface values.
% 2025 S1--S4 calibrate operating dispatch on the assumed fixed network.
% Mean normalized training dispatch is then frozen for heldout S5/S6 priors.
% No thermal or exact-public-operator validation is implied by a low residual.
if nargin<1,options=struct();end
root=fileparts(mfilename('fullpath'));h=fullfile(root,'System Matpower Format','NY_Lite');
addpath(h);addpath(fullfile(root,'System Matpower Format'));
if ~isfield(options,'output_dir'),options.output_dir=fullfile(root,'output','compact_ny_2025','electrical_fixed_peak');end
if ~isfield(options,'write_outputs'),options.write_outputs=true;end
if ~isfield(options,'run_tests'),options.run_tests=true;end
if ~isfield(options,'apply_generation_updates'),options.apply_generation_updates=true;end
if ~isfield(options,'allow_ipopt_fallback'),options.allow_ipopt_fallback=true;end
if ~isfield(options,'infrastructure_options'),options.infrastructure_options=struct();end
if ~isfield(options,'scale_policy'),options.scale_policy='fixed_year_peak';end
protect_legacy(options.output_dir,root);
inputs=build_compact_nyiso_snapshot_inputs(struct('scale_policy',options.scale_policy));
base=build_compact_npcc_corridors;modern=apply_compact_2025_infrastructure(base,options.infrastructure_options);
if options.apply_generation_updates,modern=apply_compact_2025_generation(modern);end
tests=table();
if options.run_tests
    tests=[test_compact_interface_ac_cost;test_compact_nyiso_operating_snapshot(modern,inputs)];
    assert(all(tests.passed),'compact_campaign:Tests','Implementation guard failed.');
end
folder=options.output_dir;if options.write_outputs&&~isfolder(folder),mkdir(folder);end
ns=height(inputs.snapshots);cases=cell(ns,1);attempts=table();comparison=table();case_summary=table();
train=find(inputs.snapshots.vintage==2025&inputs.snapshots.default_campaign_interface_fit_allowed);
historical=find(inputs.snapshots.vintage==2019);heldout=find(inputs.snapshots.vintage==2025&inputs.snapshots.dataset_split=="heldout");
assert(numel(train)==4&&numel(historical)==6&&numel(heldout)==2,'compact_campaign:Partition','Expected fixed6 historical/4 training/2 heldout partition.');
% Fit only registered 2025 training hours before freezing the prediction rule.
order=[train(:);historical(:);heldout(:)];training_participation=[];training_complete=false;
for j=1:numel(order)
    k=order(j);sc=inputs.snapshots(k,:);b=modern;assembly_options=struct();
    if sc.vintage==2019,b=base;end
    if j==numel(train)+1
        valid=cellfun(@(v)~isempty(v)&&v.electrical_baseline_qualified,cases(train));
        training_complete=all(valid);
        if training_complete
            pg=cellfun(@(v)max(v.result.gen(:,2),0)/sum(max(v.result.gen(:,2),0)),cases(train),'UniformOutput',false);
            training_participation=mean(cat(2,pg{:}),2);
            assert(all(isfinite(training_participation)&training_participation>=0));
        end
    end
    if sc.vintage==2025&&sc.dataset_split=="heldout"&&training_complete
        assembly_options.generation_participation=training_participation;
    end
    snapshot=build_compact_nyiso_operating_snapshot(b,inputs,sc.scenario_id,assembly_options);
    [fit,ledger]=run_case(snapshot,options,folder);
    fit.prediction_rule_training_complete=training_complete;
    fit.frozen_training_prediction_applied=sc.vintage==2025&&sc.dataset_split=="heldout"&&training_complete;
    fit.historical_capacity_prior_only=sc.vintage==2019;
    cases{k}=fit;attempts=[attempts;ledger]; %#ok<AGROW>
    t=fit.residuals;n=height(t);gamma=sc.scale_factor_gamma;
    t.scenario_id=repmat(sc.scenario_id,n,1);t.vintage=repmat(sc.vintage,n,1);t.dataset_split=repmat(sc.dataset_split,n,1);
    t.campaign_role=repmat(sc.campaign_role,n,1);t.timestamp=repmat(sc.timestamp,n,1);t.timestamp_utc=repmat(sc.timestamp_utc,n,1);
    t.scale_factor_gamma=repmat(gamma,n,1);t.actual_observed_flow_mw=t.target_flow_mw/gamma;
    t.model_proxy_in_observation_scale_mw=t.model_flow_mw/gamma;
    t.observation_scale_residual_mw=t.residual_mw/gamma;
    t.observation_scale_is_uniform_shape_rescaling=true(n,1);
    t.near_zero_target=abs(t.target_flow_mw)<100;
    t.normalized_absolute_error_with_100mw_floor=t.absolute_residual_mw./max(100,abs(t.target_flow_mw));
    t.electrically_qualified=repmat(fit.electrical_baseline_qualified,n,1);
    t.generation_dispatch_observed=false(n,1);t.generator_dispatch_validation_passed=false(n,1);
    comparison=[comparison;t]; %#ok<AGROW>
    sumrow=table(sc.scenario_id,sc.vintage,sc.dataset_split,size(fit.result.bus,1),size(fit.result.branch,1), ...
        nnz(fit.result.branch(:,11)>0),height(snapshot.boundary_inputs),height(snapshot.omitted_boundary_records), ...
        sum(snapshot.bus_injection_ledger.pd_gross_mw),sum(snapshot.boundary_register.p_injection_mw), ...
        snapshot.accounting_error_mw,fit.electrical_baseline_qualified,fit.internal_interface_fit_used, ...
        mean(t.absolute_residual_mw),max(t.absolute_residual_mw),mean(t.normalized_absolute_error_with_100mw_floor), ...
        false,false,'VariableNames',{'scenario_id','vintage','dataset_split','ny_bus_count','branch_records', ...
        'active_branch_count','boundary_channel_count','omitted_HQ_scope_records','gross_load_mw','net_scheduled_import_mw', ...
        'accounting_error_mw','electrical_baseline_qualified','interface_targets_used_in_optimizer','proxy_MAE_mw', ...
        'proxy_max_error_mw','mean_normalized_error_floor100','observed_generator_dispatch_validated','dlr_ready'});
    case_summary=[case_summary;sumrow]; %#ok<AGROW>
    if options.write_outputs
        sf=fullfile(folder,char(sc.scenario_id));if ~isfolder(sf),mkdir(sf);end
        mpc=fit.result;electrical_baseline_qualified=fit.electrical_baseline_qualified; %#ok<NASGU>
        save(fullfile(sf,'operating_snapshot.mat'),'mpc','snapshot','electrical_baseline_qualified','-v7');
        save(fullfile(sf,'operating_evidence.mat'),'fit','-v7');
        write(sf,'interface_comparison',t);write(sf,'bus_injection_ledger',snapshot.bus_injection_ledger);
        write(sf,'boundary_register',snapshot.boundary_register);write(sf,'omitted_boundary_scope',snapshot.omitted_boundary_records);
        write(sf,'branch_map',snapshot.branch_map);write(sf,'generator_map',snapshot.generator_map);
        write(sf,'interface_operator_members',snapshot.operators.members);write(sf,'interface_operator_registry',snapshot.operators.registry);
        write(sf,'audit_summary',fit.audit.summary);write(sf,'audit_bus',fit.audit.bus);write(sf,'audit_generator',fit.audit.generator);write(sf,'audit_branch',fit.audit.branch);
    end
    fprintf('%s qualified=%d proxy MAE=%.3f max=%.3f MW\n',sc.scenario_id,fit.electrical_baseline_qualified,mean(t.absolute_residual_mw),max(t.absolute_residual_mw));
end
% A separate HQ interpretation sensitivity never refits heldout observations.
sens_id="S1_2025_SUMMER_PEAK_PUBLIC";sens_index=find(inputs.snapshots.scenario_id==sens_id);
sens_options=struct('hq_boundary_policy','net_market_proxy_with_separate_Cedars');
if training_complete,sens_options.generation_participation=training_participation;end
sens_snapshot=build_compact_nyiso_operating_snapshot(modern,inputs,sens_id,sens_options);
% S1 is a training hour, but this sensitivity uses the frozen prediction rule.
sens_snapshot.snapshot.default_campaign_interface_fit_allowed=false;
[hq_sensitivity,sensitivity_attempts]=run_case(sens_snapshot,options,fullfile(folder,'HQ_net_market_sensitivity'));
hq_sensitivity.default_case_import_mw=sum(cases{sens_index}.snapshot.boundary_register.p_injection_mw);
hq_sensitivity.import_difference_mw=sum(sens_snapshot.boundary_register.p_injection_mw)-hq_sensitivity.default_case_import_mw;
out=struct('inputs',inputs,'base_build',base,'modern_build',modern,'cases',{cases}, ...
    'attempts',attempts,'comparison',comparison,'case_summary',case_summary,'tests',tests, ...
    'training_generation_participation',training_participation,'training_complete',training_complete, ...
    'all_snapshots_electrically_qualified',all(case_summary.electrical_baseline_qualified), ...
    'heldout_interface_targets_used',false,'observed_generator_dispatch_validated',false, ...
    'exact_public_interface_operators',false,'complete_HQ_boundary_scope_established',false, ...
    'electrical_baseline_qualified',all(case_summary.electrical_baseline_qualified)&&options.run_tests&&training_complete, ...
    'hq_sensitivity',hq_sensitivity,'sensitivity_attempts',sensitivity_attempts, ...
    'dlr_ready',false,'output_dir',string(folder),'options',options);
out.code_manifest=compact_ny_2025_code_manifest;
out.solver_protocol=struct('primary_solver',"MIPS",'fallback_solver',"IPOPT_if_available_and_primary_fails", ...
    'opf_start',0,'mips_cost_multiplier',1,'opf_violation',1e-8,'mips_feastol',1e-9, ...
    'mips_max_it',500,'fixed_PF_tolerance',1e-10,'fixed_PF_enforce_Q_limits',true, ...
    'training_prior_weight',.001,'prediction_prior_weight',1,'interface_scale_mw',500, ...
    'matpower_version',string(mpver),'matlab_version',string(version));
if options.write_outputs
    campaign_file=fullfile(folder,'compact_ny_2025_electrical_campaign.mat');
    save(campaign_file,'out','-v7');
    write(folder,'electrical_campaign_manifest',table("compact_ny_2025_electrical_campaign.mat",ny_reference_file_sha256(campaign_file), ...
        'VariableNames',{'artifact','sha256'}));
    write(folder,'electrical_code_manifest',out.code_manifest);
    for name=["snapshots","loads","interfaces","boundaries","external_records","source_manifest","generation_observations","rejected_pairings","boundary_channels","boundary_policy","boundary_sensitivity"]
        if isfield(inputs,name),write(folder,"source_"+name,inputs.(name));end
    end
    write(folder,'case_summary',case_summary);write(folder,'operating_attempts',attempts);write(folder,'interface_comparison',comparison);write(folder,'implementation_tests',tests);
    write(folder,'HQ_sensitivity_attempts',sensitivity_attempts);write(folder,'HQ_sensitivity_residuals',hq_sensitivity.residuals);
    if training_complete,write(folder,'frozen_training_generation_participation',table(cases{train(1)}.snapshot.generator_keys,training_participation, ...
            'VariableNames',{'generator_key','participation'}));end
    write_report(folder,out);
end
end
function [chosen,ledger]=run_case(snapshot,options,folder)
solvers="MIPS";if options.allow_ipopt_fallback&&have_feature('ipopt'),solvers(end+1)="IPOPT";end
ledger=table();chosen=[];
for k=1:numel(solvers)
    candidate=fit_compact_nyiso_operating_snapshot(snapshot,struct('solver',char(solvers(k))));
    a=candidate.bounded_audit.summary;
    row=table(snapshot.scenario_id,solvers(k),0,1,candidate.electrical_baseline_qualified, ...
        candidate.internal_interface_fit_used,candidate.network_and_injections_frozen,a.max_nodal_p_mismatch_mw, ...
        a.max_nodal_q_mismatch_mvar,candidate.mean_absolute_proxy_error_mw,candidate.max_absolute_proxy_error_mw, ...
        candidate.solver_error,candidate.replay_error,false, ...
        'VariableNames',{'scenario_id','solver','opf_start','mips_cost_multiplier','electrically_qualified', ...
        'interface_fit_used','hardware_frozen','bounded_P_residual_mw','bounded_Q_residual_mvar', ...
        'proxy_MAE_mw','proxy_max_error_mw','solver_error','replay_error','bounds_relaxed'});
    ledger=[ledger;row]; %#ok<AGROW>
    if options.write_outputs
        sf=fullfile(folder,char(snapshot.scenario_id));if ~isfolder(sf),mkdir(sf);end
        save(fullfile(sf,"attempt_"+string(k)+"_"+solvers(k)+".mat"),'candidate','-v7');
    end
    chosen=candidate;if candidate.electrical_baseline_qualified,break;end
end
end
function write(folder,name,t)
if istable(t),ny_lite_writetable_lf(t,fullfile(folder,string(name)+".csv"));end
end
function protect_legacy(folder,root)
p=lower(string(java.io.File(folder).getCanonicalPath()));
for name=["ny_only_package_a","ny_only_package_b","compact_npcc_ny"]
    ref=lower(string(java.io.File(fullfile(root,'output',name)).getCanonicalPath()));
    assert(p~=ref&&~startsWith(p,ref+filesep)&&~startsWith(ref,p+filesep),'compact_campaign:ProtectedPath','Historical artifacts are protected.');
end
end
function write_report(folder,o)
f=fopen(fullfile(folder,'ELECTRICAL_CALIBRATION_RESULTS.md'),'w');cleanup=onCleanup(@()fclose(f)); %#ok<NASGU>
fprintf(f,'# Compact NY matched-snapshot electrical results\n\n');
fprintf(f,'%d/%d snapshots pass bounded AC constraints and independent fixed-input PF. Electrical baseline qualified: %d.\n\n', ...
    nnz(o.case_summary.electrical_baseline_qualified),height(o.case_summary),o.electrical_baseline_qualified);
fprintf(f,'Scale policy: %s. A fixed year-specific summer-peak scale maps the reference peak to 10,902.2198 MW while preserving seasonal demand variation. Observed NYISO zonal MW and scheduled boundary P use the same year scale. Boundary Q=0 and bus landing splits are assumptions. Ten distinct scheduled channels include separate Cedars. The nested HQ_IMPORT_EXPORT record is excluded from the default total. A separate S1 sensitivity replaces HQ-NY with HQ_IMPORT_EXPORT without adding both; scheduled imports change by %.3f benchmark MW.\n\n',string(o.options.scale_policy),o.hq_sensitivity.import_difference_mw);
fprintf(f,'2025 S1-S4 fit seven declared AC interface proxies. Mean normalized training generation is frozen before S5/S6 prediction. Heldout and all 2019 interface values are used only for scoring, never optimizer targets or generation priors. Generator observations are unavailable: interface agreement does not validate dispatch.\n\n');
fprintf(f,'The seven operators remain conceptual/source-backed proxies with public completeness gaps. Total East is a partial F-G proxy; UPNY is six nonoverlapping local source circuits. Low fit residuals are calibration results, not exact-public-operator validation.\n\n');
fprintf(f,'| Scenario | Qualified | MAE benchmark MW | Maximum benchmark MW |\n|---|---:|---:|---:|\n');
for k=1:height(o.case_summary)
    r=o.case_summary(k,:);fprintf(f,'| %s | %d | %.3f | %.3f |\n',r.scenario_id,r.electrical_baseline_qualified,r.proxy_MAE_mw,r.proxy_max_error_mw);
end
fprintf(f,'\nNormalized errors use max(100 MW, absolute scaled observation) as denominator; near-zero targets are flagged. Observation-scale flows are uniform mathematical rescalings, not a full-size physical network. No thermal validation or DLR-ready claim is made.\n');
end
