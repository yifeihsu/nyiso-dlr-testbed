function observations = contemporary_import_nyiso_loads(files)
%CONTEMPORARY_IMPORT_NYISO_LOADS Import original NYISO palIntegrated daily CSVs.
% No download, interpolation, normalization, or time-zone guessing occurs.
% Files must retain their YYYYMMDDpalIntegrated.csv source filenames.
files = string(files(:)); observations = table();
zones = nyiso_zone_metadata; names = string({zones.name});
letters = string({zones.letter});
for k = 1:numel(files)
    [~, base, ext] = fileparts(files(k));
    if isempty(regexp(char(base+ext), '^\d{8}palIntegrated\.csv$', 'once'))
        error('contemporary_import_nyiso_loads:Filename', 'Expected original NYISO daily CSV filename.');
    end
    opts = detectImportOptions(files(k),'VariableNamingRule','preserve');
    text_fields = intersect(["Time Stamp","Time Zone","Name"],string(opts.VariableNames));
    opts = setvartype(opts,cellstr(text_fields),'string');
    raw = readtable(files(k),opts);
    req = ["Time Stamp","Time Zone","Name","PTID","Integrated Load"];
    if ~all(ismember(req,string(raw.Properties.VariableNames))) || isempty(raw)
        error('contemporary_import_nyiso_loads:Schema','Missing NYISO source fields or rows.');
    end
    [known,z] = ismember(string(raw.Name),names);
    tz = string(raw.("Time Zone"));
    if any(~known) || any(~ismember(tz,["EST","EDT"]))
        error('contemporary_import_nyiso_loads:Source','Unknown zone or time zone; refusing to infer.');
    end
    % Interpret the file's explicit EST/EDT tag. This preserves fall-back hours.
    local = datetime(raw.("Time Stamp"),'InputFormat','MM/dd/yyyy HH:mm:ss');
    offset = 5*ones(height(raw),1); offset(tz == "EDT") = 4;
    utc = local + hours(offset); utc.Format = "yyyy-MM-dd'T'HH:mm:ss'Z'";
    expected_day = extractBetween(base,1,8);
    if any(string(local,'yyyyMMdd') ~= expected_day)
        error('contemporary_import_nyiso_loads:Date','Rows do not match source file date.');
    end
    source_hash = file_hash(files(k)); n = height(raw);
    stamp = string(utc); zone = letters(z)'; zone = zone(:);
    scenario = "NYISO_" + string(utc,'yyyyMMdd_HHmmss') + "_UTC";
    source_uri = "https://mis.nyiso.com/public/csv/palIntegrated/" + ...
        extractBetween(base,1,6)+"01palIntegrated_csv.zip";
    part = table(scenario,stamp,repmat("load_p",n,1),zone, ...
        double(raw.("Integrated Load")),repmat("MW",n,1), ...
        repmat("actual_mw",n,1),repmat("public_observation",n,1), ...
        repmat(source_uri,n,1),repmat(source_hash,n,1),"load_p:"+zone, ...
        repmat("diagnostic",n,1),repmat("input",n,1),(2:n+1)', ...
        string(raw.("Time Stamp")),tz,repmat(base+ext,n,1), ...
        'VariableNames',{'scenario_id','timestamp_utc','kind','entity_id','value', ...
        'unit','power_scale','provenance_class','source_uri','source_sha256', ...
        'accounting_id','dataset_split','target_use','source_csv_line', ...
        'source_local_timestamp','source_time_zone','source_archive_member'});
    if isempty(observations), observations = part; else, observations = [observations;part]; end %#ok<AGROW>
end
observations = sortrows(observations,{'timestamp_utc','entity_id'});
validate_research_inputs(observations,research_model_contract);
end

function value = file_hash(path)
fid = fopen(path,'rb');
if fid < 0, error('contemporary_import_nyiso_loads:File','Cannot open source file.'); end
cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
bytes = fread(fid,Inf,'*uint8');
digest = java.security.MessageDigest.getInstance('SHA-256');
digest.update(bytes);
value = string(lower(reshape(dec2hex(typecast(digest.digest(),'uint8'),2)',1,[])));
end
