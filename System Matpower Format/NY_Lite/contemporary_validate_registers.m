function report = contemporary_validate_registers(assets, generators)
%CONTEMPORARY_VALIDATE_REGISTERS Structural accounting is separate from readiness.
if nargin < 1 || isempty(assets)
    assets = readtable(fullfile(fileparts(mfilename('fullpath')), ...
        'contemporary_asset_register.csv'),'TextType','string');
end
if nargin < 2, generators = table(); end
errors = strings(0,1); blockers = strings(0,1);
req = ["asset_id","status_at_cutoff","status_known_by","review_cutoff", ...
    "implemented","model_element_ids","parameter_source","source_url", ...
    "overhead_dlr_eligible","facility_type"];
if ~istable(assets) || isempty(assets) || ~all(ismember(req,string(assets.Properties.VariableNames)))
    errors(end+1) = "asset_schema_missing";
else
    if numel(unique(string(assets.asset_id))) ~= height(assets), errors(end+1) = "duplicate_asset_id"; end
    if any(string(assets.review_cutoff) ~= "2026-09-06"), errors(end+1) = "asset_cutoff_mismatch"; end
    try
        known = datetime(string(assets.status_known_by),'InputFormat','yyyy-MM-dd');
        cutoff = datetime(2026,9,6);
        if any(isnat(known) | known > cutoff), errors(end+1) = "asset_status_date_after_cutoff"; end
    catch
        errors(end+1) = "asset_status_date_invalid";
    end
    if any(~ismember(string(assets.status_at_cutoff),["in_service","completion_unverified","future"]))
        errors(end+1) = "asset_status_unknown";
    end
    active = string(assets.status_at_cutoff) == "in_service";
    implemented = strcmpi(string(assets.implemented),"true") | string(assets.implemented) == "1";
    if any(implemented & ~active), errors(end+1) = "future_or_unverified_asset_implemented"; end
    if any(implemented & (ismember(string(assets.model_element_ids),["unmapped",""]) | ...
            ismember(string(assets.parameter_source),["unavailable",""])))
        errors(end+1) = "implemented_asset_without_mapping_or_parameters";
    end
    if any(~startsWith(string(assets.source_url),"https://")), errors(end+1) = "missing_asset_source"; end
    thermal = strcmpi(string(assets.overhead_dlr_eligible),"true") | string(assets.overhead_dlr_eligible) == "1";
    if any(thermal & string(assets.facility_type) ~= "ac_overhead_corridor")
        errors(end+1) = "nonoverhead_asset_marked_overhead_dlr_eligible";
    end
    if any(thermal & ~implemented), errors(end+1) = "unmapped_asset_marked_dlr_eligible"; end
    ids = string(assets.model_element_ids(implemented));
    if numel(unique(ids)) ~= numel(ids), errors(end+1) = "duplicate_model_element_accounting"; end
    if any(active & ~implemented), blockers(end+1) = "in_service_projects_not_yet_electrically_mapped"; end
end
if isempty(generators)
    blockers(end+1) = "contemporary_generator_register_not_supplied";
else
    greq = ["accounting_id","source_gen_row","release_eligible", ...
        "contemporary_unit_id","contemporary_status","contemporary_pmin_mw", ...
        "contemporary_pmax_mw","contemporary_qmin_mvar","contemporary_qmax_mvar"];
    if ~all(ismember(greq,string(generators.Properties.VariableNames)))
        errors(end+1) = "generator_schema_missing";
    else
        if numel(unique(string(generators.accounting_id))) ~= height(generators) || ...
                numel(unique(generators.source_gen_row)) ~= height(generators)
            errors(end+1) = "duplicate_generator_accounting";
        end
        eligible = strcmpi(string(generators.release_eligible),"true") | string(generators.release_eligible) == "1";
        pmin = generators.contemporary_pmin_mw; pmax = generators.contemporary_pmax_mw;
        qmin = generators.contemporary_qmin_mvar; qmax = generators.contemporary_qmax_mvar;
        invalid = ~isfinite(pmin) | ~isfinite(pmax) | ~isfinite(qmin) | ~isfinite(qmax) | pmin > pmax | qmin > qmax | ...
            string(generators.contemporary_unit_id) == "unmapped" | string(generators.contemporary_status) == "unverified";
        if any(eligible & invalid), errors(end+1) = "unverified_generator_marked_eligible"; end
        if any(~eligible), blockers(end+1) = "contemporary_generator_crosswalk_incomplete"; end
    end
end
report = struct('pass',isempty(errors),'errors',errors,'release_blockers',blockers, ...
    'release_ready',false,'scope',"registry_accounting_only");
end
