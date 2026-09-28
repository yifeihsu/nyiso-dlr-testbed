function out=run_electrical_model_reproduction(options)
%RUN_ELECTRICAL_MODEL_REPRODUCTION Review-driven electrical candidate evidence.
% Historical Phase1A/B files and the promoted operating-case pointer remain
% unchanged. This runner reports implementation tests separately from failed
% scientific qualification gates; no thermal model or automatic promotion.
if nargin<1,options=struct();end
if ~isfield(options,'write_outputs'),options.write_outputs=true;end
if ~isfield(options,'run_tests'),options.run_tests=true;end
if ~isfield(options,'run_operating_diagnostic'),options.run_operating_diagnostic=true;end
root=fileparts(mfilename('fullpath'));h=fullfile(root,'System Matpower Format','NY_Lite');
addpath(h);addpath(fileparts(h));
if ~isfield(options,'output_dir'),options.output_dir=fullfile(root,'output','electrical_model_review');end
folder=options.output_dir;if options.write_outputs && ~isfolder(folder),mkdir(folder);end
tests=table();
if options.run_tests
    a=contemporary_test_inputs;tests=add_test(tests,"contemporary_inputs",a.checks,a.pass);
    a=test_s13_phase1c_candidate;tests=add_test(tests,"phase1c_adversarial",height(a),all(a.rejected));
    a=test_s13_phase1c_operating_allocation;tests=add_test(tests,"phase1c_operating_allocation",a.test_count,a.pass);
    a=test_s14_external_equivalent;tests=add_test(tests,"external_reduction",height(a),all(a.passed));
    a=test_electrical_reconstruction;tests=add_test(tests,"bounded_reconstruction",a.test_count,a.pass);
    a=test_registered_residual_network;tests=add_test(tests,"registered_residual_fit",a.test_count,a.pass);
    a=test_electrical_boundary_feasibility;tests=add_test(tests,"boundary_accounting",height(a),all(a.passed));
end
b=build_s13_phase1c_candidate(struct('write_outputs',false,'verbose',false));
tests=add_test(tests,"phase1c_source_identity",height(b.validation.gates),b.validation.all_passed);
assert(all(tests.passed),'Electrical implementation regression failed.');
contract=research_model_contract;
inventory=contemporary_generator_inventory(b.candidate,"s13_phase1c_historical_candidate");
register_status=contemporary_validate_registers([],inventory);
T=readtable(fullfile(h,'nyiso_public_scenarios.csv'),'TextType','string');
certificates=table();scenarios=table();generator_register=table();operator_register=table();
load_allocation=table();generation_allocation=table();allocation_conservation=table();
for k=1:height(T)
    inputs=build_electrical_reconstruction_inputs(b.candidate,T.scenario_id(k));
    allocated=apply_s13_phase1c_operating_allocation(inputs.candidate,inputs.scenario);
    inputs.candidate=allocated.candidate;
    inputs.controls.Pg_prior_mw=allocated.Pg_prior_mw;
    inputs.controls.Pg_sigma_mw=allocated.Pg_sigma_mw;
    la=allocated.load_audit;la.scenario_id=repmat(T.scenario_id(k),height(la),1);
    ga=allocated.generator_audit;ga.scenario_id=repmat(T.scenario_id(k),height(ga),1);
    za=allocated.zone_audit;za.scenario_id=repmat(T.scenario_id(k),height(za),1);
    load_allocation=[load_allocation;la];generation_allocation=[generation_allocation;ga]; %#ok<AGROW>
    allocation_conservation=[allocation_conservation;za]; %#ok<AGROW>
    cert=audit_electrical_boundary_feasibility(inputs);
    tab=cert.components;tab.scenario_id=repmat(T.scenario_id(k),height(tab),1);
    certificates=[certificates;tab]; %#ok<AGROW>
    m=inputs.candidate;nr=size(m.gen,1);
    actual=table(repmat(T.scenario_id(k),nr,1),(1:nr)',m.gen(:,1),m.gen(:,8), ...
        m.gen(:,10),m.gen(:,9),m.gen(:,5),m.gen(:,4), ...
        inputs.controls.Pg_prior_mw(:),inputs.controls.Pg_sigma_mw(:), ...
        repmat("final_post_allocation_reconstructed_controls",nr,1), ...
        'VariableNames',{'scenario_id','gen_row','bus_id','status','pmin_mw','pmax_mw', ...
        'qmin_mvar','qmax_mvar','Pg_prior_mw','Pg_sigma_mw','provenance'});
    generator_register=[generator_register;actual]; %#ok<AGROW>
    op=inputs.operator_register;op.scenario_id=repmat(T.scenario_id(k),height(op),1);
    operator_register=[operator_register;op]; %#ok<AGROW>
    if cert.provably_infeasible
        status="blocked_by_external_active_power_accounting";success=false;movement=NaN;violation=NaN;exitflag=NaN;
    elseif options.run_operating_diagnostic
        reconstruction=reconstruct_ac_operating_point(inputs.candidate,inputs.controls, ...
            struct('max_iterations',200,'verbose',false));
        success=reconstruction.success;movement=reconstruction.dispatch_movement_mw;
        violation=reconstruction.max_constraint_error_pu;exitflag=reconstruction.solver_exitflag;
        status="bounded_reconstruction_failed";if success,status="bounded_reconstruction_feasible_not_independent_validation";end
    else
        status="not_run";success=false;movement=NaN;violation=NaN;exitflag=NaN;
    end
    scenarios=[scenarios;table(T.scenario_id(k),status,success,movement,violation,exitflag,false, ...
        'VariableNames',{'scenario_id','status','bounded_ac_success','dispatch_movement_mw', ...
        'max_constraint_error_pu','solver_exitflag','independent_public_validation'})]; %#ok<AGROW>
