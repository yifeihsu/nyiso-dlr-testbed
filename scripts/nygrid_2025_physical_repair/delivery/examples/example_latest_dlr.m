% Run from the extracted package root. Weather is an explicit study scenario.
addpath(fullfile(pwd,'runtime'));
env=setup_nygrid_latest(pwd);
[result,audit,full,allocation]=run_nygrid_latest_acpf(8508);
assert(result.success&&audit.loss_allocation_gate&&audit.reduction_and_equation_gate);
weather=struct('ambient_c',25,'wind_m_s',1.5,'wind_angle_deg',90, ...
    'solar_w_m2',1000,'pressure_pa',101325);
cached=struct('full',full,'audit',audit,'allocation',allocation);
screen=screen_nygrid_latest_dlr(cached,weather);
fprintf('Equation/accounting pass: %d; operating limits pass: %d\n', ...
    result.success,audit.VQ_and_generator_assumption_gate);
fprintf('Eligible synthetic parents: %d; maximum series utilization: %.6f\n', ...
    screen.candidate_parent_count,screen.maximum_series_ampacity_utilization);
out=fullfile(pwd,'runs','example_8508');if ~isfolder(out),mkdir(out);end
writetable(screen.branch_screen,fullfile(out,'branch_screen.csv'));
writetable(screen.segment_screen,fullfile(out,'segment_screen.csv'));
writetable(screen.candidate_and_exclusion_ledger,fullfile(out,'candidate_and_exclusion_ledger.csv'));
save(fullfile(out,'example_result.mat'),'env','result','audit','full','allocation','weather','screen','-v7');
