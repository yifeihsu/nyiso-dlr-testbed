function ny_lite_writetable_lf(tbl, filename)
%NY_LITE_WRITETABLE_LF Write a CSV with repository-stable LF endings.

writetable(tbl, filename);

fid = fopen(filename, 'rb');
if fid < 0
    error('ny_lite_writetable_lf:ReadOpen', ...
        'Could not reopen generated table for reading: %s', filename);
end
read_cleanup = onCleanup(@() fclose(fid));
bytes = fread(fid, Inf, '*uint8')';
clear read_cleanup

is_crlf = bytes == uint8(13) & ...
    [bytes(2:end) uint8(0)] == uint8(10);
bytes(is_crlf) = [];

fid = fopen(filename, 'wb');
if fid < 0
    error('ny_lite_writetable_lf:WriteOpen', ...
        'Could not reopen generated table for writing: %s', filename);
end
write_cleanup = onCleanup(@() fclose(fid));
written = fwrite(fid, bytes, 'uint8');
if written ~= numel(bytes)
    error('ny_lite_writetable_lf:ShortWrite', ...
        'Generated table write was incomplete: %s', filename);
end
clear write_cleanup
end
