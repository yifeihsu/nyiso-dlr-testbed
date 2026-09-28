function out=run_compact_npcc_ny_testbed(options)
%RUN_COMPACT_NPCC_NY_TESTBED Rebuild the small NY-only NPCC benchmark.
% Bounded full-NPCC dispatch prepares one matched boundary snapshot. The
% operating network contains NY only, with fixed delivered boundary P/Q.
% All inherited loads, capability envelopes and branch hardware stay fixed.
if nargin<1,options=struct();end
options=defaults(options,'write_outputs',true,'run_tests',true,'run_crosscheck',true);
root=fileparts(mfilename('fullpath'));addpath(fullfile(root,'System Matpower Format','NY_Lite'));
if ~isfield(options,'output_dir'),options.output_dir=fullfile(root,'output','compact_npcc_ny');end
folder=options.output_dir;protect_references(root,folder);define_constants;
build=build_compact_npcc_corridors;contract=compact_npcc_model_contract;
tests=table();
if options.run_tests
    t=test_compact_npcc_model_contract;tests=add(tests,"compact_scope_contract",height(t),all(t.passed));
    t=test_compact_npcc_corridors;tests=add(tests,"focused_corridor_preservation",t.assertion_groups,t.pass);
    t=test_extract_compact_ny_boundary;tests=add(tests,"boundary_accounting",height(t),all(t.passed));
    t=test_ny_ac_reference_audit;tests=add(tests,"physical_AC_audit",height(t),all(t.passed));
end
tests=add(tests,"construction_gates",height(build.validation.gates),build.validation.pass);
assert(all(tests.passed),'compact_npcc:Tests','Compact implementation tests failed.');
adapter=build;adapter.allocation=struct('Pg_prior_mw',build.candidate.gen(:,PG), ...
    'Pg_sigma_mw',max(50,.25*(build.candidate.gen(:,PMAX)-build.candidate.gen(:,PMIN))));
solvers="MIPS";starts=0;
if options.run_crosscheck
    solvers(end+1)="MIPS";starts(end+1)=2;
    if have_feature('ipopt'),solvers=[solvers "IPOPT" "IPOPT"];starts=[starts 0 2];end
end
operating_attempts=table();diagnostics=cell(numel(solvers),1);
for k=1:numel(solvers)
    o=reconstruct_ny_regional_operating_point(adapter,struct('solver',char(solvers(k)),'opf_start',starts(k)));
    o.qualification_scope='reconstructed_NPCC_benchmark_dispatch_with_focused_corridors';
    o.result=plain_case(o.result);o.fixed_input_pf=plain_case(o.fixed_input_pf);
    diagnostics{k}=o;a=o.bounded_audit.summary;
    row=table(solvers(k),starts(k),k==1,o.result.success,o.bounded_audit.passed,o.replay_audit.passed, ...
        o.network_and_injections_frozen,o.electrical_baseline_qualified, ...
        a.max_nodal_p_mismatch_mw,a.max_nodal_q_mismatch_mvar, ...
        o.max_replay_dispatch_adjustment_mw,o.max_replay_voltage_adjustment_pu, ...
        sum(abs(o.fixed_input_pf.gen(:,PG)-adapter.allocation.Pg_prior_mw)),o.solver_error,o.replay_error, ...
        'VariableNames',{'solver','opf_start','primary_attempt','solver_success','bounded_audit_pass', ...
        'independent_PF_pass','hardware_frozen','accepted_benchmark','max_nodal_p_mismatch_mw', ...
        'max_nodal_q_mismatch_mvar','replay_dispatch_adjustment_mw','replay_voltage_adjustment_pu', ...
        'full_NPCC_dispatch_L1_movement_mw','solver_error','replay_error'});
    operating_attempts=[operating_attempts;row]; %#ok<AGROW>
end
% Primary selection is fixed in advance. Optional solver/start crosschecks
% do not replace a failed primary result or change its declared constraints.
operating=diagnostics{1};
if ~operating.electrical_baseline_qualified
    folder=fullfile(folder,'failed_primary');
    if options.write_outputs
        if ~isfolder(folder),mkdir(folder);end
        ny_lite_writetable_lf(operating_attempts,fullfile(folder,'compact_operating_attempts.csv'));
        save(fullfile(folder,'compact_failed_diagnostics.mat'),'build','diagnostics','tests','contract');
    end
    error('compact_npcc:PrimaryOperatingPoint','Primary bounded benchmark failed; diagnostic outcomes were retained.');
