function fingerprint = ny_lite_operating_point_fingerprint(mpc)
%NY_LITE_OPERATING_POINT_FINGERPRINT Hash pre-power-flow operating inputs.
%   Compute before runpf so solved slack/Q/flow values do not alter identity.
BUS_COL=[1 2 3 4 5 6 7 10 11 12 13];
GEN_COL=1:min(10,size(mpc.gen,2));
BR_COL=1:min(13,size(mpc.branch,2));
parts={ny_lite_case_fingerprint(mpc),mpc.bus(:,BUS_COL), ...
    mpc.gen(:,GEN_COL),mpc.branch(:,BR_COL)};
fingerprint=ny_lite_hash_parts(parts);
end
