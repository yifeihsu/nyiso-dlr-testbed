function report=audit_legacy_family()
% Read-only distinction between the S7/ENLITEN and released Cornell families.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
addpath(fullfile(root,'System Matpower Format','NY_Lite'));
names={'npcc_original','npcc_ny_lite_s7_seven_interface_perform_direct_candidate', ...
    'npcc_ny_lite_s7_seven_interface_perform_tieline_candidate'};
out=fullfile(root,'output','nygrid_2025_ac_loss_revision','impedance');
if ~isfolder(out),mkdir(out);end
rows=struct([]);
for j=1:numel(names)
    c=loadcase(names{j});
    hit=find((c.branch(:,1)==38&c.branch(:,2)==77)|(c.branch(:,1)==77&c.branch(:,2)==38));
    r=struct('case_name',names{j},'case_file',which(names{j}),'buses',size(c.bus,1), ...
        'branches',size(c.branch,1),'matching_38_77_rows',hit(:)', ...
        'matching_38_77_parameters',c.branch(hit,1:13));
    rows=[rows r]; %#ok<AGROW>
end
report=struct('passed',true,'scope','Read-only S7 family identity check; no solve or model change', ...
    'cases',rows,'all_38_77_pairs_absent',all(arrayfun(@(r)isempty(r.matching_38_77_rows),rows)));
fid=fopen(fullfile(out,'legacy_family_check.json'),'w');assert(fid>=0);
fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
disp(report);
end
