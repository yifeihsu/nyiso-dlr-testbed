function report=test_ny_regional_operating_contract
%TEST_NY_REGIONAL_OPERATING_CONTRACT Meaningful failure and bounded-PF gates.
define_constants;
c=loadcase('case9');c.bus(:,VMIN)=.95;c.bus(:,VMAX)=1.05;
b=struct('candidate',c,'generator_keys',"TEST:GEN:"+string((1:size(c.gen,1))'), ...
    'branch_keys',"TEST:BRANCH:"+string((1:size(c.branch,1))'));
b.allocation=struct('Pg_prior_mw',c.gen(:,PG),'Pg_sigma_mw',max(50,.25*(c.gen(:,PMAX)-c.gen(:,PMIN))));
r=reconstruct_ny_regional_operating_point(b);
assert(r.electrical_baseline_qualified&&r.bounded_audit.passed&&r.replay_audit.passed&& ...
    r.network_and_injections_frozen&&~r.minimum_relaxation_used&&r.fictitious_active_injection_mw==0&& ...
    ~r.internal_interface_fit_used&&~r.dlr_ready);
names="bounded_native_prior_and_independent_PF_pass";
q=reconstruct_ny_regional_operating_point(b,struct('solver','NOT_A_SOLVER'));
assert(~q.electrical_baseline_qualified&&~q.result.success&&strlength(q.solver_error)>0&& ...
    q.diagnostic_state_origin=="initial_input_after_solver_exception");
names(end+1)="solver_exception_is_an_explicit_unqualified_attempt";
x=b;x.candidate.gen(:,PMIN)=0;x.candidate.gen(:,PMAX)=20;
w=warning('off','all');cleanup=onCleanup(@()warning(w)); %#ok<NASGU>
q=reconstruct_ny_regional_operating_point(x);
assert(~q.electrical_baseline_qualified&&~q.replay_audit.passed&& ...
    isequal(q.result.gen(:,[PMIN PMAX QMIN QMAX]),x.candidate.gen(:,[PMIN PMAX QMIN QMAX])));
names(end+1)="insufficient_generation_does_not_relax_limits_or_qualify";
x=b;x.allocation.Pg_prior_mw(1)=NaN;
reject(@()reconstruct_ny_regional_operating_point(x),'ny_region:OperatingBounds');
names(end+1)="nonfinite_prior_rejected";
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
for folder={fullfile(root,'output','ny_only_package_a'),fullfile(root,'output','ny_only_package_a','nested'),fullfile(root,'output')}
    reject(@()run_ny_only_regional_candidate(struct('output_dir',folder{1},'run_operating',false,'run_tests',false)), ...
        'ny_region:OutputLocation');
end
names(end+1)="Package_A_equal_child_and_ancestor_output_paths_rejected";
report=table(names(:),true(numel(names),1),'VariableNames',{'test','passed'});disp(report);
end
function reject(f,id)
try,f();catch e,assert(strcmp(e.identifier,id),'Unexpected error %s',e.identifier);return;end
error('ny_region_test:MissingGuard','Expected rejection %s',id);
end
