function report=test_nygrid_rx_thermal_screen(hours)
%TEST_NYGRID_RX_THERMAL_SCREEN Selected-hour identities and admission guards.
% Start with setup_nygrid_2025_handoff(root,explicit_MATPOWER_root), then add
% this folder. Runs only the requested PF points; never an annual run or OPF.
if nargin<1,hours=[4000 8508];end
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
out=fullfile(root,'output','nygrid_2025_conductor_inference','matlab_validation');if ~isfolder(out),mkdir(out);end
source_before=protected_sources(root);names=strings(0,1);passed=false(0,1);errors=zeros(0,1);points=struct([]);
weather=table(25,.6096,90,1000,101325,'VariableNames',{'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'});
for hour=hours(:)'
    [compact,audit,full,allocation]=run_nygrid_2025_loss_consistent_acpf(hour);
    cached=struct('full',full,'audit',audit,'allocation',allocation);before=cached;
    prior=screen_nygrid_2025_loss_pf_thermal(cached,weather);
    screen=screen_nygrid_2025_rx_thermal(cached,weather);
    ledger=screen.candidate_and_exclusion_ledger;fwd=screen.forward_electrical_reconstruction;valid=fwd.research_screen_eligible;
    record("qualified_148bus_PF_h"+string(hour),size(compact.bus,1)==148&&audit.PF_converged ...
        &&audit.AC_equation_gate&&audit.loss_allocation_gate&&audit.reduction_and_equation_gate,0);
    record("PF_and_electrical_inputs_bit_identical_after_v2_screen_h"+string(hour),isequaln(before,cached) ...
        &&~screen.electrical_solution_changed&&~screen.charging_parameters_retuned&&~screen.OPF_run,0);
    old=prior.branch_screen.branch_row;[ok,k]=ismember(old,screen.branch_screen.branch_row);
    delta=max(abs(prior.branch_screen.series_phase_current_A-screen.branch_screen.series_phase_current_A(k)));
    record("v1_admitted_branches_retained_with_identical_currents_h"+string(hour),all(ok)&&delta<1e-10,delta);
    generic=ledger.research_screen_eligible&ismember(string(ledger.source_role),["retained_parent","passive_attachment_equivalent"]);
    record("generic_synthetic_OH_without_installed_identity_admitted_h"+string(hour),any(generic) ...
        &&screen.candidate_parent_count>prior.candidate_parent_count&&~any(ledger.installed_asset_DLR_verified),0);
    record("every_admitted_section_matches_R_and_X_h"+string(hour),all(fwd.R_absolute_error_pu(valid)<=1e-11) ...
        &&all(fwd.X_absolute_error_pu(valid)<=1e-10),max([fwd.R_absolute_error_pu(valid);fwd.X_absolute_error_pu(valid)]));
    record("Joule_terminal_current_and_heat_identities_h"+string(hour),screen.numerical_identities_passed ...
        &&screen.maximum_Joule_loss_identity_error_MW<1e-7&&screen.maximum_terminal_current_crosscheck_error_A<1e-6 ...
        &&screen.maximum_heat_residual_at_ampacity_W_per_m<1e-8,screen.maximum_Joule_loss_identity_error_MW);
    record("operating_and_installed_asset_flags_remain_unqualified_h"+string(hour),~screen.whole_system_operating_qualification ...
        &&~screen.installed_asset_DLR_qualification&&screen.inherited_VQ_operating_qualification==audit.VQ_and_generator_assumption_gate,0);
    row=struct('hour_index',hour,'v1_parent_count',prior.candidate_parent_count,'v2_parent_count',screen.candidate_parent_count, ...
        'runtime_branch_count',screen.candidate_runtime_branch_count,'segment_count',screen.candidate_segment_count, ...
        'imported_RX_parent_count',screen.imported_RX_candidate_parent_count,'prior_engineered_RX_parent_count',screen.prior_engineered_RX_candidate_parent_count, ...
        'geometric_B_mismatch_parent_count',screen.geometric_B_mismatch_candidate_parent_count, ...
        'max_forward_R_error_pu',max(fwd.R_absolute_error_pu(valid)),'max_forward_X_error_pu',max(fwd.X_absolute_error_pu(valid)), ...
        'max_Joule_identity_error_MW',screen.maximum_Joule_loss_identity_error_MW, ...
        'max_terminal_current_error_A',screen.maximum_terminal_current_crosscheck_error_A, ...
        'max_series_utilization',screen.maximum_series_ampacity_utilization,'max_section_end_utilization',screen.maximum_section_end_ampacity_utilization, ...
        'VQ_operating_gate',audit.VQ_and_generator_assumption_gate);
    points=[points row]; %#ok<AGROW>
    label=sprintf('hour_%04d',hour);folder=fullfile(out,label);if ~isfolder(folder),mkdir(folder);end
    writetable(ledger,fullfile(folder,'candidate_and_exclusion_ledger.csv'));
    writetable(screen.candidate_segments,fullfile(folder,'admitted_segments.csv'));
    writetable(fwd,fullfile(folder,'forward_RXB_audit.csv'));
    writetable(screen.branch_screen,fullfile(folder,'branch_current_screen.csv'));
    writetable(screen.segment_screen,fullfile(folder,'segment_thermal_screen.csv'));
    save(fullfile(folder,'selected_point_screen.mat'),'compact','audit','full','allocation','screen','-v7.3');
