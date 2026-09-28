function report = validate_s11_hourly_load_profile_integration(output_dir)
%VALIDATE_S11_HOURLY_LOAD_PROFILE_INTEGRATION Replay the retained peak in AC PF.
%   This is a single-hour integration check, not a chronological feasibility
%   study. Only the retained peak has matching saved dispatch and controls.
root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
if nargin < 1 || isempty(output_dir)
    output_dir = fullfile(root,'output','s11_hourly_load_profiles');
end
addpath(fullfile(root,'System Matpower Format'), ...
    fullfile(root,'System Matpower Format','NY_Lite'));
data = load(fullfile(output_dir,'s11_hourly_load_profiles.mat'),'profile');
base = npcc_ny_lite_s11_dlr_pf_base;
k = find(strcmp(data.profile.timestamp_utc,'2025-07-29T22:00:00Z'));
assert(isscalar(k), 'Retained peak timestamp must occur exactly once.');
applied = apply_s11_hourly_load_profile(base,data.profile,k);
assert(max(abs(applied.bus(:,3:4)-base.bus(:,3:4)),[],'all') < 1e-4);
unchanged = applied;
unchanged.bus(:,3:4) = base.bus(:,3:4);
assert(isequaln(unchanged,base), 'Hourly application changed non-load case data.');
opts = mpoption('verbose',0,'out.all',0,'pf.enforce_q_lims',0);
[pf, success] = runpf(applied,opts);
[qpf, q_success] = runpf(applied,mpoption(opts,'pf.enforce_q_lims',1));
assert(success && q_success, 'Retained peak AC PF replay failed.');
report = struct('passed',true,'timestamp_utc',data.profile.timestamp_utc{k}, ...
    'hour_index',k,'standard_ac_pf_success',logical(success), ...
    'q_limit_ac_pf_success',logical(q_success), ...
    'maximum_bus_pd_error_mw',max(abs(applied.bus(:,3)-base.bus(:,3))), ...
    'non_load_case_fields_preserved',true, ...
    'minimum_q_limit_pf_voltage_pu',min(qpf.bus(:,8)), ...
    'maximum_q_limit_pf_voltage_pu',max(qpf.bus(:,8)), ...
    'standard_pf_total_generation_mw',sum(pf.gen(:,2)), ...
    'hours_power_flow_checked',1,'all_hours_power_flow_validated',false);
fid = fopen(fullfile(output_dir,'peak_pf_validation.json'),'w');
assert(fid >= 0);
cleanup = onCleanup(@() fclose(fid));
fprintf(fid,'%s\n',jsonencode(report,PrettyPrint=true));
disp(jsonencode(report,PrettyPrint=true));
end
