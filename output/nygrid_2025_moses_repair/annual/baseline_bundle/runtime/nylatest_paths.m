function paths=nylatest_paths()
% Resolve this current runtime's model location, without saved user paths.
runtime=fileparts(mfilename('fullpath'));
normalized=strrep(runtime,'\','/');
if endsWith(normalized,'/scripts/nygrid_2025_physical_repair/delivery/runtime')
    root=fileparts(fileparts(fileparts(fileparts(runtime))));
    model=fullfile(root,'output','nygrid_2025_physical_repair','model');
else
    root=fileparts(runtime);model=fullfile(root,'model');
end
paths=struct('root',root,'runtime',runtime,'kernels',fullfile(runtime,'kernels'), ...
    'model',model,'model_file',fullfile(model,'latest_model.mat'),'receipt',fullfile(model,'model_receipt.json'));
end
