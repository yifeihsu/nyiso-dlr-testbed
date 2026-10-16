function [result,audit]=run_nygrid_2025_ac_dlr(hour_index,weather,options)
%RUN_NYGRID_2025_AC_DLR Whole-system synthetic ACOPF with OH current limits.
% Applies every active overhead segment's weather-dependent steady ampacity.
% Cables, transformers, PARs and terminal equipment keep separate MVA limits.
% This snapshot uses declared reference-temperature R, not an inferred
% equilibrium conductor temperature or an observed historical-weather replay.
if nargin<1,hour_index=8508;end
if nargin<2||isempty(weather)
    weather=table(25,.6096,90,1000,101325,'VariableNames', ...
        {'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'});
end
if isstruct(weather),weather=struct2table(weather);end
if nargin<3,options=struct();end
if ~isfield(options,'solver')
    if exist('ipopt','file')==3,options.solver='IPOPT';else,options.solver='MIPS';end
end
root=fileparts(fileparts(mfilename('fullpath')));
addpath(fullfile(root,'scripts','nygrid_2025_ac_system','thermal'));
addpath(fullfile(root,'scripts','nygrid_2025_ac_system','ac_validation'));
reference=npcc_nygrid_2025_ac(hour_index);
[candidate,limits,segments,conductors]=ac_dlr_prepare_case(reference,weather,'reference');
mpopt=mpoption('model','AC','verbose',0,'out.all',0,'opf.ac.solver',options.solver, ...
    'opf.violation',1e-7,'mips.max_it',500,'mips.feastol',1e-8);
mpopt.ipopt.opts.bound_relax_factor=0;
mpopt.ipopt.opts.tol=1e-9;
% Run with all finite engineering limits. A failed solve remains a failure;
% no dispatch boxes, boundary schedules, voltage or current limits are relaxed.
[result,success]=runopf(candidate,mpopt);
audit=struct('solver_success',logical(success),'passed',false,'hour_index',hour_index, ...
    'weather',weather,'weather_is_observed',false,'solver',options.solver, ...
    'thermal_segment_count',height(segments),'overhead_branch_count',height(limits.branch), ...
    'all_active_overhead_segments_constrained',true,'current_gamma_lift',false, ...
    'resistance_mode','declared_reference_temperature_not_solved_equilibrium', ...
    'as_built_or_historical_replay_claimed',false,'limits',limits);
if ~success,return;end
thermal=ac_dlr_current_audit(result,segments,conductors,segments.reference_temperature_c,limits);
audit.thermal=thermal;
% The independent AC audit also checks the six transfer schedules and the
% original generator boxes. It is delivered with the AC case constructor.
audit.electrical=audit_ac_solution(candidate,result);
audit.terminal=ac_terminal_current_audit(result,candidate.userdata.ac_system.terminal_current_limits);
audit.section_ends=ac_terminal_current_audit(result,candidate.userdata.ac_system.conductor_section_end_current_limits);
audit.passed=thermal.passed&&audit.electrical.passed&&audit.terminal.passed&&audit.section_ends.passed;
end
