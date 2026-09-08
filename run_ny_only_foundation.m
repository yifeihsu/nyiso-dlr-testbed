function out=run_ny_only_foundation(options)
%RUN_NY_ONLY_FOUNDATION Package A: original actual-MW NY source benchmark.
% Fast implementation tests never qualify an operating point. Default full
% run reproduces source, removes boundary/reference generators, solves a
% bounded prior-only reference and writes independently replayable inputs.
if nargin<1,options=struct();end
options=defaults(options,'write_outputs',true,'run_tests',true,'run_operating',true);
root=fileparts(mfilename('fullpath'));h=fullfile(root,'System Matpower Format','NY_Lite');addpath(h);
if ~isfield(options,'output_dir'),options.output_dir=fullfile(root,'output','ny_only_package_a');end
folder=options.output_dir;
if options.write_outputs&&~isfolder(folder),mkdir(folder);end
n=normalize_perform_ny_source(struct('write_outputs',options.write_outputs, ...
    'output_dir',fullfile(folder,'source_inventory')));
contract=research_model_contract('historical_actual_mw');tests=table();
if options.run_tests
    a=test_normalize_perform_ny_source;tests=add_test(tests,"source_normalization_adversarial",a.assertion_groups,a.pass);
    a=test_research_model_contract;tests=add_test(tests,"model_contract",height(a),all(a.passed));
    a=test_ny_boundary_assembly;tests=add_test(tests,"fixed_boundary_assembly",a.test_count,a.pass);
    a=test_ny_ac_reference_audit;tests=add_test(tests,"physical_unit_audit",height(a),all(a.passed));
    a=test_ny_prior_reconstruction;tests=add_test(tests,"bounded_prior_backend",height(a),all(a.passed));
end
tests=add_test(tests,"immutable_source_inventory",height(n.validation.gates),n.validation.pass);
assert(all(tests.passed),'run_ny_only_foundation:Tests','Implementation checks failed.');
snapshot=struct('success',false,'status','not_run');reference=struct('electrical_baseline_qualified',false);
b=build_ny_boundary_register(n);qualified=false;
if options.run_operating
    source=runpf(n.source,mpoption('verbose',0,'out.all',0,'pf.enforce_q_lims',1,'pf.tol',1e-10));
    assert(source.success,'run_ny_only_foundation:SourcePF','Original source PF failed; no qualified reference written.');
    audit=audit_ny_ac_reference(source,struct('generator_keys',n.generator_inventory.device_key, ...
        'branch_keys',n.branch_inventory.device_key));
    snapshot=struct('success',logical(source.success),'status','source_snapshot_reproduced', ...
        'result',source,'audit',audit,'source_assumptions_preserved',true, ...
        'electrical_baseline_qualified',false);
    b=build_ny_boundary_register(n,struct('snapshot_case',source,'write_outputs',options.write_outputs,'output_dir',folder));
    reference=build_ny_foundation_reference(n,b);
    qualified=reference.electrical_baseline_qualified;
end
status=table(["immutable_source_inventory";"source_snapshot_pf";"original_source_within_limits"; ...
    "bounded_NY_only_reference";"independent_fixed_input_replay";"foundation_electrical_baseline_qualified"; ...
    "final_S14_operating_candidate_qualified";"contemporary_validation";"DLR_ready"], ...
    [n.validation.pass;snapshot.success;options.run_operating&&snapshot.audit.passed; ...
    qualified;qualified;qualified;false;false;false], ...
    ["1576 buses / 2371 branches / 615 source generator records"; ...
    "Historical source assumptions preserved; violations explicitly retained"; ...
    "Marcy RF source active bound is not silently enlarged"; ...
    "Fixed gross loads, boundary PQ, network parameters and native capability bounds"; ...
    "Frozen dispatch and voltage targets; finite limits and reference adjustment audited"; ...
    "One assumed 2019 PERFORM source benchmark only"; ...
    "Package B internal reconstruction remains future work"; ...
    "Packages C/D contemporary scenarios and held-out validation remain future work"; ...
    "Thermal identity and physical parameters are not qualified by this reference"], ...
    'VariableNames',{'gate','passed','evidence_scope'});
