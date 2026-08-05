function outputs = build_nyiso_public_targets(scenarios, options)
%BUILD_NYISO_PUBLIC_TARGETS Populate scaled public NYISO target tables.

if nargin < 1 || isempty(scenarios)
    scenarios = nyiso_public_default_scenarios();
end
if nargin < 2, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
if ~isfield(options, 'scenario_file')
    options.scenario_file = fullfile(helper_dir, 'nyiso_public_scenarios.csv');
end
if ~isfield(options, 'load_target_file')
    options.load_target_file = fullfile(helper_dir, 'ny_zonal_load_targets.csv');
end
if ~isfield(options, 'interface_target_file')
    options.interface_target_file = fullfile(helper_dir, 'nyiso_public_interface_targets.csv');
end

load_opts = options;
load_opts.target_file = options.load_target_file;
load_opts.write_targets = true;
[load_rows, scenario_rows] = import_p58c_zonal_loads(scenarios, load_opts);

interface_opts = options;
interface_opts.target_file = options.interface_target_file;
interface_opts.write_targets = true;
[interface_rows, scenario_rows] = import_p32_interface_targets(scenario_rows, interface_opts);

writetable(scenario_rows, options.scenario_file);

outputs = struct( ...
    'scenario_file', options.scenario_file, ...
    'load_target_file', options.load_target_file, ...
    'interface_target_file', options.interface_target_file, ...
    'scenario_count', height(scenario_rows), ...
    'load_row_count', height(load_rows), ...
    'interface_row_count', height(interface_rows));
end
