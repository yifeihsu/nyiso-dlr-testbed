function records=loss_validation_source_records(root)
% Freeze numerical implementation, source arrays and the old cohort evidence.
old=jsondecode(fileread(fullfile(root,'output','nygrid_2025_compact_ac','validation','source_receipt.json')));
paths={fullfile(root,'System Matpower Format','run_nygrid_2025_loss_consistent_acpf.m'),[mfilename('fullpath'),'.m']};
for field={'source_data','source_code'}
    entries=old.(field{1});for j=1:numel(entries),paths{end+1}=fullfile(root,entries(j).path);end %#ok<AGROW>
end
for folder={fullfile(root,'scripts','nygrid_2025_ac_loss_revision','core')}
    d=dir(fullfile(folder{1},'*.m'));for k=1:numel(d),paths{end+1}=fullfile(d(k).folder,d(k).name);end %#ok<AGROW>
end
for extra={'output/nygrid_2025_downstate/network/bus_register.csv', ...
        'output/nygrid_2025_western_audit/dispatch/all_boundary_external_generator_shares.csv'}
    paths{end+1}=fullfile(root,extra{1}); %#ok<AGROW>
end
for mon=1:12
    paths{end+1}=fullfile(root,'output','nygrid_2025_acpf_profile_audit','acpf','monthly',sprintf('profile_PF_2025_%02d.mat',mon)); %#ok<AGROW>
end
for entry=old.numerical_library_files(:)',paths{end+1}=entry.path;end %#ok<AGROW>
paths=sort(unique(paths));records=struct('path',{},'sha256',{},'bytes',{});
for k=1:numel(paths)
    fid=fopen(paths{k},'rb');assert(fid>=0);engine=java.security.MessageDigest.getInstance('SHA-256');count=0;
    while ~feof(fid)
        bytes=fread(fid,1048576,'*uint8');count=count+numel(bytes);
        if ~isempty(bytes),engine.update(typecast(bytes,'int8'));end
    end
    fclose(fid);digest=lower(reshape(dec2hex(typecast(engine.digest(),'uint8'),2)',1,[]));
    records(end+1)=struct('path',paths{k},'sha256',digest,'bytes',count); %#ok<AGROW>
end
end
