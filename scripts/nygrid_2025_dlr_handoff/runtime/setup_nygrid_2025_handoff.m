function info=setup_nygrid_2025_handoff(package_root,matpower_root)
%SETUP_NYGRID_2025_HANDOFF Session-only, explicitly rooted portable setup.
% Default vendor location is PACKAGE_ROOT/vendor/matpower8.1. An external
% MATPOWER8.1 root may be supplied explicitly. No saved user path is changed.
if nargin<1||isempty(package_root)
    package_root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
end
if nargin<2||isempty(matpower_root),matpower_root=fullfile(package_root,'vendor','matpower8.1');end
package_root=char(java.io.File(char(package_root)).getCanonicalPath());
matpower_root=char(java.io.File(char(matpower_root)).getCanonicalPath());
assert(usejava('jvm'),'handoff:JVM','This runtime requires MATLAB with JVM for SHA-256 source guards.');
assert(isfile(fullfile(matpower_root,'lib','runpf.m'))&&isfile(fullfile(matpower_root,'LICENSE')), ...
    'handoff:MATPOWER','Supply the bundled vendor/matpower8.1 directory or an explicit MATPOWER8.1 installation root.');
vendor_dirs={fullfile(matpower_root,'lib'),fullfile(matpower_root,'mips','lib'), ...
    fullfile(matpower_root,'mp-opt-model','lib'),fullfile(matpower_root,'mptest','lib')};
for k=1:numel(vendor_dirs),assert(isfolder(vendor_dirs{k}),'handoff:VendorClosure','Missing required vendor code folder.');addpath(vendor_dirs{k},'-begin');end
relative_dirs={'System Matpower Format','System Matpower Format/NY_Lite', ...
    'scripts/nygrid_2025_ac_system/branches','scripts/nygrid_2025_ac_system/thermal', ...
    'scripts/nygrid_2025_ac_system/ac_validation','scripts/nygrid_2025_acpf_profile_audit/acpf', ...
    'scripts/nygrid_2025_compact_ac/core','scripts/nygrid_2025_ac_loss_revision/core', ...
    'scripts/nygrid_2025_dlr_handoff/runtime'};
project_dirs=cell(size(relative_dirs));
for k=1:numel(relative_dirs)
    project_dirs{k}=fullfile(package_root,relative_dirs{k});assert(isfolder(project_dirs{k}),'handoff:ProjectClosure','Missing required project code folder.');
    addpath(project_dirs{k},'-begin');
end
assert(strcmp(mpver,'8.1'),'handoff:Version','This handoff was validated against MATPOWER8.1; use that version for reproduction.');
expected=char(java.io.File(fullfile(matpower_root,'lib','runpf.m')).getCanonicalPath());
actual=char(java.io.File(which('runpf')).getCanonicalPath());
assert(strcmpi(actual,expected),'handoff:ShadowedMATPOWER','runpf resolves outside the explicitly selected MATPOWER root.');
info=struct('package_root',package_root,'matpower_root',matpower_root,'MATLAB_version',version, ...
    'MATLAB_release',version('-release'),'MATPOWER_version',mpver,'MIPS_version',mipsver, ...
    'MP_Opt_Model_version',mpomver,'MP_Test_version',mpver_mptest, ...
    'project_paths',{project_dirs},'vendor_paths',{vendor_dirs},'persistent_user_path_changed',false, ...
    'JVM_required',true,'MATLAB_runtime_not_bundled',true,'vendor_case_data_not_required',true);
names={'npcc_nygrid_2025_ac','run_nygrid_2025_compact_acpf','run_nygrid_2025_loss_consistent_acpf', ...
    'run_nygrid_2025_ac_dlr','runpf','runopf','makeYbus','newtonpf','mips','have_feature'};
info.function_resolution=struct('name',{},'path',{});
for k=1:numel(names),info.function_resolution(end+1)=struct('name',names{k},'path',which(names{k}));end %#ok<AGROW>
end

function value=mpver_mptest()
if exist('mptestver','file'),value=mptestver;else,value='unknown';end
end
