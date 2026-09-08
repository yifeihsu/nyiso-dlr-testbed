function out = build_s14_nyiso_retention_set(source, options)
%BUILD_S14_NYISO_RETENTION_SET Register NY buses and first external terminals.
% Diagnostic inventory only: constructing this table never qualifies a source
% or freezes promotion ports. Selection uses registered IDs, never BUS_AREA.
% options.zone_map requires bus_id, physical_zone; options.overlay_bus_map
% requires model_bus, physical_zone. Defaults use cumulative source metadata.
if nargin < 2, options = struct(); end
here = fileparts(mfilename('fullpath'));
if isfield(options, 'zone_map'), zones = options.zone_map;
else, zones = readtable(fullfile(here, 'ny_bus_zone_map.csv'), 'TextType','string'); end
if isfield(options, 'overlay_bus_map')
    overlay = options.overlay_bus_map;
elseif isfield(source, 'userdata') && isfield(source.userdata, 's13') && ...
        isfield(source.userdata.s13, 'overlay_report')
    overlay = source.userdata.s13.overlay_report.bus_map;
else
    overlay = table(zeros(0,1),strings(0,1), 'VariableNames',{'model_bus','physical_zone'});
end
ids = source.bus(:,1); n = numel(ids);
assert(numel(unique(ids)) == n, 's14:DuplicateBus', 'Source bus IDs must be unique.');
zone = strings(n,1); reason = strings(n,1); classification = repmat("npcc_equivalent_terminal",n,1);
confidence = repmat("registered",n,1);
for k = 1:height(zones)
    r = find(ids == zones.bus_id(k));
    if isempty(r), continue; end
    z = upper(string(zones.physical_zone(k)));
    if strlength(z) == 1 && any(z == string(('A':'K')'))
        zone(r) = z; reason(r) = "registered_nyiso_zone";
    end
end
for k = 1:height(overlay)
    r = find(ids == overlay.model_bus(k));
    assert(~isempty(r), 's14:MissingOverlayBus','Registered overlay bus absent from source.');
    z = upper(string(overlay.physical_zone(k)));
    assert(strlength(z)==1 && any(z == string(('A':'K')')), ...
        's14:OverlayZone','NY overlay must have a registered A-K zone.');
    zone(r) = z; reason(r) = "registered_nyiso_overlay";
    classification(r) = "source_backed_overlay_terminal";
end
ny = strlength(zone)>0;
assert(any(ny), 's14:EmptyNY','No registered NYISO bus is present.');
if ~isfield(options,'require_all_zones'), options.require_all_zones = true; end
if options.require_all_zones
    assert(all(ismember(string(('A':'K')'),zone(ny))), ...
        's14:ZoneCoverage','Retention must cover all eleven NYISO zones.');
end
[fok,f] = ismember(source.branch(:,1),ids); [tok,t] = ismember(source.branch(:,2),ids);
assert(all(fok & tok), 's14:UnknownBranchBus','Source branch references an unknown bus.');
% Retain endpoints of offline ties too, so outages do not rewrite the ports.
ties = xor(ny(f),ny(t));
boundary = unique([f(ties & ~ny(f)); t(ties & ~ny(t))]);
retain = ny; retain(boundary) = true;
reason(boundary) = "first_external_tie_terminal";
classification(boundary) = "external_boundary_terminal";
group = strings(n,1);
if isfield(options,'boundary_groups')
    groups = options.boundary_groups;
else
    groups = table([100;102;103;29;35;140;134;138;124;125], ...
        ["HQ";"ONTARIO";"ONTARIO";"ISONE";"ISONE";"PJM";"PJM";"PJM";"PJM";"PJM"], ...
        'VariableNames',{'bus_id','boundary_group'});
end
for k = 1:height(groups)
    r = find(ids == groups.bus_id(k));
    if ~isempty(r), group(r) = string(groups.boundary_group(k)); end
end
group(boundary(strlength(group(boundary))==0)) = "UNREGISTERED";
names = "BUS_" + string(ids);
if isfield(source,'bus_name'), names = string(source.bus_name(:)); end
rows = find(retain);
register = table(ids(rows), upper(strtrim(names(rows))), zone(rows), ...
    source.bus(rows,10),reason(rows),group(rows),classification(rows),rows,confidence(rows), ...
    'VariableNames',{'bus_id','normalized_name','zone','base_kv','retention_reason', ...
    'boundary_group','electrical_class','source_row','confidence'});
out = struct('register',register,'ny_bus_ids',ids(ny), ...
    'boundary_bus_ids',ids(boundary),'retained_bus_ids',ids(rows), ...
    'ny_internal_branch_rows',find(ny(f)&ny(t)), 'tie_branch_rows',find(ties), ...
    'source_keep_branch_rows',find(ny(f)|ny(t)), ...
    'ports_frozen_for_promotion',false,'promotion_eligible',false);
end
