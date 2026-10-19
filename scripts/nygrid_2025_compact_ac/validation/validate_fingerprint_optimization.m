function report=validate_fingerprint_optimization()
% The optimized single-update digest must preserve every exported cache hash.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'scripts','nygrid_2025_compact_ac','core'));
files=dir(fullfile(root,'output','nygrid_2025_compact_ac','models','compact_ac_h*.mat'));assert(numel(files)==5);
rows=struct([]);
for k=1:numel(files)
    d=load(fullfile(files(k).folder,files(k).name),'model');
    current=compact_ac_operator_fingerprint(d.model);assert(strcmp(current,d.model.operator_fingerprint));
    rows=[rows struct('file',files(k).name,'stored_operator_fingerprint',d.model.operator_fingerprint, ...
        'current_operator_fingerprint',current,'passed',true)]; %#ok<AGROW>
end
report=struct('passed',true,'exported_models',5,'operator_bytes_unchanged',true,'checks',rows);
path=fullfile(root,'output','nygrid_2025_compact_ac','validation','fingerprint_optimization_parity.json');
fid=fopen(path,'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
fprintf('OPERATOR_FINGERPRINT_OPTIMIZATION 5/5 unchanged\n');
end
