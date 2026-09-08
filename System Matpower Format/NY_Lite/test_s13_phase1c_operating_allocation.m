function out=test_s13_phase1c_operating_allocation
%TEST_S13_PHASE1C_OPERATING_ALLOCATION Conservation and double-count guards.
% Bounded network feasibility is a separate gate and is not asserted here.
define_constants;
b=build_s13_phase1c_candidate(struct('write_outputs',false,'verbose',false));
i=build_electrical_reconstruction_inputs(b.candidate,'S1_2019_SUMMER_PEAK_PUBLIC');
a=apply_s13_phase1c_operating_allocation(i.candidate,i.scenario);
assert(all(a.zone_audit.conservation_pass)&&max(a.zone_audit.max_conservation_error)<1e-7);
assert(isequal(a.candidate.branch,i.candidate.branch)&& ...
    isequal(a.candidate.bus(:,[GS BS]),i.candidate.bus(:,[GS BS])));
ng=size(i.candidate.gen,1);
assert(isequal(a.candidate.gen(1:ng,GEN_STATUS),i.candidate.gen(:,GEN_STATUS)));
assert(all(isfinite(a.candidate.gen(:,[PMIN PMAX QMIN QMAX])),'all'));
assert(numel(a.Pg_prior_mw)==size(a.candidate.gen,1)&& ...
    numel(a.Pg_sigma_mw)==size(a.candidate.gen,1));
placeholder=a.generator_audit.source_Q_limits_placeholder;
assert(sum(placeholder)==1&&a.generator_audit.source_bus(placeholder)==1136);
g=a.generator_audit.gen_row(placeholder);
assert(a.candidate.gen(g,PMAX)==0&&a.candidate.gen(g,PMIN)==0&& ...
    max(abs(a.candidate.gen(g,[QMIN QMAX])))<1000);
rejected=false;
try,apply_s13_phase1c_operating_allocation(a.candidate,i.scenario);
catch e,rejected=strcmp(e.identifier,'apply_s13_phase1c_operating_allocation:AlreadyApplied');end
assert(rejected,'Repeated allocation must fail before moving any device twice.');
bad=i.scenario;bad.target_load_mw(bad.zone=="J")=bad.target_load_mw(bad.zone=="J")+1;
bad_rejected=false;
try,apply_s13_phase1c_operating_allocation(i.candidate,bad);
catch e,bad_rejected=strcmp(e.identifier,'apply_s13_phase1c_operating_allocation:LoadTarget');end
assert(bad_rejected,'Mismatched operating inputs must fail.');
assert(~a.promotion_eligible&&~a.source_shunt_qualification&& ...
    ~a.candidate.userdata.s13.construction_source_qualified);
out=struct('pass',true,'test_count',8,'max_conservation_error', ...
    max(a.zone_audit.max_conservation_error),'added_generator_rows',size(a.candidate.gen,1)-ng, ...
    'double_application_rejected',rejected,'mismatched_scenario_rejected',bad_rejected, ...
    'operating_feasibility_claimed',false);
disp(out);
end
