function value = nygrid_cached_import(reader, filename, timeStamp)
%NYGRID_CACHED_IMPORT Cache the exact result of an upstream CSV reader.
if nargin < 3, timeStamp = []; end
value = nygrid_cached_table(filename, '', reader, timeStamp);
end
