function sha=ny_reference_file_sha256(path)
%NY_REFERENCE_FILE_SHA256 Exact bytes of a frozen replay input.
fid=fopen(path,'rb');assert(fid>=0);closer=onCleanup(@()fclose(fid)); %#ok<NASGU>
bytes=fread(fid,Inf,'*uint8');
digest=java.security.MessageDigest.getInstance('SHA-256');digest.update(bytes);
sha=string(lower(reshape(dec2hex(typecast(digest.digest(),'uint8'),2).',1,[])));
end
