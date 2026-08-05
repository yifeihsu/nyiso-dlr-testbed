function fingerprint = ny_lite_case_fingerprint(mpc)
%NY_LITE_CASE_FINGERPRINT Hash structural/input limits, excluding solved state.
BUS_COL=[1 2 5 6 7 10 11 12 13];
GEN_COL=[1 4 5 7 8 9 10];
BR_COL=1:min(13,size(mpc.branch,2));
parts={mpc.baseMVA,mpc.bus(:,BUS_COL),mpc.gen(:,GEN_COL),mpc.branch(:,BR_COL)};
if isfield(mpc,'gencost'), parts{end+1}=mpc.gencost; end
fingerprint=ny_lite_hash_parts(parts);
end
