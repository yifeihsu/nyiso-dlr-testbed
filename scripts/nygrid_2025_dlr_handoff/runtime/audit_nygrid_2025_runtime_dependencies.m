function report=audit_nygrid_2025_runtime_dependencies(matpower_root)
% Audit potential source dependencies; data closure is separately inventoried.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
setup=setup_nygrid_2025_handoff(root,matpower_root);
out=fullfile(root,'output','nygrid_2025_dlr_handoff','runtime_audit');if ~isfolder(out),mkdir(out);end
names={'npcc_nygrid_2025_ac','run_nygrid_2025_compact_acpf','run_nygrid_2025_loss_consistent_acpf', ...
    'run_nygrid_2025_ac_dlr','ac_dlr_prepare_case','ac_dlr_limits','ac_dlr_apply_resistance','ac_dlr_current_audit', ...
    'ac_conductor_heat','ac_conductor_resistance','dlr_heat_balance'};
if exist('screen_nygrid_2025_loss_pf_thermal','file'),names{end+1}='screen_nygrid_2025_loss_pf_thermal';end
if exist('smoke_nygrid_2025_handoff','file'),names{end+1}='smoke_nygrid_2025_handoff';end
entries=cellfun(@which,names,'UniformOutput',false);assert(all(~cellfun(@isempty,entries)));
[files,products]=matlab.codetools.requiredFilesAndProducts(entries);
records=struct('path',{},'scope',{},'relative_path',{},'sha256',{});
for k=1:numel(files)
    path=files{k};scope='other_external';relative='';
    if startsWith(path,[root filesep],'IgnoreCase',true),scope='project';relative=path(numel(root)+2:end);
    elseif startsWith(path,[setup.matpower_root filesep],'IgnoreCase',true),scope='MATPOWER';relative=path(numel(setup.matpower_root)+2:end);
    elseif startsWith(path,[matlabroot filesep],'IgnoreCase',true),scope='MATLAB_builtin_or_toolbox';relative=path(numel(matlabroot)+2:end);end
    records(end+1)=struct('path',path,'scope',scope,'relative_path',strrep(relative,filesep,'/'),'sha256',filehash(path)); %#ok<AGROW>
end
writetable(struct2table(records),fullfile(out,'static_function_dependencies.csv'));
report=struct('completed',true,'entrypoints',{names},'entrypoint_files',{entries},'setup',setup, ...
    'dependency_count',numel(files),'dependencies',records,'potential_required_products',products, ...
    'static_analysis_does_not_capture_dynamic_data_loads_or_all_callbacks',true, ...
    'potential_optional_solver_dependencies_are_not_required_for_selected_MIPS_runtime',true);
fid=fopen(fullfile(out,'static_function_dependency_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
fprintf('HANDOFF_DEPENDENCIES %d sources project%d MATPOWER%d other%d\n',numel(records),sum(strcmp({records.scope},'project')),sum(strcmp({records.scope},'MATPOWER')),sum(strcmp({records.scope},'other_external')));
disp(products);
end

function digest=filehash(path)
fid=fopen(path,'rb');assert(fid>=0);clean=onCleanup(@()fclose(fid));e=java.security.MessageDigest.getInstance('SHA-256');
while ~feof(fid),b=fread(fid,1048576,'*uint8');if ~isempty(b),e.update(typecast(b,'int8'));end,end
digest=lower(reshape(dec2hex(typecast(e.digest(),'uint8'),2)',1,[]));
end
