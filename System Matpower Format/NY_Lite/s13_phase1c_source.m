function [src,buses,branches,relative_path,sha] = s13_phase1c_source
%S13_PHASE1C_SOURCE Verify the pinned electrical source and explicit selection.
h=fileparts(mfilename('fullpath'));root=fileparts(fileparts(h));
relative_path="PERFORM/On Peak 2019 v23_Perform_NY/On Peak 2019 v23/nyiso_On_Peak_v23_shunts_as_z_load.m";
path=fullfile(root,relative_path);addpath(fileparts(path));
fid=fopen(path,'rb');assert(fid>=0,'s13_phase1c_source:MissingSource','Missing source.');
cleanup=onCleanup(@()fclose(fid));bytes=fread(fid,Inf,'*uint8');
% The repository is used on Windows and Linux: normalize only line endings.
text=native2unicode(bytes','UTF-8');
text=strrep(text,sprintf('\r\n'),sprintf('\n'));
text=strrep(text,sprintf('\r'),sprintf('\n'));
bytes=unicode2native(text,'UTF-8');
d=java.security.MessageDigest.getInstance('SHA-256');d.update(bytes);
sha=string(lower(reshape(dec2hex(typecast(d.digest(),'uint8'),2).',1,[])));
buses=readtable(fullfile(h,'s13_phase1c_source_bus_manifest.csv'),'TextType','string');
branches=readtable(fullfile(h,'s13_phase1c_source_branch_manifest.csv'),'TextType','string');
assert(all(buses.source_sha256==sha)&&all(branches.source_sha256==sha), ...
    's13_phase1c_source:Hash','PERFORM source SHA-256 does not match the manifest.');
src=nyiso_On_Peak_v23_shunts_as_z_load;
[ok,idx]=ismember(buses.source_bus,src.bus(:,1));
assert(all(ok)&&numel(unique(buses.model_bus))==height(buses), ...
    's13_phase1c_source:BusIdentity','Invalid or duplicated bus manifest identity.');
assert(isequal(string(src.bus_name(idx)),buses.source_bus_name)&& ...
    isequal(src.bus(idx,10),buses.source_base_kv)&& ...
    isequal(perform_nyiso_zone_letters(src,buses.source_bus),buses.physical_zone), ...
    's13_phase1c_source:BusMetadata','Source bus manifest changed.');
expected=table2array(branches(:,2:14));
assert(isequal(src.branch(branches.source_branch_row,1:13),expected), ...
    's13_phase1c_source:BranchParameters','Source branch manifest changed.');
assert(numel(unique(branches.source_branch_row))==height(branches)&& ...
    all(ismember(expected(:,1:2),buses.source_bus),'all'), ...
    's13_phase1c_source:BranchIdentity','Branch identity or endpoint missing.');
end
