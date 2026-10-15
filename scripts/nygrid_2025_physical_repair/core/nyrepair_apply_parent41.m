function [m,change]=nyrepair_apply_parent41(m)
% Restore imported R/X with a complete, frozen synthetic conductor realization.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
path=fullfile(root,'output','nygrid_2025_physical_repair','physics','parent41_parameters.json');
p=jsondecode(fileread(path));parent=m.userdata.ac_system.branch_parent_row(:);r=find(parent==41);assert(isscalar(r));
assert(max(abs(m.branch(r,3:5)-p.baseline_R_X_B(:)'))<1e-10,'nyrepair:Parent41Base','Unexpected parent41 baseline; do not apply twice.');
before=m.branch(r,:);m.branch(r,3:5)=p.repaired_R_X_B(:)';
m.userdata.ac_system.thermal_segments=replace_segment(m.userdata.ac_system.thermal_segments,r,p.thermal_segment);
m.userdata.ac_sections.thermal_segments=replace_segment(m.userdata.ac_sections.thermal_segments,r,p.thermal_segment);
assert(isequal(before([1:2 6:end]),m.branch(r,[1:2 6:end])),'nyrepair:Apparatus','Only electrical R/X/B may change.');
change=struct('parent',41,'runtime_rows',r,'before_R_X_B',before(3:5),'after_R_X_B',m.branch(r,3:5), ...
    'catalog_id',p.selected_candidate.catalog_id,'circuits',p.selected_candidate.circuits, ...
    'length_m',p.selected_candidate.length_m,'geographic_chord_required',false,'installed_conductor_identified',false, ...
    'thermal_metadata_rebuilt',true,'aggregate_apparatus_current_ceiling_preserved',true, ...
    'parameter_file_sha256',nylatest_file_sha256(path));
end

function out=replace_segment(old,row,values)
was_table=istable(old);was_cell=iscell(old);if was_table,T=old;elseif was_cell,T=struct2table([old{:}]);else,T=struct2table(old);end
which=find(T.branch_row==row);assert(isscalar(which));names=fieldnames(values);
for i=1:numel(names)
    name=names{i};if ~ismember(name,T.Properties.VariableNames),continue;end
    value=values.(name);column=T.(name);
    if iscell(column),column{which}=value;
    elseif isstring(column),column(which)=string(value);
    elseif islogical(column),column(which)=logical(value);
    else,column(which)=value;end
    T.(name)=column;
end
if ismember('corridor_segment_length_m',T.Properties.VariableNames),T.corridor_segment_length_m(which)=values.segment_length_m;end
if was_table,out=T;else,out=table2struct(T);if was_cell,out=num2cell(out);end,end
end
