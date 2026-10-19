function summary=validate_full_loader(out)
% Fresh MATPOWER verification of the derived full-system final-device loader.
% This tests its independent annual DC replay, not equivalence to reduced NYgrid.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
if nargin<1||isempty(out),out=fullfile(root,'output','nygrid_2019_full_stage1');end
[found,location]=fileattrib(out);assert(found&&isscalar(location)&&location.directory, ...
    'nygrid:OutputFolder','The selected baseline folder does not exist.');
out=location.Name;
oldpath=path;path_cleanup=onCleanup(@()path(oldpath));
addpath(fullfile(root,'System Matpower Format'));
d=load(fullfile(out,'full_year.mat'),'hour_index','branch_pf','result_pg','bus_va');
c=load(fullfile(out,'captured_stages.mat'),'hour_indices');
assert(isequal(d.hour_index(:),(1:8760)') && size(d.branch_pf,1)==8760, ...
    'nygrid:Coverage','Require complete annual baseline.');
assert(numel(c.hour_indices)==13 && numel(unique(c.hour_indices))==13);
opts=mpoption('verbose',0,'out.all',0,'exp.use_legacy_core',1);
tolerance=1e-7;
rows=cell(numel(c.hour_indices),1);
for k=1:numel(c.hour_indices)
    h=c.hour_indices(k);
    m=npcc_nygrid_2019_full_dc(h,out);
    [r,success]=rundcpf(m,opts);
    assert(success && all(isfinite(r.branch(:,14))), ...
        'nygrid:FullLoaderPF','DC PF failed for hour %d.',h);
    branch_error=max(abs(r.branch(:,14)'-d.branch_pf(h,:)));
    generation_error=max(abs(r.gen(:,2)'-d.result_pg(h,:)));
    angle_error=max(abs(r.bus(:,9)'-d.bus_va(h,:)));
    [~,gf]=ismember(r.gen(:,1),r.bus(:,1));
    [~,bf]=ismember(r.branch(:,1),r.bus(:,1));[~,bt]=ismember(r.branch(:,2),r.bus(:,1));
    [~,df]=ismember(r.dcline(:,1),r.bus(:,1));[~,dt]=ismember(r.dcline(:,2),r.bus(:,1));
    assert(all([gf;bf;bt;df;dt]>0));
    n=size(r.bus,1);
    injection=accumarray(gf,r.gen(:,2).*(r.gen(:,8)>0),[n,1])-r.bus(:,3)-r.bus(:,5);
    exits=accumarray(bf,r.branch(:,14),[n,1])+accumarray(bt,r.branch(:,16),[n,1]) ...
        +accumarray(df,r.dcline(:,4),[n,1])-accumarray(dt,r.dcline(:,5),[n,1]);
    residual=max(abs(injection-exits));
    assert(max([branch_error,generation_error,angle_error,residual])<tolerance, ...
        'nygrid:FullLoaderMismatch','Independent annual replay differs at hour %d.',h);
    rows{k}=table(h,string(m.userdata.nygrid2019.prepared_local_label),success, ...
        branch_error,generation_error,angle_error,residual, ...
        'VariableNames',{'hour_index','prepared_local_hour','dc_pf_success','branch_max_error_mw', ...
        'generation_max_error_mw','angle_max_error_deg','nodal_balance_residual_mw'});
end
% Index guards are checked before file access/indexing, including malformed input.
invalid={0,-1,8761,1.5,NaN,Inf,[1 2],"1"};
for k=1:numel(invalid)
    rejected=false;
    try
        npcc_nygrid_2019_full_dc(invalid{k},out);
    catch e
        rejected=strcmp(e.identifier,'nygrid:HourIndex');
    end
    assert(rejected,'nygrid:IndexGuard','Malformed hour index was not rejected as intended.');
end
checks=vertcat(rows{:});
writetable(checks,fullfile(out,'full_loader_validation.csv'));
summary=struct('passed',true,'fresh_matpower_hours',height(checks),'invalid_index_guards',numel(invalid), ...
    'tolerance_mw',tolerance,'tolerance_angle_deg',tolerance, ...
    'max_branch_error_mw',max(checks.branch_max_error_mw), ...
    'max_generation_error_mw',max(checks.generation_max_error_mw), ...
    'max_angle_error_deg',max(checks.angle_max_error_deg), ...
    'max_nodal_balance_residual_mw',max(checks.nodal_balance_residual_mw), ...
    'matlab_version',version,'matpower_version',mpver, ...
    'validation_scope','fresh MATPOWER full final-device solve agrees with independent annual DC reconstruction', ...
    'released_reduced_model_equivalence_claimed',false,'ac_or_equipment_feasibility_claimed',false);
fid=fopen(fullfile(out,'full_loader_validation.json'),'w');assert(fid>=0);
cleanup=onCleanup(@()fclose(fid));fprintf(fid,'%s\n',jsonencode(summary,PrettyPrint=true));
disp(checks);
end
