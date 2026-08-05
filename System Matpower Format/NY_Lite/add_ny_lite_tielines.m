function [mpc, added] = add_ny_lite_tielines(mpc, profile, options)
%ADD_NY_LITE_TIELINES Append selected NY-lite equivalent branches.
%   Idempotence is based on persistent candidate names stored in userdata,
%   not on the current reactance value.

if nargin < 2 || isempty(profile), profile = 'core'; end
if nargin < 3, options = struct(); end
if ~isfield(options, 'on_existing'), options.on_existing = 'skip'; end
if ~isfield(options, 'candidate_override'), options.candidate_override = []; end

mpc = attach_nyiso_zone_metadata(mpc);
if ~isfield(mpc.userdata, 'ny_lite') || ~isfield(mpc.userdata.ny_lite, 'original_branch_count')
    mpc.userdata.ny_lite.original_branch_count = size(mpc.branch, 1);
end
if ~isfield(mpc.userdata.ny_lite, 'added_tielines')
    mpc.userdata.ny_lite.added_tielines = struct([]);
end

candidates = ny_lite_tieline_candidates;
if ~isempty(options.candidate_override)
    candidates = apply_candidate_override(candidates, options.candidate_override);
end
names = {candidates.name};
if iscell(profile)
    selected = ismember(names, profile);
elseif strcmpi(profile, 'core')
    selected = [candidates.include_default];
elseif strcmpi(profile, 'all')
    selected = true(size(candidates));
elseif strcmpi(profile, 'none')
    selected = false(size(candidates));
else
    selected = ismember(names, {char(profile)});
    if ~any(selected)
        error('add_ny_lite_tielines:UnknownProfile', ...
            'Unknown tie-line profile or candidate: %s', char(profile));
    end
end

existing_names = {};
if ~isempty(mpc.userdata.ny_lite.added_tielines) && ...
        isfield(mpc.userdata.ny_lite.added_tielines, 'name')
    existing_names = {mpc.userdata.ny_lite.added_tielines.name};
end
added = struct([]);
for k = find(selected)
    c = candidates(k);
    if any(strcmp(c.name, existing_names))
        if strcmpi(options.on_existing, 'error')
            error('add_ny_lite_tielines:AlreadyAdded', ...
                'Candidate %s has already been added.', c.name);
        end
        continue;
    end

    ncol = max(13, size(mpc.branch, 2));
    new_branch = zeros(1, ncol);
    new_branch(1:13) = [c.from_bus, c.to_bus, c.br_r_initial, c.br_x_initial, ...
        c.br_b_initial, c.rate_a_initial, c.rate_b_initial, c.rate_c_initial, ...
        0, 0, 1, -360, 360];
    mpc.branch = [mpc.branch; new_branch];

    tagged = c;
    tagged.branch_index = size(mpc.branch, 1);
    if isempty(added), added = tagged; else, added(end + 1) = tagged; end %#ok<AGROW>
    existing_names{end + 1} = c.name; %#ok<AGROW>
end

if ~isempty(added)
    if isempty(mpc.userdata.ny_lite.added_tielines)
        mpc.userdata.ny_lite.added_tielines = added;
    else
        mpc.userdata.ny_lite.added_tielines = ...
            [mpc.userdata.ny_lite.added_tielines, added];
    end
end
mpc.userdata.ny_lite.tieline_profile = profile;
end
function candidates = apply_candidate_override(candidates, overrides)
if ~isstruct(overrides)
    error('add_ny_lite_tielines:BadOverride', ...
        'candidate_override must be a struct array.');
end
for k = 1:numel(overrides)
    if ~isfield(overrides(k), 'name')
        error('add_ny_lite_tielines:BadOverride', ...
            'Each candidate override must include a name field.');
    end
    idx = find(strcmp({candidates.name}, overrides(k).name), 1);
    if isempty(idx)
        error('add_ny_lite_tielines:UnknownOverride', ...
            'No tie-line candidate named %s exists.', overrides(k).name);
    end
    fields = fieldnames(overrides(k));
    for f = 1:numel(fields)
        candidates(idx).(fields{f}) = overrides(k).(fields{f});
    end
end
end
