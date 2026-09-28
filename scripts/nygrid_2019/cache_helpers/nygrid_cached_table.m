function value = nygrid_cached_table(filename, variable_name, reader, timeStamp)
%NYGRID_CACHED_TABLE Immutable process-local released-data cache.
% Clear this function before changing source files. All cached inputs are
% pinned by the generated execution manifest. No numerical model state or
% network-reduction result is cached.
persistent entries
if isempty(entries), entries = containers.Map('KeyType','char','ValueType','any'); end
path = char(java.io.File(char(filename)).getCanonicalPath());
if isempty(reader)
    key = [path '::MAT::' variable_name];
else
    details = functions(reader);
    key = [path '::CSV::' details.file '::' func2str(reader)];
end
if ~isKey(entries,key)
    if isempty(reader)
        loaded = load(path,variable_name);
        data = loaded.(variable_name);
    else
        data = reader(path);
    end
    entry = struct('data',data,'rows',[],'times',[]);
    if istable(data) && ismember('TimeStamp',data.Properties.VariableNames)
        assert(isdatetime(data.TimeStamp),'nygrid_cache:TimeType','Expected released datetime timestamps.');
        [times,~,groups] = unique(data.TimeStamp);
        valid = ~isnat(times);
        serial = datenum(times(valid));
        assert(numel(unique(serial))==numel(serial),'nygrid_cache:TimeCollision','Timestamp indexing would merge distinct source timestamps.');
        row_groups = accumarray(groups,(1:height(data))',[numel(times),1],@(x){sort(x)});
        entry.rows = containers.Map(serial,row_groups(valid));
        entry.times = data.TimeStamp;
    end
    entries(key) = entry;
end
entry = entries(key);
value = entry.data;
if isempty(timeStamp) || isempty(entry.rows), return; end
assert(isscalar(timeStamp)&&isdatetime(timeStamp),'nygrid_cache:Query','Expected one released-model datetime.');
query = timeStamp;
if contains(path,'nuclearGenDaily_')
    query = dateshift(query,'start','day');
elseif contains(path,'hydroGenMonthly_')
    query = dateshift(query,'start','month');
end
if isnat(query)
    value = value([],:);
    return;
end
serial = datenum(query);
if isKey(entry.rows,serial)
    rows = entry.rows(serial);
    % Preserve datetime equality semantics even if the caller supplies a
    % different timezone or a subsecond value sharing a serial representation.
    rows = rows(entry.times(rows)==query);
    value = value(rows,:);
else
    value = value([],:);
end
end
