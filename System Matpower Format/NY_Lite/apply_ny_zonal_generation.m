function [mpc, report] = apply_ny_zonal_generation(mpc, targets, options)
%APPLY_NY_ZONAL_GENERATION Allocate A-K generation targets to online units.

if nargin < 2, targets = []; end
if nargin < 3, options = struct(); end
if ~isfield(options, 'target_file')
    options.target_file = fullfile(fileparts(mfilename('fullpath')), ...
        'ny_zonal_generation_and_interchange.csv');
end
if ~isfield(options, 'fixed_snapshot'), options.fixed_snapshot = false; end

GEN_BUS=1; PG=2; GEN_STATUS=8; PMAX=9; PMIN=10;
mpc = attach_nyiso_zone_metadata(mpc);
zones = nyiso_zone_metadata;
target_mw = normalize_targets(targets, zones, options);
report = struct([]);

for z = 1:numel(zones)
    zone_bus_ids = mpc.bus(strcmp(mpc.userdata.nyiso_physical_zone, zones(z).letter), 1);
    gi = find(mpc.gen(:, GEN_STATUS) > 0 & ismember(mpc.gen(:, GEN_BUS), zone_bus_ids));
    if isempty(gi)
        if abs(target_mw(z)) > 1e-8
            error('apply_ny_zonal_generation:MissingGenerator', ...
                ['Zone %s has a nonzero generation target but no online generator. ' ...
                 'Call add_ny_equivalent_generators or revise the target.'], zones(z).letter);
        end
        allocation = zeros(0,1);
    else
        allocation = project_total(target_mw(z), mpc.gen(gi, PMIN), ...
            mpc.gen(gi, PMAX), mpc.gen(gi, PG));
        mpc.gen(gi, PG) = allocation;
        if options.fixed_snapshot
            mpc.gen(gi, PMIN) = allocation;
            mpc.gen(gi, PMAX) = allocation;
        end
    end
    rec = struct('zone_letter', zones(z).letter, 'target_mw', target_mw(z), ...
        'applied_mw', sum(allocation), 'generator_indices', gi(:)');
    if isempty(report), report = rec; else, report(end + 1) = rec; end %#ok<AGROW>
end
mpc.userdata.ny_lite.zonal_generation_report = report;
end

function target = normalize_targets(input, zones, options)
if isempty(input)
    error('apply_ny_zonal_generation:TargetsRequired', ...
        'Explicit zonal generation targets or a scenario_id are required.');
end
if ischar(input) || (exist('isstring','builtin') && isstring(input))
    token = char(input);
    if exist(token, 'file') == 2
        tbl = readtable(token);
    else
        tbl = readtable(options.target_file);
        names = cellfun(@lower, tbl.Properties.VariableNames, 'UniformOutput', false);
        sc = find(strcmp(names, 'scenario_id'), 1);
        if isempty(sc), error('Generation target file lacks scenario_id.'); end
        vals = tbl{:, sc};
        if iscell(vals), mask = strcmp(vals, token); else, mask = strcmp(cellstr(vals), token); end
        tbl = tbl(mask, :);
        if height(tbl)==0, error('Unknown generation scenario %s.', token); end
    end
    input = tbl;
end
if isnumeric(input)
    if numel(input) ~= numel(zones), error('Expected 11 A-K generation targets.'); end
    target = input(:);
elseif (exist('istable','builtin') || exist('istable','file')) && istable(input)
    names = cellfun(@lower, input.Properties.VariableNames, 'UniformOutput', false);
    zc = find(strcmp(names,'nyiso_zone_letter') | strcmp(names,'zone'), 1);
    gc = find(strcmp(names,'generation_mw') | strcmp(names,'target_generation_mw'), 1);
    if isempty(zc) || isempty(gc), error('Generation table needs zone and generation_mw columns.'); end
    target = NaN(numel(zones),1);
    for k=1:height(input)
        zv=input{k,zc}; if iscell(zv), zv=zv{1}; end
        zi=nyiso_zone_index(char(zv));
        gv=input{k,gc};
        if iscell(gv), gv=gv{1}; end
        if isnumeric(gv)
            value = double(gv);
        else
            value = str2double(char(gv));
        end
        if ~isnan(zi), target(zi)=value; end
    end
else
    error('Unsupported generation-target input type.');
end
if any(~isfinite(target)) || any(target < -1e-8)
    error('Generation targets must be complete, finite, and nonnegative.');
end
end

function pg = project_total(target, pmin, pmax, seed)
pmin=pmin(:); pmax=pmax(:); seed=seed(:);
if target < sum(pmin)-1e-7 || target > sum(pmax)+1e-7
    error('apply_ny_zonal_generation:InfeasibleTarget', ...
        'Target %.6g MW is outside aggregate limits [%.6g, %.6g].', ...
        target, sum(pmin), sum(pmax));
end
pg=min(max(seed,pmin),pmax);
for iter=1:100
    delta=target-sum(pg);
    if abs(delta)<1e-8, break; end
    if delta>0, room=pmax-pg; else, room=pg-pmin; end
    active=room>1e-10;
    if ~any(active), break; end
    weights=room; weights(~active)=0; weights=weights/sum(weights);
    step=delta*weights;
    if delta>0, step=min(step,room); else, step=max(step,-room); end
    pg=pg+step;
end
if abs(target-sum(pg))>1e-6, error('Could not allocate zonal target within limits.'); end
end
