function validate_ac_dlr_system()
%VALIDATE_AC_DLR_SYSTEM Bounded whole-network current-constrained AC snapshots.
% Weather scenarios are declared before solving and are not historical data.
% Infeasible cases stay in the output rather than relaxing limits or skipping.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
addpath(fullfile(root,'scripts','nygrid_2025_ac_system','ac_validation'));
out=fullfile(root,'output','nygrid_2025_ac_system','thermal');if ~isfolder(out),mkdir(out);end
weather=table(["catalog_reference";"breezy"],[25;25],[.6096;2.0],[90;90],[1000;1000],[101325;101325], ...
    'VariableNames',{'scenario','ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'});
writetable(weather,fullfile(out,'declared_weather_scenarios.csv'));
% Preserve the original typical/pre-post hours and also cover the same
% annual minimum/maximum load snapshots used by the electrical audit.
hours=[2630 4000 4194 8508];rows=struct([]);overlay_sha='';design_sha='';policy_sha='';
for h=hours
    for wi=1:height(weather)
        w=weather(wi,2:end);name=weather.scenario(wi);
        reference=npcc_nygrid_2025_ac(h);
        if isempty(overlay_sha),overlay_sha=reference.userdata.ac_system.branch_parameter_overlay_sha256;end
        if isempty(design_sha),design_sha=reference.userdata.ac_system.sectioned_design_plan_sha256;end
        if isempty(policy_sha),policy_sha=reference.userdata.ac_system.generator_capability_policy_sha256;end
        assert(strcmp(overlay_sha,reference.userdata.ac_system.branch_parameter_overlay_sha256), ...
            'acDLR:ChangedOverlay','Do not mix parameter revisions inside one validation run.');
        assert(strcmp(design_sha,reference.userdata.ac_system.sectioned_design_plan_sha256), ...
            'acDLR:ChangedDesign','Do not mix section/reactor design revisions inside one run.');
        assert(strcmp(policy_sha,reference.userdata.ac_system.generator_capability_policy_sha256), ...
            'acDLR:ChangedPolicy','Do not mix reactive-capability policies inside one run.');
        [candidate,limits,segments,conductors]=ac_dlr_prepare_case(reference,w,'reference');
        % Compile current limits before any optimization result is available.
        prefix=sprintf('h%d_%s',h,name);
        writetable(limits.segment,fullfile(out,[prefix '_segment_limits.csv']));
        opt=mpoption('model','AC','verbose',0,'out.all',0,'opf.ac.solver','IPOPT','opf.violation',1e-7);
        opt.ipopt.opts.bound_relax_factor=0;opt.ipopt.opts.tol=1e-9;opt.ipopt.opts.max_iter=1000;
        tic;[result,success]=runopf(candidate,opt);elapsed=toc;
        row=struct('hour',h,'scenario',char(name),'solver_success',logical(success),'electrical_pass',false, ...
            'thermal_pass',false,'seconds',elapsed,'buses',size(candidate.bus,1), ...
            'active_OH_branches',height(limits.branch),'active_OH_segments',height(segments), ...
            'max_P_KCL_mw',NaN,'max_Q_KCL_mvar',NaN,'max_ampacity_fraction',NaN, ...
            'max_loss_identity_error_mw',NaN,'loss_mw',NaN,'objective',NaN, ...
            'external_P_change_mw',NaN,'six_transfer_P_change_mw',NaN,'fixed_reference_R',true);
        row.terminal_current_pass=false;row.max_terminal_current_fraction=NaN;
        row.section_end_thermal_pass=false;row.max_section_end_ampacity_fraction=NaN;
        electrical=[];thermal=[];terminal=[];section_ends=[];
        if success
            [electrical,detail]=audit_ac_solution(candidate,result);
            thermal=ac_dlr_current_audit(result,segments,conductors,segments.reference_temperature_c,limits);
            terminal=ac_terminal_current_audit(result,candidate.userdata.ac_system.terminal_current_limits);
            section_ends=ac_terminal_current_audit(result,candidate.userdata.ac_system.conductor_section_end_current_limits);
            row.electrical_pass=electrical.passed;row.thermal_pass=thermal.passed;
            row.max_P_KCL_mw=electrical.max_nodal_P_residual_mw;row.max_Q_KCL_mvar=electrical.max_nodal_Q_residual_mvar;
            row.max_ampacity_fraction=thermal.maximum_ampacity_fraction;
            row.max_loss_identity_error_mw=thermal.maximum_loss_identity_error_mw;
            row.loss_mw=electrical.AC_real_losses_mw;row.objective=result.f;
            row.external_P_change_mw=electrical.max_external_P_schedule_change_mw;
            row.six_transfer_P_change_mw=electrical.max_fixed_transfer_P_change_mw;
            row.terminal_current_pass=terminal.passed;row.max_terminal_current_fraction=terminal.maximum_fraction;
            row.section_end_thermal_pass=section_ends.passed;row.max_section_end_ampacity_fraction=section_ends.maximum_fraction;
            writetable(thermal.segment,fullfile(out,[prefix '_segment_currents.csv']));
            writetable(thermal.branch,fullfile(out,[prefix '_branch_heating.csv']));
            writetable(terminal.table,fullfile(out,[prefix '_terminal_currents.csv']));
            writetable(section_ends.table,fullfile(out,[prefix '_section_end_currents.csv']));
        else
            detail=[];
        end
        save(fullfile(out,[prefix '.mat']),'reference','candidate','result','limits','segments','w','electrical','thermal','terminal','section_ends','detail','opt');
        rows=[rows row]; %#ok<AGROW>
        writetable(struct2table(rows),fullfile(out,'whole_system_snapshot_results.csv'));
        fprintf('WHOLE_SYSTEM h%d %s solver%d AC%d thermal%d branches%d segments%d ratio%.9g time%.2f\n', ...
            h,name,success,row.electrical_pass,row.thermal_pass,row.active_OH_branches,row.active_OH_segments,row.max_ampacity_fraction,elapsed);
    end
end
summary=struct('completed',true,'all_snapshot_constraints_passed',all([rows.solver_success]&[rows.electrical_pass]&[rows.thermal_pass]&[rows.terminal_current_pass]&[rows.section_end_thermal_pass]), ...
    'snapshots',numel(rows),'hours',hours,'weather_is_observed',false,'whole_active_OH_network_constrained',true, ...
    'synthetic_existing_power_scale',true,'current_gamma_lift',false,'parameter_or_limit_fit_to_results',false, ...
    'resistance_mode','75C_ACSR_and95C_ACSS_declared_reference_not_equilibrium_temperature', ...
    'historical_annual_AC_DLR_replay_completed',false,'results',rows,'MATLAB_version',version, ...
    'branch_parameter_overlay_sha256',overlay_sha,'sectioned_design_plan_sha256',design_sha);
summary.generator_capability_policy_sha256=policy_sha;
fid=fopen(fullfile(out,'whole_system_validation.json'),'w');fprintf(fid,'%s\n',jsonencode(summary,'PrettyPrint',true));fclose(fid);
end
