function tests=test_compact_independent_generation_prior
%TEST_COMPACT_INDEPENDENT_GENERATION_PRIOR Synthetic source data only.
z=string(('A':'K')');m=struct('baseMVA',100,'bus',zeros(11,13),'gen',zeros(6,21),'branch',zeros(0,13));
m.bus(:,1)=(1:11)';m.userdata.nyiso_physical_zone=cellstr(z);
m.gen(:,1)=[1;1;2;3;3;4];m.gen(:,8)=[1;1;1;1;0;1];
m.gen(:,10)=[10;20;15;0;0;0];m.gen(:,9)=[110;320;15;200;500;1];
m.gen(:,2:3)=7;m.gen(:,4)=999;m.gen(:,5)=-999;
s=struct('candidate',m,'scenario_id',"synthetic",'generator_keys',"GEN"+string((1:6)'), ...
    'snapshot',table(.5,'VariableNames',{'scale_factor_gamma'}));
prior=[230;50;300;1;0;0;0;80;0;0;0];
p=table(repmat("synthetic",11,1),z,prior/.5,prior,true(11,1),repmat("synthetic_fixture",11,1), ...
    'VariableNames',{'scenario_id','zone','prior_public_mw','prior_benchmark_mw','coverage_qualified','source_method'});
o=apply_compact_independent_generation_prior(s,p);names=strings(0,1);
assert(isequal(o.Pg_prior_mw,[60;170;15;200;0;1]));
names(end+1)="headroom_allocation_preserves_PMIN_and_clips_each_online_generator";
q=o.independent_prior_zone_ledger;
assert(q.bounded_generator_prior_mw(q.zone=="A")==230&&q.total_unrepresented_prior_mw(q.zone=="A")==0);
assert(q.unallocated_source_prior_mw(q.zone=="B")==35&&q.clipped_source_prior_mw(q.zone=="C")==100);
assert(q.unallocated_source_prior_mw(q.zone=="H")==80&&q.online_generator_count(q.zone=="H")==0);
names(end+1)="fixed_no_generator_and_capacity_shortfalls_remain_in_source_zones";
assert(abs(sum(prior)-sum(o.Pg_prior_mw)-sum(q.total_unrepresented_prior_mw))<1e-10);
names(end+1)="all_source_generation_accounted_with_signed_unrepresented_ledger";
assert(isequal(o.candidate.bus,m.bus)&&isequal(o.candidate.branch,m.branch) ...
    &&isequal(o.candidate.gen(:,[1 3:end]),m.gen(:,[1 3:end])));
names(end+1)="all_hardware_controls_and_reactive_priors_preserved";
assert(o.Pg_prior_mw(5)==0&&o.independent_prior_generator_ledger.within_zone_capacity_share(5)==0);
names(end+1)="offline_capability_never_absorbs_source_prior";
assert(max(abs(o.Pg_sigma_mw(1:2)-50*sqrt([.25;.75])))<1e-12);
delta=12*[.25;.75];assert(abs(sum((delta./o.Pg_sigma_mw(1:2)).^2)-(12/50)^2)<1e-12);
names(end+1)="coherent_zonal_objective_weight_independent_of_aggregate_count";
assert(all(o.Pg_sigma_mw>=1)&&all(q.zone_sigma_mw>=50));
names(end+1)="finite_sigma_floors_apply_to_fixed_and_zero_headroom_records";
ps=p;ps.prior_benchmark_mw(1)=0;ps.prior_public_mw(1)=0;os=apply_compact_independent_generation_prior(s,ps);
assert(isequal(os.Pg_prior_mw(1:2),[10;20])&&os.independent_prior_zone_ledger.clipped_source_prior_mw(1)==-30);
names(end+1)="below_minimum_source_prior_keeps_negative_clipping_evidence";
sp=s;sp.interface_targets=table(1e9,'VariableNames',{'target_flow_mw'});sp.candidate.gen(:,2)=-100;
op=apply_compact_independent_generation_prior(sp,p);assert(isequal(op.Pg_prior_mw,o.Pg_prior_mw));
names(end+1)="allocation_does_not_read_old_dispatch_or_interface_targets";
bad=p;bad.coverage_qualified(1)=false;reject(@()apply_compact_independent_generation_prior(s,bad),'SourceCoverage');
names(end+1)="unqualified_source_coverage_rejected";
bad=p;bad.zone(2)="A";reject(@()apply_compact_independent_generation_prior(s,bad),'Zones');
names(end+1)="missing_or_duplicate_source_zone_rejected";
bad=p;bad.prior_benchmark_mw(1)=NaN;reject(@()apply_compact_independent_generation_prior(s,bad),'SourceValue');
names(end+1)="nonfinite_source_prior_rejected";
bad=p;bad.prior_public_mw(1)=bad.prior_public_mw(1)+100;reject(@()apply_compact_independent_generation_prior(s,bad),'Scale');
names(end+1)="mismatched_actual_and_benchmark_MW_rejected";
bad=s;bad.generator_keys(2)=bad.generator_keys(1);reject(@()apply_compact_independent_generation_prior(bad,p),'Keys');
names(end+1)="duplicate_generator_identity_rejected";
assert(~o.electrical_baseline_qualified&&~o.dlr_ready&&~o.independent_prior_policy.cross_zone_reallocation ...
    &&~o.independent_prior_policy.interface_targets_used&&isempty(o.generation_participation)&&isnan(o.prior_loss_fraction));
names(end+1)="source_prior_is_not_observed_dispatch_or_electrical_qualification";
n=p(1,:);n.generator_key="GEN1";n.prior_public_mw=200;n.prior_benchmark_mw=100;
on=apply_compact_independent_generation_prior(s,p,n);
assert(isequal(on.Pg_prior_mw(1:2),[100;130])&&isequal(on.Pg_sigma_mw,o.Pg_sigma_mw));
assert(on.independent_prior_zone_ledger.named_source_subset_mw(1)==100);
names(end+1)="named_estimates_reserved_before_generic_allocation_without_changing_sigma";
n.prior_public_mw=300;n.prior_benchmark_mw=150;on=apply_compact_independent_generation_prior(s,p,n);
assert(isequal(on.Pg_prior_mw(1:2),[110;80])&&on.independent_named_prior_ledger.clipped_source_prior_mw==40);
assert(on.independent_prior_zone_ledger.total_unrepresented_prior_mw(1)==40);
names(end+1)="named_capability_clipping_is_not_reassigned_to_generic_devices";
n.generator_key="missing_key";on=apply_compact_independent_generation_prior(s,p,n);
assert(sum(on.Pg_prior_mw(1:2))==80&&on.independent_named_prior_ledger.unallocated_source_prior_mw==150);
names(end+1)="unmapped_named_subset_retained_as_unallocated_source_generation";
n=p(3,:);n.generator_key="GEN5";n.prior_public_mw=100;n.prior_benchmark_mw=50;
on=apply_compact_independent_generation_prior(s,p,n);
assert(on.Pg_prior_mw(5)==0&&on.independent_named_prior_ledger.unallocated_source_prior_mw==50 ...
    &&on.independent_prior_zone_ledger.total_unrepresented_prior_mw(3)==100);
names(end+1)="offline_named_source_is_neither_dispatched_nor_reassigned";
n=p(1,:);n.generator_key="GEN1";n.prior_public_mw=1000;n.prior_benchmark_mw=500;
reject(@()apply_compact_independent_generation_prior(s,p,n),'NamedSubset');
names(end+1)="named_subset_cannot_exceed_zonal_total";
n=p(1,:);n.generator_key="GEN3";
reject(@()apply_compact_independent_generation_prior(s,p,n),'NamedIdentity');
names(end+1)="named_model_and_source_zones_must_agree";
tests=table(names(:),true(numel(names),1),'VariableNames',{'test','passed'});disp(tests);
end
function reject(fn,suffix)
id="independent_prior:"+suffix;
try,fn();catch e,assert(string(e.identifier)==id,'Unexpected error %s instead of %s.',e.identifier,id);return;end
error('independent_prior_test:MissingGuard','Expected %s.',id);
end
