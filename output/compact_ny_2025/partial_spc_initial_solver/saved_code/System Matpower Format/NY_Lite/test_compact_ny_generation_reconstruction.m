function tests=test_compact_ny_generation_reconstruction
%TEST_COMPACT_NY_GENERATION_RECONSTRUCTION Target-free assembly and fail-closed guards.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
src=fullfile(root,'output','compact_ny_2025','generation_sources');
folder=tempname;mkdir(folder);cleanup=onCleanup(@()rmdir(folder,'s')); %#ok<NASGU>
names=["snapshots","loads","boundaries","external_records","interfaces"];
for name=names,copyfile(fullfile(src,'hourly_inputs',name+".csv"),fullfile(folder,name+".csv"));end
copyfile(fullfile(src,'combined','zonal_generation_priors.csv'),fullfile(folder,'priors.csv'));
copyfile(fullfile(src,'generation_reconstruction_protocol.json'),fullfile(folder,'protocol.json'));
opts=struct('input_dir',folder,'prior_file',fullfile(folder,'priors.csv'),'named_prior_file',"", ...
    'source_protocol_file',fullfile(folder,'protocol.json'),'output_dir',fullfile(folder,'result'), ...
    'scenario_ids',["S1_2019_SUMMER_PEAK_PUBLIC";"S1_2025_SUMMER_PEAK_PUBLIC"], ...
    'write_outputs',false,'run_tests',false,'run_operating',false);
out=run_compact_ny_generation_reconstruction(opts);names=strings(0,1);
assert(isequal(out.case_summary.generator_record_count,[35;37])&&all(out.case_summary.input_coverage_qualified) ...
    &&all(cellfun(@isempty,out.cases))&&isempty(out.attempts));
names(end+1)="both_vintages_assemble_with_exact_generator_inventory_without_optimizer";
assert(~out.electrical_baseline_qualified&&~out.all_eligible_snapshots_electrically_qualified ...
    &&~out.all_registered_snapshots_electrically_qualified&&~out.interface_scoring_performed ...
    &&all(isnan(out.blind_interface_predictions.model_flow_mw))&&height(out.blind_interface_predictions)==14);
names(end+1)="assembly_and_unscored_predictions_do_not_claim_electrical_qualification";
assert(all(out.case_summary.load_boundary_accounting_error_mw<1e-7) ...
    &&all(out.zone_generation_deviations.online_generator_count(out.zone_generation_deviations.zone=="H")==0));
names(end+1)="load_accounting_and_unrepresented_zone_H_remain_explicit";
f=fullfile(folder,'interfaces.csv');t=readtable(f,'TextType','string');t.target_flow_mw(1)=1;
ny_lite_writetable_lf(t,f);reject(@()run_compact_ny_generation_reconstruction(opts),'generation_campaign:TargetUnblinded');
names(end+1)="finite_internal_targets_rejected_before_any_snapshot_or_solver";
copyfile(fullfile(src,'hourly_inputs','interfaces.csv'),f);
f=fullfile(folder,'priors.csv');p=readtable(f,'TextType','string');
ix=p.scenario_id==opts.scenario_ids(1)&p.zone=="A";p.prior_benchmark_mw(ix)=NaN;ny_lite_writetable_lf(p,f);
out=run_compact_ny_generation_reconstruction(opts);
assert(~out.case_summary.input_coverage_qualified(1)&&out.case_summary.input_coverage_qualified(2) ...
    &&isempty(out.snapshots{1})&&~isempty(out.snapshots{2})&&contains(out.case_summary.skip_reason(1),"source_generation"));
names(end+1)="missing_source_prior_skips_only_affected_snapshot_and_preserves_registration";
copyfile(fullfile(src,'combined','zonal_generation_priors.csv'),f);
f=fullfile(folder,'external_records.csv');e=readtable(f,'TextType','string');
ix=find(e.scenario_id==opts.scenario_ids(1)&e.public_interface_name=="SCH - HQ_CEDARS",1);e.target_import_mw(ix)=e.target_import_mw(ix)+1;
ny_lite_writetable_lf(e,f);out=run_compact_ny_generation_reconstruction(opts);
assert(~out.case_summary.input_coverage_qualified(1)&&contains(out.case_summary.skip_reason(1),"boundary_channels"));
names(end+1)="boundary_actual_benchmark_scale_mismatch_skips_snapshot";
copyfile(fullfile(src,'hourly_inputs','external_records.csv'),f);
n=readtable(fullfile(src,'combined','named_generator_priors.csv'),'TextType','string');
n(n.scenario_id==opts.scenario_ids(2)&n.generator_key=="NY2025:GEN:CRICKET_VALLEY:PV73",:)=[];
opts.named_prior_file=fullfile(folder,'named_priors.csv');ny_lite_writetable_lf(n,opts.named_prior_file);
out=run_compact_ny_generation_reconstruction(opts);
assert(out.case_summary.input_coverage_qualified(1)&&~out.case_summary.input_coverage_qualified(2) ...
    &&contains(out.case_summary.skip_reason(2),"named_generator_source"));
names(end+1)="missing_registered_named_subset_cannot_silently_revert_to_generic_allocation";
opts.output_dir=fullfile(root,'output','compact_ny_2025','electrical_fixed_peak');
reject(@()run_compact_ny_generation_reconstruction(opts),'generation_campaign:FrozenOutput');
names(end+1)="frozen_electrical_artifact_directory_rejected";
tests=table(names(:),true(numel(names),1),'VariableNames',{'test','passed'});disp(tests);
end
function reject(fn,id)
try,fn();catch e,assert(string(e.identifier)==id,'Unexpected error %s instead of %s.',e.identifier,id);return;end
error('generation_campaign_test:MissingGuard','Expected %s.',id);
end
