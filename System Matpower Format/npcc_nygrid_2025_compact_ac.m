function model=npcc_nygrid_2025_compact_ac(hour_index)
%NPCC_NYGRID_2025_COMPACT_AC Compact AC admittance model anchored to148 buses.
% Use run_nygrid_2025_compact_acpf(model), not runpf(model): equivalent
% matrix couplings are not physical conductor branches. Detailed currents
% and eliminated voltages are recovered algebraically from the148-bus solve.
if nargin<1,hour_index=8508;end
root=fileparts(fileparts(mfilename('fullpath')));
addpath(fullfile(root,'scripts','nygrid_2025_compact_ac','core'));
model=compact_ac_build(npcc_nygrid_2025_ac(hour_index));
end