out=struct('inventory',n,'contract',contract,'boundary',b,'source_snapshot',snapshot, ...
    'reference',reference,'tests',tests,'status',status,'electrical_baseline_qualified',qualified, ...
    'qualification_scope','assumed_2019_PERFORM_source_reference_only', ...
    'contemporary_validation_coverage','not_evaluated','dlr_ready',false,'output_dir',folder);
if options.write_outputs
    write(tests,'implementation_tests');write(status,'qualification_status');
    if options.run_operating
        write_audit(snapshot.audit,'original_source');
        write_audit(reference.fixed_control_trial_audit,'fixed_control_repair');
        write_audit(reference.bounded_audit,'bounded_reconstruction');
        write_audit(reference.replay_audit,'independent_replay');
        write(reference.support_register,'assumed_reactive_support');
        write(reference.application.bus_injection_ledger,'gross_effective_load_ledger');
        write(reference.application.native_generator_map,'native_generator_map');
        write(reference.application.accounting,'boundary_assembly_accounting');
        write(reference.accounting,'reference_power_accounting');
        write(reference.dispatch,'native_and_support_dispatch');
        write(reference.reference_adjustment,'reference_replay_adjustment');
        attempted=table(["original_source_snapshot";"fixed_control_repair";"bounded_prior_only_reconstruction";"independent_fixed_input_replay"], ...
            [snapshot.success;reference.fixed_control_trial.success;reference.reconstruction.result.success;reference.reconstruction.fixed_input_pf.success], ...
            [snapshot.audit.passed;reference.fixed_control_trial_audit.passed;reference.bounded_audit.passed;reference.replay_audit.passed], ...
            false(4,1),'VariableNames',{'attempt','solver_or_pf_converged','all_declared_limits_passed','relaxation_used'});
        write(attempted,'operating_attempts');
        mpc=reference.reconstruction.result; %#ok<NASGU>
        % MATPOWER uses this frozen bounded dispatch for a fresh PF. No solver
        % optimization result or stored terminal flows are accepted as replay.
        generator_keys=reference.generator_keys;branch_keys=n.branch_inventory.device_key; %#ok<NASGU>
        gross_boundary_ledger=reference.application.bus_injection_ledger; %#ok<NASGU>
        source_manifest=n.source_manifest;expected_qualified=qualified; %#ok<NASGU>
        boundary_register=b.boundary_register; %#ok<NASGU>
        save(fullfile(folder,'ny_foundation_reference.mat'),'mpc','generator_keys','branch_keys', ...
            'gross_boundary_ledger','source_manifest','expected_qualified','boundary_register');
        fingerprint=table("ny_foundation_reference.mat",ny_reference_file_sha256(fullfile(folder,'ny_foundation_reference.mat')), ...
            'VariableNames',{'artifact','sha256'});
        write(fingerprint,'reference_input_manifest');
        write_report(out,folder);
    end
end
disp(status);
    function write(t,name),ny_lite_writetable_lf(t,fullfile(folder,[name '.csv']));end
    function write_audit(a,name)
        for f={'summary','bus','generator','branch'},write(a.(f{1}),[name '_' f{1}]);end
    end
