function fingerprint = s14_network_fingerprint(source)
%S14_NETWORK_FINGERPRINT Hash topology, all branch parameters and bus shunts.
% Operating injections and solved voltages intentionally do not affect this
% hash; changing them is a scenario update, not network recalibration.
payload = sprintf('%.17g,', [source.baseMVA; size(source.bus,1); ...
    reshape(source.bus(:,[1 5 6 10]),[],1); size(source.branch,1); ...
    reshape(source.branch(:,1:13),[],1)]);
digest = java.security.MessageDigest.getInstance('SHA-256');
digest.update(uint8(unicode2native(payload,'UTF-8')));
fingerprint = lower(reshape(dec2hex(typecast(digest.digest(),'uint8'),2).',1,[]));
end
