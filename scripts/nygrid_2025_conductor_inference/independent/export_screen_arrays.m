function export_screen_arrays()
% Export only saved numerical arrays for an independent Python readback.
% No electrical or thermal solve; all outputs stay in the new audit namespace.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
out=fullfile(root,'output','nygrid_2025_conductor_inference','independent','screen_arrays');
if ~isfolder(out),mkdir(out);end
for hour=[4000 8508]
    source=fullfile(root,'output','nygrid_2025_conductor_inference','matlab_validation', ...
        sprintf('hour_%04d',hour),'selected_point_screen.mat');
    d=load(source,'full','audit','allocation');
    bus=d.full.bus;branch=d.full.branch;baseMVA=d.full.baseMVA;
    original_bus=d.allocation.final_input.bus;original_branch=d.allocation.final_input.branch;
    gen=d.full.gen;original_gen=d.allocation.final_input.gen;
    dcline=d.full.dcline;original_dcline=d.allocation.final_input.dcline;
    save(fullfile(out,sprintf('hour_%04d_numeric.mat',hour)), ...
        'hour','bus','branch','baseMVA','original_bus','original_branch','gen','original_gen', ...
        'dcline','original_dcline','-v7');
end
end
