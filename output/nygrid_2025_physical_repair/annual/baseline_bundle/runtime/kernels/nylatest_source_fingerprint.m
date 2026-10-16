function digest=nylatest_source_fingerprint(m,retained_ids)
% Numerical source contract, independent of labels and transient timing data.
engine=java.security.MessageDigest.getInstance('SHA-256');
parts={double(m.baseMVA),double(m.bus),double(m.gen),double(m.branch(:,1:13)),double(retained_ids(:))};
if isfield(m,'dcline'),parts{end+1}=double(m.dcline);end
for k=1:numel(parts)
    a=parts{k};shape=double(size(a));
    engine.update(typecast(shape(:),'int8'));
    if ~isempty(a),engine.update(typecast(a(:),'int8'));end
end
raw=typecast(engine.digest(),'uint8');digest=lower(reshape(dec2hex(raw,2)',1,[]));
end