end
full_reference=operating.fixed_input_pf;
assembly=extract_compact_ny_boundary(full_reference,build);
mpc=assembly.candidate;contract=compact_npcc_model_contract(mpc);
result=plain_case(runpf(mpc,mpoption('verbose',0,'out.all',0,'pf.enforce_q_lims',1,'pf.tol',1e-10)));
audit=audit_ny_ac_reference(result,struct('generator_keys',assembly.generator_keys,'branch_keys',assembly.branch_keys));
[~,fi]=ismember(mpc.bus(:,BUS_I),full_reference.bus(:,BUS_I));
angle_shift=full_reference.bus(full_reference.bus(:,BUS_I)==assembly.reference_bus,VA);
fv=full_reference.bus(fi,VM).*exp(1i*(full_reference.bus(fi,VA)-angle_shift)*pi/180);
nyv=result.bus(:,VM).*exp(1i*result.bus(:,VA)*pi/180);
voltage_error=max(abs(nyv-fv));dispatch_error=max(abs(result.gen(:,PG)-mpc.gen(:,PG)));
frozen=isequal(result.bus(:,[BUS_I PD QD GS BS BASE_KV VMIN VMAX]),mpc.bus(:,[BUS_I PD QD GS BS BASE_KV VMIN VMAX]))&& ...
    isequal(result.branch(:,1:13),mpc.branch(:,1:13))&& ...
    isequal(result.gen(:,[GEN_BUS GEN_STATUS PMIN PMAX QMIN QMAX]),mpc.gen(:,[GEN_BUS GEN_STATUS PMIN PMAX QMIN QMAX]));
