function verify_ac_scoring_dc
%VERIFY_AC_SCORING_DC Independent raw-prior DC parity fixture, REF42.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(root,'System Matpower Format','NY_Lite'));define_constants;
file=fullfile(root,'output','nygrid_compact_2019','ac_checkpoint','restored_fleet_ac_checkpoint.mat');
manifest=readtable(fullfile(fileparts(file),'output_manifest.csv'),'TextType','string','Delimiter',',');
ix=manifest.relative_path=="restored_fleet_ac_checkpoint.mat";source_sha=char(ny_reference_file_sha256(file));
assert(nnz(ix)==1&&manifest.sha256(ix)==string(source_sha));
d=load(file,'out');dc_branch_pf=zeros(3,92);dc_pg=zeros(3,37);dc_va=zeros(3,51);
scenario_ids=cell(3,1);reference_bus=42;
for k=1:3
    s=d.out.cases{k}.snapshot;m=s.candidate;
    assert(m.bus(m.bus(:,BUS_TYPE)==REF,BUS_I)==reference_bus);
    [r,success]=rundcpf(m,mpoption('verbose',0,'out.all',0));assert(success);
    dc_branch_pf(k,:)=r.branch(:,PF)';dc_pg(k,:)=r.gen(:,PG)';dc_va(k,:)=r.bus(:,VA)';
    scenario_ids{k}=char(s.scenario_id);
end
folder=fullfile(root,'output','nygrid_compact_2019','ac_scoring');if ~isfolder(folder),mkdir(folder);end
save(fullfile(folder,'dc_matpower_parity.mat'),'dc_branch_pf','dc_pg','dc_va','scenario_ids','reference_bus','source_sha','-v7');
end
