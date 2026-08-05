function hex = ny_lite_hash_parts(parts)
%NY_LITE_HASH_PARTS Deterministic MD5 hash for numeric/text input parts.
md = java.security.MessageDigest.getInstance('MD5');
for k=1:numel(parts)
    value=parts{k};
    if isnumeric(value) || islogical(value)
        token=sprintf('%.17g,',double(value(:)));
    else
        token=char(value);
    end
    md.update(uint8(token));
    md.update(uint8('|'));
end
raw=typecast(md.digest(),'uint8');
hex=lower(reshape(dec2hex(raw,2).',1,[]));
end
