function ts = nyiso_public_timestamp(value)
%NYISO_PUBLIC_TIMESTAMP Parse public scenario timestamp values.

if isdatetime(value)
    ts = value;
    return;
end
if iscell(value)
    value = value{1};
end
value = char(string(value));
formats = {'yyyy-MM-dd HH:mm:ss','yyyy-MM-dd HH:mm', ...
    'MM/dd/yyyy HH:mm:ss','MM/dd/yyyy HH:mm'};
last_err = [];
for k = 1:numel(formats)
    try
        ts = datetime(value, 'InputFormat', formats{k});
        return;
    catch ME
        last_err = ME;
    end
end
rethrow(last_err);
end
