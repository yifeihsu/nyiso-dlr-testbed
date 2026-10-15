function digest=nylatest_operator_fingerprint(c)
%COMPACT_AC_OPERATOR_FINGERPRINT Bind the immutable reduction/recovery cache.
% Hash sparse coordinates as well as real and imaginary values. Metadata that
% labels recovered conductors is protected alongside the Newton operators.
engine=java.security.MessageDigest.getInstance('SHA-256');
chunks={};
fields={'Yred','voltage_lift','Yfull','Yf_full','Yt_full','Yseries_full', ...
    'YfL','YtL','YseriesL','retained_bus_ids','anchor_bus_ids','promoted_bus_ids', ...
    'full_bus_ids','retained_full_rows','eliminated_full_rows', ...
    'from_current_base_A','to_current_base_A','branch_from_bus','branch_to_bus'};
if isfield(c,'branch_parent_row'),fields{end+1}='branch_parent_row';end
for n=1:numel(fields)
    chunks{end+1}=int8(fields{n}(:)); %#ok<AGROW>
    a=double(c.(fields{n}));shape=double(size(a));
    chunks{end+1}=typecast(shape(:),'int8'); %#ok<AGROW>
    if issparse(a)
        [i,j,v]=find(a);parts={double(1),double(i),double(j),real(v),imag(v)};
    else
        parts={double(0),real(a(:)),imag(a(:))};
    end
    for q=1:numel(parts)
        if ~isempty(parts{q})
            part_bytes=typecast(parts{q}(:),'int8');
            chunks{end+1}=part_bytes(:); %#ok<AGROW>
        end
    end
end
labels={c.source_fingerprint};
if isfield(c,'branch_keys'),labels=[labels;cellstr(string(c.branch_keys(:)))];end
for n=1:numel(labels)
    bytes=unicode2native(labels{n},'UTF-8');count=double(numel(bytes));
    count_bytes=typecast(count,'int8');
    chunks{end+1}=count_bytes(:);chunks{end+1}=typecast(bytes(:),'int8'); %#ok<AGROW>
end
% One Java update of exactly the same ordered bytes avoids thousands of
% MATLAB/Java transitions per PF without weakening the cache integrity check.
engine.update(vertcat(chunks{:}));
raw=typecast(engine.digest(),'uint8');digest=lower(reshape(dec2hex(raw,2)',1,[]));
end
