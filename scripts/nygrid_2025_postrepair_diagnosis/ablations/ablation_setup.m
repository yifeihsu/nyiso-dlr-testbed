function [root,out,recipe,setup]=ablation_setup()
% Authenticated diagnostic overlay on the frozen current executable bundle.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
out=fullfile(root,'output','nygrid_2025_postrepair_diagnosis','ablations');
recipe=jsondecode(fileread(fullfile(out,'scenario_recipe.json')));
bundle=fullfile(root,'output','nygrid_2025_moses_repair','annual','candidate_bundle');
addpath(fullfile(bundle,'runtime'));setup=setup_nygrid_latest(bundle,'C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower');
for k=1:numel(recipe.inputs)
    entry=recipe.inputs(k);assert(strcmp(nylatest_file_sha256(fullfile(root,entry.path)),entry.sha256),'ablation:ChangedInput','Frozen ablation input changed: %s',entry.path);
end
end
