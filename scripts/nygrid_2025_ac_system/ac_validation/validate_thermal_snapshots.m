function report=validate_thermal_snapshots()
% Independent electrical/current audit of all saved thermal attempts.
% Direct branch laws and 3*n*b*I_sub^2*R_ref*length check the saved solver state.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
addpath(fullfile(root,'scripts','nygrid_2025_ac_system','thermal'));
source=fullfile(root,'output','nygrid_2025_ac_system','thermal');
out=fullfile(root,'output','nygrid_2025_ac_system','ac_validation','independent_thermal_snapshots');
if ~isfolder(out),mkdir(out);end
primary=jsondecode(fileread(fullfile(source,'whole_system_validation.json')));
assert(primary.completed&&primary.snapshots==8&&numel(primary.results)==8);
checks=struct([]);qualified_count=0;failed_count=0;
for k=1:numel(primary.results)
    row=primary.results(k);label=sprintf('h%d_%s',row.hour,row.scenario);
    data=load(fullfile(source,[label '.mat']));m=data.candidate;r=data.result;reference=data.reference;
    expected=npcc_nygrid_2025_ac(row.hour);
    assert(isequal(reference.bus,expected.bus)&&isequal(reference.gen,expected.gen) ...
        &&isequal(reference.branch,expected.branch)&&isequal(reference.dcline,expected.dcline)&&isequal(reference.gencost,expected.gencost));
    assert(isequal(m.bus,reference.bus)&&isequal(m.gen,reference.gen)&&isequal(m.dcline,reference.dcline) ...
        &&isequal(m.gencost,reference.gencost)&&isequal(m.branch(:,[1 2 4:13]),reference.branch(:,[1 2 4:13])));
    u=m.userdata.ac_system;ue=expected.userdata.ac_system;
    assert(strcmp(u.branch_parameter_overlay_sha256,ue.branch_parameter_overlay_sha256) ...
        &&strcmp(u.sectioned_design_plan_sha256,ue.sectioned_design_plan_sha256) ...
        &&strcmp(u.generator_capability_policy_sha256,ue.generator_capability_policy_sha256));
    assert(logical(r.success)==row.solver_success);
    [a,detail]=audit_ac_solution(m,r);
    c=struct('label',label,'hour_index',row.hour,'scenario',row.scenario,'solver_success',logical(r.success), ...
        'qualified_constrained_operating_point',false,'independent_electrical_pass',a.passed, ...
        'all_input_and_constraint_preservation_checks_passed',true,'failed_trial_not_promoted',false, ...
        'ACPF_replay_passed',false,'maximum_P_KCL_MW',a.max_nodal_P_residual_mw, ...
        'maximum_Q_KCL_MVAr',a.max_nodal_Q_residual_mvar, ...
        'maximum_hardware_terminal_fraction',a.maximum_hardware_terminal_current_fraction, ...
        'maximum_cable_static_current_fraction',a.maximum_cable_section_static_current_fraction, ...
        'maximum_OH_series_current_fraction',a.maximum_OH_series_current_fraction, ...
        'maximum_OH_section_end_fraction',a.maximum_conductor_section_end_current_fraction, ...
        'maximum_current_crosscheck_error_amp',NaN,'maximum_heat_identity_error_MW',NaN, ...
        'maximum_reference_R_match_error_pu',NaN,'ACPF_iterations',NaN, ...
        'ACPF_max_P_KCL_MW',NaN,'ACPF_max_Q_KCL_MVAr',NaN, ...
        'ACPF_maximum_OH_series_current_fraction',NaN, ...
        'branch_parameter_overlay_sha256',u.branch_parameter_overlay_sha256, ...
        'sectioned_design_plan_sha256',u.sectioned_design_plan_sha256, ...
        'generator_capability_policy_sha256',u.generator_capability_policy_sha256, ...
        'reference_temperature_is_not_equilibrium',true,'asbuilt_or_historical_qualification_claimed',false);
    if ~r.success
        assert(~row.electrical_pass&&~row.thermal_pass&&~row.terminal_current_pass&&~row.section_end_thermal_pass&&~a.passed);
        c.failed_trial_not_promoted=true;failed_count=failed_count+1;
    else
        assert(row.electrical_pass&&row.thermal_pass&&row.terminal_current_pass&&row.section_end_thermal_pass&&a.passed);
        segments=u.thermal_segments;rr=segments.branch_row;
        assert(all(m.branch(rr,11)>0)&&all(string(u.branch_keys(rr))==string(segments.branch_key)));
        circuits=double(segments.circuits);bundle=double(segments.bundle_count);
        assert(all(circuits>=1&circuits==fix(circuits)&bundle>=1&bundle==fix(bundle)));
        amps=detail.series_current_amp(rr);
        sub=amps./(circuits.*bundle);
        heat=3*circuits.*bundle.*sub.^2 ...
            .*segments.r_ref_ohm_per_m_per_subconductor.*segments.segment_length_m/1e6;
        unique_rows=unique(rr);Rsum=zeros(numel(unique_rows),1);Hsum=Rsum;
        for j=1:numel(unique_rows)
            take=rr==unique_rows(j);Rsum(j)=sum(segments.reference_r_pu(take));Hsum(j)=sum(heat(take));
            expected_limit=min(data.limits.segment.ampacity_subconductor_a(take).*circuits(take).*bundle(take));
            q=find(m.userdata.ac_dlr.branch_rows==unique_rows(j));assert(isscalar(q));
            assert(abs(expected_limit-m.userdata.ac_dlr.series_phase_limit_a(q))<1e-8);
        end
        c.maximum_reference_R_match_error_pu=max(abs(Rsum-m.branch(unique_rows,3)));
        c.maximum_heat_identity_error_MW=max(abs(Hsum-real(detail.from_power_mva(unique_rows)+detail.to_power_mva(unique_rows))));
        c.maximum_current_crosscheck_error_amp=max(abs(amps-data.thermal.segment.series_phase_current_a));
        assert(c.maximum_reference_R_match_error_pu<1e-11&&c.maximum_heat_identity_error_MW<1e-7 ...
            &&c.maximum_current_crosscheck_error_amp<1e-5&&max(abs(heat-data.thermal.segment.joule_loss_mw))<1e-7);
        assert(all(sub<=data.limits.segment.ampacity_subconductor_a*(1+1e-6)));
        independent_segments=segments;independent_segments.direct_series_phase_current_amp=amps;
        independent_segments.direct_subconductor_current_amp=sub;independent_segments.direct_joule_loss_MW=heat;
        writetable(independent_segments,fullfile(out,[label '_independent_segment_audit.csv']));
        [pf,pa,pf_detail,pf_input,pf_options]=replay_acpf_solution(m,r);
        assert(pa.passed&&pa.OH_series_current_limits_audited&&pa.conductor_section_end_current_limits_audited ...
            &&pa.hardware_terminal_current_limits_audited&&pa.cable_section_static_current_limits_audited);
        c.ACPF_replay_passed=pa.passed;c.ACPF_iterations=pa.PF_iterations;
        c.ACPF_max_P_KCL_MW=pa.max_nodal_P_residual_mw;c.ACPF_max_Q_KCL_MVAr=pa.max_nodal_Q_residual_mvar;
        c.ACPF_maximum_OH_series_current_fraction=pa.maximum_OH_series_current_fraction;
        c.qualified_constrained_operating_point=true;qualified_count=qualified_count+1;
        save(fullfile(out,[label '_ACPF.mat']),'pf','pa','pf_detail','pf_input','pf_options');
        fid=fopen(fullfile(out,[label '_ACPF.json']),'w');fprintf(fid,'%s\n',jsonencode(pa,'PrettyPrint',true));fclose(fid);
    end
    save(fullfile(out,[label '_audit.mat']),'a','detail','c');
    fid=fopen(fullfile(out,[label '_audit.json']),'w');fprintf(fid,'%s\n',jsonencode(c,'PrettyPrint',true));fclose(fid);
    checks=[checks c]; %#ok<AGROW>
    fprintf('INDEPENDENT_THERMAL %s source_success%d qualified%d PF%d current_error%.3g heat_error%.3g\n', ...
        label,r.success,c.qualified_constrained_operating_point,c.ACPF_replay_passed,c.maximum_current_crosscheck_error_amp,c.maximum_heat_identity_error_MW);
end
assert(qualified_count==4&&failed_count==4);
writetable(struct2table(checks),fullfile(out,'independent_snapshot_checks.csv'));
report=struct('independent_audit_complete',true,'root_classification_confirmed',true,'all_eight_inputs_preserved',true, ...
    'snapshot_attempts',numel(checks),'qualified_constrained_operating_points',qualified_count, ...
    'failed_OPF_trials_not_promoted',failed_count,'all_snapshots_physically_qualified',false, ...
    'all_four_successful_points_ACPF_replay_passed',true,'annual_AC_or_thermal_qualification_claimed',false, ...
    'steady_ampacity_with_declared_reference_resistance_only',true,'conductor_temperature_equilibrium_validated',false, ...
    'physical_asbuilt_ratings_or_historical_weather_claimed',false,'checks',checks);
fid=fopen(fullfile(out,'independent_thermal_snapshot_validation.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
end
