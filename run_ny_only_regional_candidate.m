function out=run_ny_only_regional_candidate(options)
%RUN_NY_ONLY_REGIONAL_CANDIDATE Package B complete regional replacement.
% Rebuilds row235 proof, source device mapping, bounded full-demand operating
% point and independent fixed-input PF. Smaller failed variants are retained.
if nargin<1,options=struct();end
options=defaults(options,'write_outputs',true,'run_tests',true,'run_operating',true,'run_smaller_variants',true);
root=fileparts(mfilename('fullpath'));h=fullfile(root,'System Matpower Format','NY_Lite');addpath(h);
[~,PG,QG,~,~,~,~,GEN_STATUS]=idx_gen;
if ~isfield(options,'output_dir'),options.output_dir=fullfile(root,'output','ny_only_package_b');end
foundation_dir=fullfile(root,'output','ny_only_package_a');
assert(~isfield(options,'foundation_dir')||strcmp(options.foundation_dir,foundation_dir), ...
    'ny_region:FoundationLocation','Package B uses the authoritative committed Package A reference.');
folder=options.output_dir;
absolute_output=lower(string(java.io.File(folder).getCanonicalPath()));
absolute_foundation=lower(string(java.io.File(foundation_dir).getCanonicalPath()));
assert(absolute_output~=absolute_foundation&&~startsWith(absolute_output,absolute_foundation+filesep)&& ...
    ~startsWith(absolute_foundation,absolute_output+filesep), ...
    'ny_region:OutputLocation','Package B outputs cannot overlap the frozen Package A directory.');
n=normalize_perform_ny_source;
foundation_path=fullfile(foundation_dir,'ny_foundation_reference.mat');
fm=readtable(fullfile(foundation_dir,'reference_input_manifest.csv'),'TextType','string');
assert(height(fm)==1&&fm.artifact=="ny_foundation_reference.mat"&&fm.sha256==ny_reference_file_sha256(foundation_path), ...
    'ny_region:FoundationManifest','Package A reference differs from its frozen manifest.');
foundation=load(foundation_path);
assert(isequal(foundation.expected_qualified,true)&&isequal(foundation.source_manifest,n.source_manifest), ...
    'ny_region:Foundation','Qualified immutable-source Package A inputs are required.');
