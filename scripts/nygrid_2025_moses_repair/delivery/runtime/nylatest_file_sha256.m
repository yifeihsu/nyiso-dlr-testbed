function digest=nylatest_file_sha256(path)
fid=fopen(path,'rb');assert(fid>=0,'nylatest:File','Cannot read the requested model file.');clean=onCleanup(@()fclose(fid));
e=java.security.MessageDigest.getInstance('SHA-256');
while ~feof(fid),b=fread(fid,1048576,'*uint8');if ~isempty(b),e.update(typecast(b,'int8'));end,end
digest=lower(reshape(dec2hex(typecast(e.digest(),'uint8'),2)',1,[]));
end