end
m=allocation.final_input;baseline=m;sg=as_table(m.userdata.ac_system.thermal_segments);
candidate=screen.candidate_segments(1,:);rr=candidate.branch_row;parent=m.userdata.ac_system.branch_parent_row(rr);
hit=find(double(sg.branch_row)==rr,1);
bad=m;bad.branch(rr,3)=bad.branch(rr,3)*1.01;
check_parent('changed_electrical_R_rejected',bad,parent,'forward_catalog_R_differs');
bad=m;bad.branch(rr,4)=bad.branch(rr,4)*1.01;
check_parent('changed_electrical_X_rejected_even_when_R_matches',bad,parent,'forward_geometry_X_differs');
bad=m;modified=sg;modified.gmd_m(hit)=modified.gmd_m(hit)*1.01;bad.userdata.ac_system.thermal_segments=modified;
check_parent('changed_GMD_rejected',bad,parent,'segment_catalog_temperature_or_geometry_validation_failed');
bad=m;modified=sg;modified.base_kv(hit)=modified.base_kv(hit)+1;bad.userdata.ac_system.thermal_segments=modified;
check_parent('mismatched_segment_voltage_base_rejected',bad,parent,'segment_catalog_temperature_or_geometry_validation_failed');
bad=m;modified=sg;modified.circuits(hit)=1.5;bad.userdata.ac_system.thermal_segments=modified;
check_parent('fractional_circuit_multiplicity_rejected',bad,parent,'segment_catalog_temperature_or_geometry_validation_failed');
bad=m;modified=sg;modified.reference_temperature_c(hit)=24;bad.userdata.ac_system.thermal_segments=modified;
check_parent('unsupported_resistance_temperature_rejected',bad,parent,'segment_catalog_temperature_or_geometry_validation_failed');
bad=m;modified=sg;modified.catalog_id=string(modified.catalog_id);modified.catalog_id(hit)="NOT_A_CATALOG_ENTRY";bad.userdata.ac_system.thermal_segments=modified;
check_parent('unknown_conductor_catalog_entry_rejected',bad,parent,'segment_catalog_temperature_or_geometry_validation_failed');
bad=m;bad.branch(rr,9)=1.01;check_parent('transformer_tap_object_rejected',bad,parent,'nonunity_transformer_tap');
bad=m;bad.branch(rr,10)=1;check_parent('phase_shift_object_rejected',bad,parent,'phase_shifter_or_PAR');
bad=m;[~,bus]=ismember(bad.branch(rr,2),bad.bus(:,1));bad.bus(bus,10)=bad.bus(bus,10)+1;
check_parent('voltage_changing_object_rejected',bad,parent,'voltage_changing_object');
bad=m;bad.branch(rr,11)=0;check_parent('inactive_object_rejected',bad,parent,'inactive_or_inconsistent_runtime_status');
multi=ledger.original_parent_row(find(ledger.research_screen_eligible&ledger.runtime_branch_count>1,1));
section=find(m.userdata.ac_system.branch_parent_row==multi);bad=m;change=.01*min(m.branch(section,3));
bad.branch(section(1),3)=bad.branch(section(1),3)+change;bad.branch(section(2),3)=bad.branch(section(2),3)-change;
check_parent('equal_parent_total_but_inconsistent_section_R_rejected',bad,multi,'forward_catalog_R_differs');
bad=m;bad.branch(rr,5)=bad.branch(rr,5)+.01;[~,bl]=nygrid_rx_thermal_candidates(bad);k=bl.original_parent_row==parent;
record('B_mismatch_disclosed_without_rewriting_or_gating_RX',bl.research_screen_eligible(k) ...
    &&~bl.geometric_B_matches_current_case(k)&&~bl.B_used_as_eligibility_gate(k)&&bad.branch(rr,5)==m.branch(rr,5)+.01,0);
