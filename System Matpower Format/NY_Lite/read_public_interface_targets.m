function targets = read_public_interface_targets(scenario_id, target_file)
%READ_PUBLIC_INTERFACE_TARGETS Read scaled public interface targets.

if nargin < 2 || isempty(target_file)
    target_file = fullfile(fileparts(mfilename('fullpath')), ...
        'nyiso_public_interface_targets.csv');
end
if exist(target_file, 'file') ~= 2
    error('read_public_interface_targets:MissingFile', ...
        'Cannot find %s.', target_file);
end
targets = readtable(target_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
targets = targets(strcmp(string(targets.scenario_id), string(scenario_id)), :);
if height(targets) == 0
    error('read_public_interface_targets:MissingScenario', ...
        'No interface targets found for scenario %s.', string(scenario_id));
end
end
