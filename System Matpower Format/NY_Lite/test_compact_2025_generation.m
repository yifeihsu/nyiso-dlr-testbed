function out=test_compact_2025_generation(base)
%TEST_COMPACT_2025_GENERATION Source-event scaling and aggregate double counts.
if nargin<1,base=apply_compact_2025_infrastructure();end
o=apply_compact_2025_generation(base);g=o.candidate.gen;gamma=.355758660106238;
names="generation_validation";passed=o.generation_validation.pass;assert(passed);
assert(size(g,1)==64&&sum(o.ny_generator_mask)==37&&size(o.candidate.bus,1)==160 ...
    && isequal(o.candidate.bus,base.candidate.bus)&&isequal(o.candidate.branch,base.candidate.branch));
names(end+1)="two_identified_proxies_no_added_bus_or_branch";passed(end+1)=true;
assert(abs(g(63,9)-1100*gamma)<1e-12&&abs(g(64,9)-132*gamma)<1e-12 ...
    && abs(g(58,9)+g(63,9)-900)<1e-10&&abs(g(62,9)+g(64,9)-600)<1e-10);
names(end+1)="fixed_public_scale_and_G_K_capacity_carveout";passed(end+1)=true;
assert(abs(g(49,9)-(1200-528*gamma))<1e-10);
names(end+1)="Astoria_assumed_regional_share_removed_once";passed(end+1)=true;
assert(~any(g(:,1)==77)&&all(o.generation_retirement_register.additional_retirement_deduction_mw==0) ...
    && all(contains(o.generation_retirement_register.accounting_policy,"aggregate_composition_unknown")));
names(end+1)="IndianPoint_absent_does_not_claim_aggregate_retirement_complete";passed(end+1)=true;
assert(all(g(63:64,[2:5 10])==0,'all')&&all(~o.generation_prior_register.dispatch_observed) ...
    && isequal(o.candidate.bus(:,2),base.candidate.bus(:,2)));
names(end+1)="new_P_only_proxies_no_invented_Q_voltage_or_observed_dispatch";passed(end+1)=true;
assert(all(o.generator_keys(63:64)==["NY2025:GEN:CRICKET_VALLEY:PV73";"NY2025:GEN:SOUTH_FORK:K9003"]) ...
    && numel(unique(o.generator_keys))==64);
names(end+1)="new_and_inherited_generator_identity_unique";passed(end+1)=true;
off=apply_compact_2025_generation(base,struct('include_assumed_astoria_retirement',false));
assert(off.candidate.gen(49,9)==1200&&all(off.generation_change_register.removed_from_parent_slot_mw(3)==0));
names(end+1)="Astoria_mapping_assumption_has_no_retirement_sensitivity";passed(end+1)=true;
wind=apply_compact_2025_generation(base,struct('south_fork_available_fraction',.25));
assert(abs(wind.candidate.gen(64,9)-.25*132*gamma)<1e-10 ...
    && wind.candidate.gen(62,9)==g(62,9));
names(end+1)="wind_availability_derates_proxy_without_recreating_retired_parent_capacity";passed(end+1)=true;
reject(@()apply_compact_2025_generation(o),'AlreadyApplied');
names(end+1)="double_application_rejected";passed(end+1)=true;
bad=base;bad.candidate.gen(58,1)=76;bad.full_candidate=bad.candidate;
reject(@()apply_compact_2025_generation(bad),'SlotIdentity');
names(end+1)="wrong_parent_slot_mapping_rejected";passed(end+1)=true;
reject(@()apply_compact_2025_generation(base,struct('south_fork_available_fraction',1.1)),'Bounds');
names(end+1)="unbounded_wind_availability_rejected";passed(end+1)=true;
out=struct('pass',all(passed),'assertion_groups',numel(passed), ...
    'gates',table(names(:),passed(:),'VariableNames',{'test','passed'}));disp(out.gates);
end

function reject(fn,suffix)
id=['compact_2025_gen:' suffix];
try,fn();catch err,assert(strcmp(err.identifier,id),'Unexpected error %s',err.identifier);return;end
error('compact_2025_gen_test:MissingGuard','Expected %s.',id);
end