end
% A diagnostic source can support reduction identity without qualifying the
% physical overlap, public reconstruction, or contemporary infrastructure.
source=runpf(b.candidate,mpoption('verbose',0,'out.all',0));
assert(source.success,'Inherited Phase1C diagnostic power flow failed.');
source_label="phase1c_inherited_unqualified_snapshot";operating=struct('success',false);
allocation=struct();
if options.run_operating_diagnostic
    inputs=build_electrical_reconstruction_inputs(b.candidate,T.scenario_id(1));
    if exist('apply_s13_phase1c_operating_allocation','file')==2
        allocation=apply_s13_phase1c_operating_allocation(inputs.candidate,inputs.scenario);
        inputs.candidate=allocation.candidate;
        inputs.controls.Pg_prior_mw=allocation.Pg_prior_mw;
        inputs.controls.Pg_sigma_mw=allocation.Pg_sigma_mw;
    end
    prior_only=rmfield(inputs.controls,{'operator_from','operator_to','target_mw','tolerance_mw'});
    operating=reconstruct_ac_operating_point(inputs.candidate,prior_only, ...
        struct('max_iterations',250,'verbose',true));
    if operating.success
        source=operating.result;source_label="phase1c_bounded_prior_only_reconstruction";
    end
end
reduction=build_s14_external_equivalent(source);
direct=validate_s14_against_s13_full(source,reduction);
responses=validate_electrical_transfer_responses(source,reduction);
status=table(["implementation_regressions";"phase1c_source_identity"; ...
    "contemporary_register_accounting";"bounded_prior_only_operating_point"; ...
    "passive_external_reduction_identity";"reduced_operating_limits"; ...
    "six_historical_public_reconstructions";"internal_overlap_resolution"; ...
    "contemporary_asset_and_generator_mapping";"independent_public_heldout_validation"; ...
    "promoted_operating_model"], ...
    [all(tests.passed);b.validation.all_passed;register_status.pass;operating.success; ...
    reduction.direct_passed && direct.reduction_metrics_passed;direct.passed; ...
    all(scenarios.bounded_ac_success);false;false;false;false], ...
    ["Executable tests only";"53 exact PERFORM elements; historical construction"; ...
    "Dated register validation; no asset instantiation claim"; ...
    "Assumed/reconstructed inputs; regional public targets excluded"; ...
    source_label;"Independent PF replay with finite generator limits"; ...
    "Regional accounting and bounded AC reconstruction; in-sample"; ...
    "Source-backed passive port targets still required"; ...
    "Current engineering parameters and unit crosswalk absent"; ...
    "Frozen transfer diagnostics are not held-out public observations"; ...
    "No promotion while required scientific gates remain open"], ...
    'VariableNames',{'gate','passed','evidence_scope'});
out=struct('tests',tests,'phase1c',b,'contract',contract,'status',status, ...
    'contemporary_register_status',register_status,'scenario_status',scenarios, ...
    'boundary_certificates',certificates,'source',source,'source_label',source_label, ...
    'operating',operating,'allocation',allocation,'reduction',reduction,'direct',direct, ...
    'responses',responses,'promotion_eligible',false);
if options.write_outputs
    write(tests,'implementation_tests');write(status,'qualification_gates');
    write(scenarios,'historical_scenario_status');write(certificates,'boundary_feasibility');
    write(generator_register,'historical_generator_controls');write(operator_register,'regional_operator_register');
    write(load_allocation,'downstate_load_allocation');write(generation_allocation,'downstate_generation_allocation');
    write(allocation_conservation,'downstate_allocation_conservation');
    write(inventory,'contemporary_generator_inventory');
    write(reduction.retention.register,'s14_retention');write(reduction.external_register,'s14_multiport');
    write(reduction.parameter_register,'s14_equivalent_parameters');
    write(reduction.injection_register,'s14_boundary_injections');
    write(reduction.external_loss_accounting,'s14_external_loss_accounting');
    write(direct.gates,'s14_direct_replay');write(direct.interfaces,'s14_interface_replay');
    write(responses,'frozen_transfer_responses');
    candidate=reduction.candidate; %#ok<NASGU>
    save(fullfile(folder,'s14_electrical_diagnostic.mat'),'candidate','source');
end
disp(status);fprintf('Electrical candidate: %d buses, %d branches; %d external buses eliminated. Promotion=false.\n', ...
    size(reduction.candidate.bus,1),size(reduction.candidate.branch,1),numel(reduction.eliminated_external_bus_ids));
    function write(t,name)
        ny_lite_writetable_lf(t,fullfile(folder,[name '.csv']));
    end
end
function t=add_test(t,name,count,passed)
t=[t;table(string(name),count,logical(passed),'VariableNames',{'suite','checks','passed'})];
end