active=mpc.branch(:,BR_STATUS)>0;
[~,f]=ismember(mpc.branch(active,F_BUS),mpc.bus(:,BUS_I));[~,t]=ismember(mpc.branch(active,T_BUS),mpc.bus(:,BUS_I));
connected=max(conncomp(graph(f,t,[],size(mpc.bus,1))))==1;
gross=sum(assembly.bus_injection_ledger.pd_gross_mw);boundary=sum(assembly.boundary_register.p_injection_mw);
gates=table(["NY_only_51_bus_case_with_hard_200_cap";"all_original_46_NPCC_NY_buses"; ...
    "92_branch_records_87_active_35_generators";"one_connected_network";"ten_fixed_boundary_ties"; ...
    "gross_benchmark_load_preserved";"boundary_counted_once";"NY_hardware_and_capability_frozen"; ...
    "bounded_NY_AC_audit";"matched_full_reference_voltage";"fixed_dispatch_replay"; ...
    "no_external_boundary_response_or_thermal_claim"], ...
    [size(mpc.bus,1)==51&&size(mpc.bus,1)<=200;all(ismember((37:82)',mpc.bus(:,BUS_I))); ...
    size(mpc.branch,1)==92&&sum(active)==87&&size(mpc.gen,1)==35;connected; ...
    height(assembly.boundary_register)==10; ...
    abs(gross-sum(build.full_candidate.bus(build.ny_bus_mask,PD)))<1e-9; ...
    abs(sum(mpc.bus(:,PD))-(gross-boundary))<1e-8;frozen;audit.passed; ...
    voltage_error<1e-7;dispatch_error<1e-3; ...
    ~assembly.boundary_response_equivalence_established&&~contract.dlr_ready], ...
    'VariableNames',{'test','passed'});
qualified=all(gates.passed)&&all(tests.passed)&&options.run_tests;
assets=compact_npcc_asset_register(build,assembly,result,audit);
if options.run_tests
    t=test_compact_npcc_asset_register;tests=add(tests,"electrical_asset_current_register",t.assertion_groups,t.pass);
    qualified=qualified&&t.pass;
end
summary=table(size(mpc.bus,1),200,46,size(mpc.branch,1),sum(active),size(mpc.gen,1), ...
    height(assembly.boundary_register),gross,boundary,sum(assembly.boundary_register.q_injection_mvar), ...
    sum(result.gen(result.gen(:,GEN_STATUS)>0,PG)),audit.summary.branch_loss_mw,audit.summary.shunt_loss_mw, ...
    voltage_error,dispatch_error,qualified,false,false, ...
    'VariableNames',{'NY_buses','bus_limit','original_NPCC_NY_buses','branch_records','active_branches', ...
    'aggregate_generator_records','boundary_ties','gross_NY_load_mw','net_boundary_P_mw','net_boundary_Q_mvar', ...
    'NY_generation_mw','branch_loss_mw','shunt_loss_mw','matched_voltage_error_pu', ...
    'replay_dispatch_adjustment_mw','electrical_baseline_qualified','contemporary_validated','dlr_ready'});
source_manifest=build.source_manifest;expected_qualified=qualified;
if ~options.run_tests,folder=fullfile(folder,'implementation_only');
elseif ~qualified,folder=fullfile(folder,'failed_NY_validation');end
out=struct('build',build,'contract',contract,'mpc',mpc,'full_reference',full_reference, ...
    'assembly',assembly,'result',result,'audit',audit,'assets',assets,'tests',tests,'gates',gates, ...
    'operating_attempts',operating_attempts,'summary',summary,'electrical_baseline_qualified',qualified, ...
    'contemporary_validated',false,'dlr_ready',false,'output_dir',folder);
if options.write_outputs
    if ~isfolder(folder),mkdir(folder);end
    save(fullfile(folder,'compact_npcc_ny_reference.mat'),'mpc','full_reference','build','assembly','source_manifest','expected_qualified');
    save(fullfile(folder,'compact_operating_evidence.mat'),'result','audit','diagnostics','tests','gates','summary','contract');
    path=fullfile(folder,'compact_npcc_ny_reference.mat');
    manifest=table("compact_npcc_ny_reference.mat",ny_reference_file_sha256(path),'VariableNames',{'artifact','sha256'});
    ny_lite_writetable_lf(manifest,fullfile(folder,'compact_input_manifest.csv'));
    write_tables(folder,struct('compact_summary',summary,'compact_implementation_tests',tests, ...
        'compact_acceptance_gates',gates,'compact_operating_attempts',operating_attempts, ...
        'compact_electrical_asset_register',assets,'compact_source_manifest',source_manifest));
    for field=["bus_map","physical_branch_register","parent_branch_disposition", ...
            "source_device_exclusion_register","source_connection_omission_register", ...
            "local_identity_tests","functional_replacement_comparison"]
        ny_lite_writetable_lf(build.(field),fullfile(folder,"compact_"+field+".csv"));
    end
    for field=["boundary_register","bus_injection_ledger","generator_register","branch_map"]
        ny_lite_writetable_lf(assembly.(field),fullfile(folder,"compact_"+field+".csv"));
    end
    for entry={"full_bounded",operating.bounded_audit;"full_replay",operating.replay_audit;"NY_replay",audit}'
        for field=["summary","bus","generator","branch"]
            ny_lite_writetable_lf(entry{2}.(field),fullfile(folder,"compact_"+entry{1}+"_"+field+".csv"));
        end
    end
    report(folder,summary,operating_attempts,tests,gates,audit);
end
assert(all(gates.passed),'compact_npcc:NYValidation','NY-only audit failed; output is diagnostic only.');
disp(summary);
end

function m=plain_case(m)
% MATPOWER solver objects are caches, not frozen electrical inputs.
keep=intersect(fieldnames(m),{'version','baseMVA','bus','gen','branch','gencost','bus_name','success','userdata'});
m=rmfield(m,setdiff(fieldnames(m),keep));
end
function t=add(t,name,n,pass)
t=[t;table(string(name),n,logical(pass),'VariableNames',{'test','assertion_groups','passed'})];
end
function write_tables(folder,s)
for name=string(fieldnames(s))',ny_lite_writetable_lf(s.(name),fullfile(folder,name+".csv"));end
end
function o=defaults(o,varargin)
for k=1:2:numel(varargin),if ~isfield(o,varargin{k}),o.(varargin{k})=varargin{k+1};end,end
end
function protect_references(root,folder)
target=lower(string(java.io.File(folder).getCanonicalPath()));
for name=["ny_only_package_a","ny_only_package_b"]
    ref=lower(string(java.io.File(fullfile(root,'output',name)).getCanonicalPath()));
    assert(target~=ref&&~startsWith(target,ref+filesep)&&~startsWith(ref,target+filesep), ...
        'compact_npcc:OutputLocation','Compact outputs cannot overlap preserved Package A/B evidence.');
end
end
function report(folder,s,attempts,tests,gates,a)
f=fopen(fullfile(folder,'COMPACT_NPCC_NY_RESULTS.md'),'w');assert(f>=0);cl=onCleanup(@()fclose(f)); %#ok<NASGU>
fprintf(f,'# Compact NPCC NY benchmark results\n\n');
fprintf(f,'The preferred preliminary electrical testbed contains **%d NY buses**, including all **46 original NPCC NY buses**, under a hard **200-bus ceiling**. It has **%d active branches** (%d records), **%d aggregate generator records**, and **%d fixed boundary injections**.\n\n',s.NY_buses,s.active_branches,s.branch_records,s.aggregate_generator_records,s.boundary_ties);
fprintf(f,'Electrical baseline qualified under declared benchmark assumptions: **%s**. Contemporary validation: **not claimed**. DLR ready: **false**.\n\n',string(s.electrical_baseline_qualified));
fprintf(f,'| Matched benchmark quantity | Value |\n| --- | ---: |\n');
fprintf(f,'| Gross NY load | %.6f MW |\n| Net boundary P (positive into NY) | %.6f MW |\n| Net boundary Q | %.6f MVAr |\n| NY aggregate generation | %.6f MW |\n| Internal branch losses | %.6f MW |\n| Shunt losses | %.6f MW |\n',s.gross_NY_load_mw,s.net_boundary_P_mw,s.net_boundary_Q_mvar,s.NY_generation_mw,s.branch_loss_mw,s.shunt_loss_mw);
fprintf(f,'\nThe negative boundary P is a net export in this reconstructed NPCC benchmark. Each boundary uses the negative of the removed tie''s solved NY-terminal flow, preserving its delivered-power sign and NY-side charging contribution. Gross demand and boundary injections are separately registered; effective demand subtracts each boundary injection once. This fixed P/Q representation reproduces one matched state, not external voltage or contingency response.\n\n');
fprintf(f,'All %d implementation assertion groups and %d acceptance gates pass. A fresh NY power flow has maximum nodal residuals %.3g MW and %.3g MVAr, matched complex-voltage error %.3g pu, and active-dispatch adjustment %.3g MW. Voltage, both-terminal static ratings, angle limits and every declared generator P/Q envelope pass the physical audit.\n\n',sum(tests.assertion_groups),height(gates),a.summary.max_nodal_p_mismatch_mw,a.summary.max_nodal_q_mismatch_mvar,s.matched_voltage_error_pu,s.replay_dispatch_adjustment_mw);
fprintf(f,'The primary reconstruction uses MIPS start 0 with a generator-prior objective and unchanged hardware, loads, shunts, ratings and capability bounds. %d of %d solver/start attempts pass bounded audit and independent full-network replay. Full-NPCC generation moves %.3f MW in total absolute terms from inherited priors: this is a reconstructed benchmark dispatch, not an observed historical operating snapshot. Every attempted result is retained in the operating evidence.\n\n',sum(attempts.accepted_benchmark),height(attempts),attempts.full_NPCC_dispatch_L1_movement_mw(1));
fprintf(f,'The 35 NY generator records comprise 21 original NPCC identities with inherited S7/S4 aggregate envelopes and 14 S4 P-only equivalents. Broad Q limits (including +/-999 and +/-9999 MVAr) are declared benchmark assumptions, not verified physical plant capability. No new generator or relaxed limit is introduced.\n\n');
fprintf(f,'Eleven source AC circuit records refine Pleasant Valley/East Fishkill/Wood Street/Millwood and Ramapo/Ladentown/Buchanan. Five overlapping parent records (88,89,94,235,236) are inactive. The two S7 parallel aggregates 235/236 are exact electrical replacements; the original NPCC corridor retirements are declared functional substitutions with response changes, not exact response-equivalent reductions. Source-device exclusions and omitted incident source connections remain explicit.\n\n');
fprintf(f,'`compact_electrical_asset_register.csv` records terminal RMS model currents and electrical provenance. Overhead/cable/conductor realization remains unverified and all thermal eligibility is false. Inherited equivalent currents do not represent individual physical conductors. The 878-bus Package B case remains an optional historical reference.\n\n');
fprintf(f,'Rebuild: `run_compact_npcc_ny_testbed`. Independently verify the frozen input without optimization: `replay_compact_npcc_ny_testbed`. Load the frozen NY case: `npcc_ny_compact_dlr_testbed`.\n');
end