build=build_ny_regional_candidate(n,foundation,struct('replacement_zones',string(('D':'K')')));
v=validate_ny_region_replacement(n.source,build.parent,build);
tests=table();
if options.run_tests
    t=test_row235_replacement;tests=add(tests,"exact_row235_replacement",t.assertion_groups,t.pass);
    t=test_map_perform_injections_to_ny_candidate(n,foundation);tests=add(tests,"source_device_allocation",t.test_count,t.pass);
    t=test_ny_region_replacement;tests=add(tests,"regional_adversarial",height(t),all(t.passed));
    t=test_ny_ac_reference_audit;tests=add(tests,"physical_unit_audit",height(t),all(t.passed));
    t=test_ny_regional_operating_contract;tests=add(tests,"bounded_operating_contract",height(t),all(t.passed));
    t=test_compare_ny_region_to_foundation;tests=add(tests,"independent_operating_comparison",t.test_count,t.pass);
end
tests=add(tests,"row235_local_identity",height(build.row235.validation.gates),build.row235.validation.pass);
tests=add(tests,"regional_provenance_and_conservation",height(v.gates),v.passed);
assert(all(tests.passed),'ny_region:Tests','Package B implementation tests failed.');
attempts=table();alternatives={};comparison=struct();operating=struct('electrical_baseline_qualified',false);qualified=false;
if options.run_operating
    fr=replay_ny_only_foundation(foundation_dir);assert(fr.passed);
    if options.run_smaller_variants
        for zones={string(('G':'K')'),["D";string(('G':'K')')]}
            trial_build=build_ny_regional_candidate(n,foundation,struct('replacement_zones',zones{1}));
            trial_v=validate_ny_region_replacement(n.source,trial_build.parent,trial_build);
            trial=reconstruct_ny_regional_operating_point(trial_build);
            name="replacement_"+join(zones{1},'');
            attempts=attempt(attempts,name,trial_build,trial,trial_v.passed);
            alternatives{end+1}=struct('name',name,'build',trial_build,'validation',trial_v,'operating',trial); %#ok<AGROW>
        end
    end
    operating=reconstruct_ny_regional_operating_point(build);
    qualified=operating.electrical_baseline_qualified&&v.passed;
    attempts=attempt(attempts,"replacement_"+join(build.replacement_zones,''),build,operating,v.passed);
    if qualified,comparison=compare_ny_region_to_foundation(build,operating.fixed_input_pf,fr.result);end
end
% Failed or implementation-only runs cannot overwrite an accepted delivery.
if ~options.run_operating,folder=fullfile(folder,'implementation_only');
elseif ~qualified,folder=fullfile(folder,'failed_candidate');end
status=table(["row235_exact_overlap_resolved";"regional_input_and_device_conservation"; ...
    "bounded_historical_candidate";"independent_fixed_input_replay"; ...
    "electrical_baseline_qualified";"upstate_response_identity_established"; ...
    "contemporary_validation";"DLR_ready";"final_S14_DLR_delivery_promoted"], ...
    [build.row235.validation.pass;v.passed;qualified;qualified;qualified;false;false;false;false], ...
    ["Original row235 replaced by its two exact physical parallel records"; ...
    "D-K source region plus NPCC A-C with explicit aggregation assumptions"; ...
    "Actual source MW; fixed gross loads and boundary PQ; finite original device limits"; ...
    "Fresh power flow with frozen dispatch and voltage targets; physical-unit audits"; ...
    "One assumed 2019 NPCC/PERFORM regional candidate only"; ...
    "Common-terminal source device identity is not upstream aggregation response equivalence"; ...
    "Packages C/D scenario and held-out work remains";"Thermal parameters are not qualified"; ...
    "The historical electrical candidate is distinct from final DLR delivery"], ...
    'VariableNames',{'gate','passed','evidence_scope'});
out=struct('build',build,'validation',v,'operating',operating,'comparison',comparison,'tests',tests,'attempts',attempts, ...
    'status',status,'electrical_baseline_qualified',qualified,'output_dir',folder, ...
    'qualification_scope','assumed_2019_NPCC_PERFORM_regional_candidate_only', ...
    'contemporary_validation_coverage','not_evaluated','dlr_ready',false);
if options.write_outputs
    if ~isfolder(folder),mkdir(folder);end
    for k=1:numel(alternatives)
        alt=alternatives{k};d=fullfile(folder,'alternatives',alt.name);if ~isfolder(d),mkdir(d);end
        ny_lite_writetable_lf(alt.validation.gates,fullfile(d,'regional_validation.csv'));
        for kind={'bounded_audit','replay_audit'},write_audit_to(alt.operating.(kind{1}),d,kind{1});end
        ny_lite_writetable_lf(alt.build.source_bus_map,fullfile(d,'source_bus_map.csv'));
        mpc=alt.operating.result;replacement_zones=alt.build.replacement_zones;expected_qualified=alt.operating.electrical_baseline_qualified; %#ok<NASGU>
        save(fullfile(d,'attempt.mat'),'mpc','replacement_zones','expected_qualified');
    end
    write(tests,'implementation_tests');write(status,'qualification_status');write(attempts,'operating_attempts');
    write(v.gates,'regional_validation');
    for field={'source_bus_map','anchor_register','source_branch_map','retired_branch_register', ...
            'retained_parent_branch_map','parent_branch_disposition','retired_legacy_bus_injections','retired_legacy_generators'}
        write(build.(field{1}),field{1});
    end
    for field={'source_load_ledger','generator_map','control_map','boundary_register','shunt_register','model_bus_ledger','zone_accounting'}
        write(build.allocation.(field{1}),field{1});
    end
    for field={'disposition_register','bus_map','source_branch_register','affected_region_register','matched_terminal_tests'}
        write(build.row235.(field{1}),['row235_' field{1}]);
    end
    write(build.row235.validation.gates,'row235_local_validation');
    dependencies=table(["Package_A_reference";"source_allocation_anchor_register"], ...
        ["output/ny_only_package_a/ny_foundation_reference.mat";"System Matpower Format/NY_Lite/perform_retained_control_anchors.csv"], ...
        [ny_reference_file_sha256(foundation_path);ny_reference_file_sha256(fullfile(h,'perform_retained_control_anchors.csv'))], ...
        'VariableNames',{'dependency','repository_path','sha256'});write(dependencies,'dependency_manifest');
    if options.run_operating
        write_audit_to(operating.bounded_audit,folder,'bounded');write_audit_to(operating.replay_audit,folder,'independent_replay');
        q=operating.fixed_input_pf;
        native=build.allocation.generator_map.source_device_role~="assumed_reactive_support"&q.gen(:,GEN_STATUS)>0;
        dispatch=build.allocation.generator_map;
        dispatch.bounded_pg_mw=operating.result.gen(:,PG);dispatch.bounded_qg_mvar=operating.result.gen(:,QG);
        dispatch.replay_pg_mw=q.gen(:,PG);dispatch.replay_qg_mvar=q.gen(:,QG);
        dispatch.pg_movement_mw=q.gen(:,PG)-dispatch.prior_pg_mw;
        dispatch.qg_movement_mvar=q.gen(:,QG)-dispatch.prior_qg_mvar;write(dispatch,'native_and_support_dispatch');
        loss=operating.replay_audit.summary.branch_loss_mw+operating.replay_audit.summary.shunt_loss_mw;
        gross=sum(build.allocation.model_bus_ledger.pd_gross_mw);boundary=sum(build.allocation.boundary_register.p_injection_mw);
        accounting=table(gross,boundary,sum(q.gen(native,PG)),loss,sum(q.gen(native,PG))+boundary-gross-loss, ...
            sum(abs(dispatch.pg_movement_mw(native))),sum(abs(dispatch.qg_movement_mvar(native))), ...
            q.gen(end,PG),q.gen(end,QG),operating.max_replay_dispatch_adjustment_mw, ...
            operating.max_replay_voltage_adjustment_pu, ...
            'VariableNames',{'gross_load_mw','fixed_boundary_p_mw','native_generation_mw','total_loss_mw', ...
            'balance_error_mw','native_P_movement_from_Package_A_mw','native_Q_movement_from_Package_A_mvar', ...
            'assumed_support_p_mw','assumed_support_q_mvar','max_replay_P_adjustment_mw','max_replay_V_adjustment_pu'});
        write(accounting,'power_accounting');out.accounting=accounting;
        if qualified
            for field={'exact_bus_voltage_comparison','source_branch_comparison','summary'}
                write(comparison.(field{1}),['source_response_' field{1}]);
            end
        end
        mpc=operating.result;
        mpc.userdata.package_b.electrical_baseline_qualified=qualified;
        mpc.userdata.package_b.qualification_scope=out.qualification_scope;
        generator_keys=build.generator_keys;branch_keys=build.branch_keys;source_manifest=n.source_manifest; %#ok<NASGU>
        replacement_zones=build.replacement_zones;expected_qualified=qualified; %#ok<NASGU>
        save(fullfile(folder,'ny_regional_candidate.mat'),'mpc','generator_keys','branch_keys','source_manifest', ...
            'replacement_zones','expected_qualified','build');
        manifest=table("ny_regional_candidate.mat",ny_reference_file_sha256(fullfile(folder,'ny_regional_candidate.mat')), ...
            'VariableNames',{'artifact','sha256'});write(manifest,'candidate_input_manifest');
        write_report(out,folder);
    end
end
disp(status);
if options.run_operating
    assert(qualified,'ny_region:OperatingQualification','Regional candidate failed bounded solve or independent replay; inspect recorded attempts.');
end
    function write(t,name),ny_lite_writetable_lf(t,fullfile(folder,[name '.csv']));end
end
function t=add(t,name,n,passed),t=[t;table(string(name),n,logical(passed),'VariableNames',{'suite','checks','passed'})];end
function t=attempt(t,name,b,r,local)
a=r.bounded_audit.summary;
t=[t;table(string(name),size(b.candidate.bus,1),size(b.candidate.branch,1),local,logical(r.result.success), ...
    r.bounded_audit.passed,r.replay_audit.passed,r.electrical_baseline_qualified, ...
    a.max_nodal_p_mismatch_mw,a.max_nodal_q_mismatch_mvar,a.max_voltage_violation_pu, ...
    a.max_generator_p_violation_mw,a.max_generator_q_violation_mvar,a.max_branch_overload_mva, ...
    r.solver,r.opf_start,false,r.solver_error,r.diagnostic_state_origin, ...
    'VariableNames',{'attempt','buses','branches','regional_mapping_passed','solver_converged', ...
    'bounded_audit_passed','independent_replay_passed','electrical_baseline_qualified', ...
    'max_nodal_p_mismatch_mw','max_nodal_q_mismatch_mvar','max_voltage_violation_pu', ...
    'max_generator_p_violation_mw','max_generator_q_violation_mvar','max_branch_overload_mva', ...
    'solver','opf_start','relaxation_used','solver_error','diagnostic_state_origin'})];
end
function write_audit_to(a,folder,prefix)
for field={'summary','bus','generator','branch'}
    ny_lite_writetable_lf(a.(field{1}),fullfile(folder,[prefix '_' field{1} '.csv']));
end
end
function s=defaults(s,varargin)
for k=1:2:numel(varargin),if ~isfield(s,varargin{k}),s.(varargin{k})=varargin{k+1};end,end
end
function write_report(out,folder)
b=out.build;r=out.operating;a=out.accounting;
fid=fopen(fullfile(folder,'NY_ONLY_REGIONAL_RESULTS.md'),'w');assert(fid>=0);cl=onCleanup(@()fclose(fid)); %#ok<NASGU>
fprintf(fid,'# NY-only Package B regional candidate\n\nElectrical baseline qualified: **%s**, for one assumed 2019 NPCC/PERFORM regional candidate. Contemporary coverage and DLR readiness remain false.\n\n',string(out.electrical_baseline_qualified));
fprintf(fid,'The connected source region covers D-K: %d source buses plus %d retained NPCC A-C buses, %d total branches and %d generator records. Of the generator records,594 are native source records and one is the separately bounded Marcy Q-only research support inherited from Package A.\n\n',numel(b.region_source_buses),size(b.candidate.bus,1)-numel(b.region_source_buses),size(b.candidate.branch,1),size(b.candidate.gen,1));
fprintf(fid,'Row235 is an exact duplicate of the two Pleasant Valley-Wood Street physical parallel records and is retired first. The regional package then retires every inherited D-K incident branch, all old NY injections and all old NY generators before transferring source devices once. Other retired paths are functional replacements with assumed correspondence; the historical parent remains an explicit alternative. No nonpassive residual is fitted.\n\n');
fprintf(fid,'Common-terminal source/candidate complex power error: %.9g MVA; current error: %.9g kA. These local device checks do not establish retained A-C aggregation response identity. Aggregated A-C load and controls, including the C-E cut mapping, remain declared research assumptions.\n\n',out.validation.common_voltage_max_complex_power_error_mva,out.validation.common_voltage_max_current_error_ka);
fprintf(fid,'| Quantity | Value |\n|---|---:|\nGross demand | %.6f MW |\nFixed net boundary injection | %.6f MW |\nNative generation | %.6f MW |\nLosses | %.6f MW |\nBalance error | %.9g MW |\nNative P movement from Package A | %.6f MW |\nNative Q movement from Package A | %.6f MVAr |\nMarcy support P | %.9g MW |\nMarcy support Q | %.6f MVAr |\nMaximum replay P adjustment | %.9g MW |\nMaximum replay V adjustment | %.9g pu |\n', ...
    a.gross_load_mw,a.fixed_boundary_p_mw,a.native_generation_mw,a.total_loss_mw,a.balance_error_mw, ...
    a.native_P_movement_from_Package_A_mw,a.native_Q_movement_from_Package_A_mvar,a.assumed_support_p_mw, ...
    a.assumed_support_q_mvar,a.max_replay_P_adjustment_mw,a.max_replay_V_adjustment_pu);
fprintf(fid,'\nDefault reconstruction uses MATPOWER MIPS with its interior initialization (opf.start=0), quadratic native P-prior deviations and fixed hardware, schedules and capability bounds. PV targets, voltage magnitudes and native reactive outputs may move within the declared envelopes. No load shedding, fictitious P, constraint relaxation, boundary schedule movement or interface target fit is used. Independent PF maximum nodal mismatches: %.9g MW / %.9g MVAr.\n\n', ...
    r.replay_audit.summary.max_nodal_p_mismatch_mw,r.replay_audit.summary.max_nodal_q_mismatch_mvar);
fprintf(fid,'Separate source-response tables compare each independently solved operating point at its own voltages. They quantify voltage and both-terminal P/Q/current differences, without an acceptance threshold. A bounded electrical baseline does not establish exact source response; broader response qualification remains Package D work.\n\n');
fprintf(fid,'Smaller G-K and D+G-K variants are reproducibly attempted and retained in operating_attempts.csv and alternatives/. Their failed numerical solves are not proofs of global infeasibility. D-K removes the collapsed E/F ports and the weak aggregated Plattsburgh pocket without altering source limits. Additional exploratory warm-start and IPOPT runs informed this choice; they do not supply the accepted artifact.\n\n');
fprintf(fid,'Reproduce with `run_ny_only_regional_candidate`; replay the hash-verified saved input with `replay_ny_only_regional_candidate`. Load the frozen case with `npcc_ny_lite_s14_ny_only_regional_candidate`. The runner records all default attempted variants. Fast run_operating=false implementation checks never qualify an operating point.\n\n');
fprintf(fid,'The canonical source conversion retains its known RAW control and circuit-identity ambiguities. Physical parameters and voltage bases are copied; overhead/cable classification, contemporary plant status, thermal eligibility and held-out response accuracy are not established. Package A and historical NPCC/S7/S13 artifacts remain preserved.\n');
end