bad=m;bad.userdata.ac_system.thermal_segments=[sg;sg(hit,:)];
reject('duplicate_segment_realization_not_summed',@()nygrid_rx_thermal_candidates(bad),'rxThermal:SegmentKeys');
reject('explicit_weather_required',@()screen_nygrid_2025_rx_thermal(cached,[]),'rxThermal:ExplicitWeather');
badcache=cached;badcache.audit.loss_allocation_gate=false;
reject('unqualified_cached_PF_rejected',@()screen_nygrid_2025_rx_thermal(badcache,weather),'rxThermal:UnqualifiedPF');
keyed=repmat(weather,height(screen.candidate_segments),1);keyed.branch_key=string(screen.candidate_segments.branch_key);keyed.segment_id=string(screen.candidate_segments.segment_id);
keyed.branch_key(1)="wrong_runtime_branch";
reject('wrong_weather_segment_keys_rejected',@()screen_nygrid_2025_rx_thermal(cached,keyed),'rxThermal:WeatherOrder');
k=ledger.original_parent_row==224;
record('parent224_excluded_by_RX_feasibility_not_installed_identity',~ledger.research_screen_eligible(k) ...
    &&ledger.current_RX_below_catalog_geometry_minimum(k)&&contains(string(ledger.reason(k)),'current_X_over_R_below_declared_catalog_geometry_minimum') ...
    &&~ledger.installed_circuit_identity_required(k),ledger.catalog_geometry_minimum_X_over_R(k));
k=ismember(ledger.original_parent_row,[300 309 310 386]);
record('documented_cable_conflicts_excluded_with_specific_evidence',all(~ledger.research_screen_eligible(k)) ...
    &&all(contains(string(ledger.reason(k)),'cable_corridor_evidence_conflict'))&&all(strlength(string(ledger.cable_conflict_source(k)))>0),0);
record('all_adversarial_checks_preserve_original_case',isequaln(baseline,m)&&isequaln(before,cached),0);
source_after=protected_sources(root);record('frozen_electrical_inputs_and_handoff_v1_files_unchanged',isequaln(source_before,source_after),0);
tests=table(names,passed,errors,'VariableNames',{'test','passed','error'});writetable(tests,fullfile(out,'tests.csv'));
report=struct('passed',all(passed),'test_count',numel(passed),'hours',hours,'points',points, ...
    'weather_is_observed',false,'weather',table2struct(weather),'MATLAB_version',version,'MATPOWER_version',mpver, ...
    'protected_sources',source_after,'new_runtime_source_files',current_sources(root), ...
    'electrical_input_files_changed',false,'handoff_v1_changed',false,'annual_replay_run',false,'OPF_run',false, ...
    'installed_asset_DLR_qualification',false,'whole_system_operating_qualification',false, ...
    'scope','selected-point R/X-conditioned synthetic conductor screen and adversarial guards; no electrical model changes');
fid=fopen(fullfile(out,'validation_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
disp(tests);fprintf('RX_THERMAL_VALIDATION pass%d tests%d\n',report.passed,report.test_count);
assert(report.passed,'rxThermal:Tests','One or more R/X thermal checks failed.');
    function record(name,ok,error_value)
        names(end+1,1)=string(name);passed(end+1,1)=logical(ok);errors(end+1,1)=error_value;
        fprintf('RX_TEST %s pass%d error%.12g\n',name,ok,error_value);
    end
    function check_parent(name,badcase,p,reason)
        [~,l]=nygrid_rx_thermal_candidates(badcase);k=l.original_parent_row==p;
        record(name,~l.research_screen_eligible(k)&&contains(string(l.reason(k)),reason),0);
    end
    function reject(name,fn,identifier)
        matched=false;try,fn();catch err,matched=strcmp(err.identifier,identifier);if ~matched,fprintf('UNEXPECTED %s %s\n',err.identifier,err.message);end,end
        record(name,matched,0);
    end
end

function t=as_table(value)
if iscell(value),t=struct2table([value{:}]);elseif isstruct(value),t=struct2table(value);else,t=value;end
end

function records=protected_sources(root)
closure=jsondecode(fileread(fullfile(root,'output','nygrid_2025_dlr_handoff','runtime_data_closure.json')));
paths=string({closure.entries.path})';
code=jsondecode(fileread(fullfile(root,'output','nygrid_2025_dlr_handoff','runtime_audit','runtime_code_closure.json')));
paths=[paths;string({code.entries.target})'; ...
    "output/nygrid_2025_ac_system/engineering/geometry_defaults.csv"; ...
    "output/nygrid_2025_acpf_profile_audit/structure/overhead_cable_classification_conflicts.csv"];
records=hash_records(root,unique(paths));
end

function records=current_sources(root)
files=dir(fullfile(root,'scripts','nygrid_2025_conductor_inference','*.m'));
paths="scripts/nygrid_2025_conductor_inference/"+string({files.name})';records=hash_records(root,paths);
end

function records=hash_records(root,paths)
records=struct('path',{},'sha256',{});
for k=1:numel(paths),records(end+1)=struct('path',char(paths(k)),'sha256',filehash(fullfile(root,paths(k)))) ;end %#ok<AGROW>
end

function digest=filehash(path)
fid=fopen(path,'rb');assert(fid>=0);clean=onCleanup(@()fclose(fid));e=java.security.MessageDigest.getInstance('SHA-256');
while ~feof(fid),b=fread(fid,1048576,'*uint8');if ~isempty(b),e.update(typecast(b,'int8'));end,end
digest=lower(reshape(dec2hex(typecast(e.digest(),'uint8'),2)',1,[]));
end