end
function t=add_test(t,name,count,passed)
t=[t;table(string(name),count,logical(passed),'VariableNames',{'suite','checks','passed'})];
end
function s=defaults(s,varargin)
for k=1:2:numel(varargin),if ~isfield(s,varargin{k}),s.(varargin{k})=varargin{k+1};end,end
end
function write_report(out,folder)
r=out.reference;s=out.source_snapshot.audit.summary;a=r.accounting;
fid=fopen(fullfile(folder,'NY_ONLY_FOUNDATION_RESULTS.md'),'w');assert(fid>=0);closer=onCleanup(@()fclose(fid)); %#ok<NASGU>
fprintf(fid,'# NY-only Package A reference\n\n');
fprintf(fid,'Electrical qualification: **%s**, scoped to one assumed 2019 PERFORM source reference. Final S14 candidate, contemporary coverage and DLR readiness remain unqualified.\n\n',string(out.electrical_baseline_qualified));
fprintf(fid,'The immutable source contains 1576 buses, 2371 branches and 615 generator records (not physical-unit count). Its reproduced PF converges, with %d generator limit violation(s); maximum active violation %.6f MW.\n\n',s.violated_generators,s.max_generator_p_violation_mw);
fprintf(fid,'Twenty boundary proxies are represented by fixed PQ injections at original NY bus IDs. Inactive records remain zero. The separate Marcy RF placeholder is removed without any P/Q injection. A distinct assumed Marcy Q-only PV device has P=0 and Q bounds [-900,900] MVAr. Roseton bus847 supplies the native angle reference.\n\n');
fprintf(fid,'| Quantity | Value |\n|---|---:|\nGross demand | %.6f MW |\nFixed net boundary injection | %.6f MW |\nNative generation | %.6f MW |\nBranch and shunt losses | %.6f MW |\nPower-accounting error | %.9g MW |\nNative dispatch L1 movement from source priors | %.6f MW |\nBoundary schedule movement | %.6f MW |\nAssumed support active injection | %.9g MW |\nAssumed support Q | %.6f MVAr |\n', ...
    a.gross_load_mw,a.fixed_boundary_p_mw,a.native_generation_mw,a.total_loss_mw,a.balance_error_mw, ...
    a.native_dispatch_l1_movement_mw,a.boundary_schedule_movement_mw,a.assumed_support_p_mw,a.assumed_support_q_mvar);
fprintf(fid,'| Native reactive dispatch L1 movement | %.6f MVAr |\n| Maximum voltage movement from source | %.6f pu |\n', ...
    a.native_reactive_l1_movement_mvar,a.max_voltage_movement_from_source_pu);
fprintf(fid,'\nThe bounded solve minimizes squared native P-prior deviations with MATPOWER MIPS; it does not fit internal interfaces. Native voltage/reactive controls vary within original source envelopes. Gross loads, source shunts, branches, boundary PQ and native capability limits remain fixed. The Marcy support envelope is a declared research assumption, not a verified physical device.\n\n');
fprintf(fid,'Independent fixed-input PF passes: %s. Maximum nodal mismatch %.9g MW / %.9g MVAr. Maximum reference P adjustment %.9g MW. No relaxation or fictitious active injection is used in the accepted reference.\n\n', ...
    string(r.replay_audit.passed),r.replay_audit.summary.max_nodal_p_mismatch_mw, ...
    r.replay_audit.summary.max_nodal_q_mismatch_mvar,max(abs(r.reference_adjustment.replay_adjustment_mw)));
fprintf(fid,'Every original snapshot, fixed-control repair, bounded solve and replay attempt has a row in operating_attempts.csv. Each has full bus/generator/branch ledgers in physical units. Original source violations are preserved in original_source_*.csv; they are not silently repaired in source files.\n\n');
fprintf(fid,'Reproduce from repository root with `run_ny_only_foundation`; independently replay the saved input with `replay_ny_only_foundation`. Fast `run_operating=false` checks never establish electrical qualification.\n\n');
fprintf(fid,'Limitations: source-era inferred/assumed controls and boundary Q, ambiguous identical parallel circuit IDs, no contemporary observations, no NPCC internal replacement, no thermal eligibility. The voltage envelope remains the explicit source 0.9-1.1 pu envelope; this reference is not evidence for a tighter study envelope or NYISO certification.\n');
fprintf(fid,'\nSource preservation refers to the canonical MATPOWER conversion. The RAW remote regulator at generator 138/1 targets bus1296, while the canonical conversion controls local bus138; this conversion limitation is retained and disclosed in the control inventory. It is not a claim of reproducing every RAW control.\n');
end
