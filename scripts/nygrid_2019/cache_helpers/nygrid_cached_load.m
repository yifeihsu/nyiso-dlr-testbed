function nygrid_cached_load(filename, variable_name, timeStamp)
%NYGRID_CACHED_LOAD Assign a cached released MAT table to the calling function.
% No allocation/reduction calculations are cached. The caller's original
% hourly/day/month filter remains in place after this exact input selection.
value = nygrid_cached_table(filename, char(variable_name), [], timeStamp);
assignin('caller', char(variable_name), value);
end
