function report = validate_research_inputs(inputs, contract, options)
%VALIDATE_RESEARCH_INPUTS Validate observations before any case modification.
% Unique electrical keys are timestamp/kind/entity; accounting_id and
% scenario_id aliases cannot bypass duplicate-injection detection.
if nargin < 2 || isempty(contract), contract = research_model_contract; end
if nargin < 3, options = struct(); end
if ~isfield(options, 'fail_on_error'), options.fail_on_error = true; end
errors = strings(0,1);
required = ["scenario_id","timestamp_utc","kind","entity_id","value", ...
    "unit","power_scale","provenance_class","source_uri","source_sha256", ...
    "accounting_id","dataset_split","target_use"];
if ~istable(inputs) || ~all(ismember(required, string(inputs.Properties.VariableNames)))
    errors(end+1) = "schema: missing required observation columns";
    report = finish(errors, options); return;
end
if isempty(inputs)
    errors(end+1) = "schema: no observations supplied";
    report = finish(errors, options); return;
end
for name = required(required ~= "value")
    v = string(inputs.(name));
    if any(ismissing(v) | strlength(strtrim(v)) == 0)
        errors(end+1) = "schema: empty " + name;
    end
end
v = inputs.value;
if ~isnumeric(v) || any(~isfinite(v)), errors(end+1) = "value: must be finite numeric"; end
kind = string(inputs.kind); entity = string(inputs.entity_id);
allowed = ["load_p","load_q","generation_p","generation_q", ...
    "external_import_p","external_import_q","interface_p","voltage_vm"];
if any(~ismember(kind, allowed)), errors(end+1) = "kind: unsupported electrical quantity"; end
units = repmat("MW", height(inputs),1);
units(endsWith(kind,"_q")) = "MVAr"; units(kind == "voltage_vm") = "pu";
if any(string(inputs.unit) ~= units), errors(end+1) = "unit: inconsistent electrical units"; end
if any(string(inputs.power_scale) ~= string(contract.power_scale))
    errors(end+1) = "scale: observations do not match case power scale";
end
if isnumeric(v) && any(v(kind == "load_p") < 0)
    errors(end+1) = "load: active demand must be nonnegative";
end
provenance = string(inputs.provenance_class);
allowed_provenance = ["public_observation","declared_assumption"];
if contract.allow_synthetic_observations, allowed_provenance(end+1) = "synthetic_fixture"; end
if any(~ismember(provenance, allowed_provenance))
    errors(end+1) = "provenance: unsupported or synthetic observation class";
end
observed = provenance == "public_observation";
hash = string(inputs.source_sha256);
if any(observed & cellfun(@isempty, regexp(cellstr(hash), '^[a-fA-F0-9]{64}$', 'once')))
    errors(end+1) = "provenance: public observations require a SHA256 source fingerprint";
end
if any(observed & ~startsWith(string(inputs.source_uri), ["https://","http://"]))
    errors(end+1) = "provenance: public observations require a source URL";
end
stamp = string(inputs.timestamp_utc);
if any(cellfun(@isempty, regexp(cellstr(stamp), '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$', 'once')))
    errors(end+1) = "vintage: timestamps must be explicit UTC ISO-8601";
else
    try
        t = datetime(stamp, 'InputFormat', "yyyy-MM-dd'T'HH:mm:ss'Z'", 'TimeZone', 'UTC');
        lo = datetime(contract.observation_valid_from_utc, 'InputFormat', "yyyy-MM-dd'T'HH:mm:ss'Z'", 'TimeZone','UTC');
        hi = datetime(contract.observation_valid_until_utc, 'InputFormat', "yyyy-MM-dd'T'HH:mm:ss'Z'", 'TimeZone','UTC');
        if any(isnat(t) | t < lo | t >= hi), errors(end+1) = "vintage: observation outside declared topology window"; end
    catch
        errors(end+1) = "vintage: invalid calendar date";
    end
end
key = stamp + "|" + kind + "|" + entity;
if numel(unique(key)) ~= height(inputs), errors(end+1) = "accounting: duplicate electrical observation/injection"; end
ak = stamp + "|" + string(inputs.accounting_id);
if numel(unique(ak)) ~= height(inputs), errors(end+1) = "accounting: reused accounting_id at same timestamp"; end
splits = string(inputs.dataset_split); uses = string(inputs.target_use);
if any(~ismember(splits,["calibration","held_out","diagnostic"])) || ...
        any(~ismember(uses,["input","calibration_target","validation_target"]))
    errors(end+1) = "evidence: unknown split or target use";
end
if any(splits == "held_out" & uses == "calibration_target") || ...
        any(provenance ~= "public_observation" & uses == "validation_target")
    errors(end+1) = "evidence: reconstruction or assumed targets cannot be independent held-out evidence";
end
for scenario = unique(string(inputs.scenario_id))'
    rows = string(inputs.scenario_id) == scenario;
    if numel(unique(stamp(rows))) ~= 1
        errors(end+1) = "scenario: operating point contains mismatched timestamps";
    end
    loads = rows & kind == "load_p";
    if any(loads) && (~isequal(sort(entity(loads)), string(('A':'K')')))
        errors(end+1) = "load: require exactly one actual-MW load for each zone A-K";
    end
end
report = finish(errors, options);
report.observation_count = height(inputs);
report.power_scale = contract.power_scale;
report.is_release_validation = false;
end

function report = finish(errors, options)
report = struct('pass',isempty(errors),'errors',errors,'is_release_validation',false);
if ~report.pass && options.fail_on_error
    error('validate_research_inputs:Invalid', '%s', strjoin(errors, newline));
end
end
