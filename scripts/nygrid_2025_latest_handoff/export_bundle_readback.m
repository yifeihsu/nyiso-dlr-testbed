function export_bundle_readback()
% Read current consolidated bundle tables for independent comparison only.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
out=fullfile(root,'output','nygrid_2025_latest_handoff','independent_bundle');
if ~isfolder(out),mkdir(out);end
d=load(fullfile(root,'output','nygrid_2025_latest_handoff','model','latest_model.mat'),'model');m=d.model;
a=table(double(m.axis.hour_index),string(m.axis.timestamp_utc),logical(m.axis.source_qualified), ...
    double(m.axis.state_index),double(m.axis.reference_bus),logical(m.axis.post_dover_full_service), ...
    'VariableNames',{'hour_index','timestamp_utc','source_qualified','state_index','reference_bus','post_dover_full_service'});
writetable(a,fullfile(out,'bundled_hour_axis.csv'));
writetable(m.generator_registry,fullfile(out,'bundled_generator_registry.csv'));
writetable(m.fixed_transfer_registry,fullfile(out,'bundled_transfer_registry.csv'));
writetable(m.thermal.branch_registry,fullfile(out,'bundled_thermal_branch_registry.csv'));
writetable(m.thermal.conductors,fullfile(out,'bundled_conductors.csv'));
writetable(m.thermal.geometry,fullfile(out,'bundled_geometry.csv'));
writetable(m.thermal.cable_conflicts,fullfile(out,'bundled_cable_conflicts.csv'));
end
