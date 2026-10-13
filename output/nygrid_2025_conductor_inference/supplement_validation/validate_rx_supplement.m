restoredefaultpath;
parts=strsplit(path,pathsep);keep=startsWith(string(parts),string(matlabroot),'IgnoreCase',true);path(strjoin(parts(keep),pathsep));
clear functions;
root='C:/Users/Holiday/AppData/Local/Temp/nygrid_rx_supplement_823_xnad/nygrid_dlr_runtime_20261013';
addpath(fullfile(root,'scripts','nygrid_2025_dlr_handoff','runtime'));
setup_nygrid_2025_handoff(root);
addpath(fullfile(root,'scripts','nygrid_2025_conductor_inference'));
w=table(25,.6096,90,1000,101325,'VariableNames',{'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'});
s=screen_nygrid_2025_rx_thermal(8508,w);
assert(s.candidate_parent_count==180&&s.candidate_runtime_branch_count==252&&s.candidate_segment_count==253);
assert(s.numerical_identities_passed&&~s.electrical_solution_changed&&~s.current_gamma_rescaling_applied);
names={'nygrid_rx_thermal_candidates','screen_nygrid_2025_rx_thermal','run_nygrid_2025_loss_consistent_acpf','ac_conductor_heat'};
resolved=struct('name',{},'path',{});
for k=1:numel(names),f=which(names{k});assert(startsWith(char(java.io.File(f).getCanonicalPath()),[char(java.io.File(root).getCanonicalPath()) filesep],'IgnoreCase',true));resolved(end+1)=struct('name',names{k},'path',f);end
receipt=struct('passed',true,'MATLAB_version',version,'package_root',root,'candidate_parent_count',s.candidate_parent_count,...
 'candidate_runtime_branch_count',s.candidate_runtime_branch_count,'candidate_segment_count',s.candidate_segment_count,...
 'maximum_Joule_error_MW',s.maximum_Joule_loss_identity_error_MW,'maximum_current_error_A',s.maximum_terminal_current_crosscheck_error_A,...
 'maximum_series_utilization',s.maximum_series_ampacity_utilization,'electrical_solution_changed',s.electrical_solution_changed,...
 'VQ_operating_gate',s.inherited_VQ_operating_qualification,'function_resolution',resolved,'no_OPF',~s.OPF_run);
out=fullfile(root,'runs','rx_validation');
writetable(s.candidate_and_exclusion_ledger,fullfile(out,'candidate_ledger.csv'));
writetable(s.branch_screen,fullfile(out,'branch_screen.csv'));
f=fopen(fullfile(out,'matlab_portable_receipt.json'),'w');fprintf(f,'%s\n',jsonencode(receipt,'PrettyPrint',true));fclose(f);
disp(jsonencode(receipt));
