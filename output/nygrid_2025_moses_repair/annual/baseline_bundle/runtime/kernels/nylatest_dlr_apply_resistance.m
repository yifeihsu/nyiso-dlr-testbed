function mpc=nylatest_dlr_apply_resistance(mpc,segments,conductors,temperature_c)
%AC_DLR_APPLY_RESISTANCE Rebuild R from immutable per-segment physical data.
% Sequential line sections add resistance; each segment declares its own
% integer circuit and bundle multiplicity. Updates never compound R.
n=height(segments);if isscalar(temperature_c),temperature_c=repmat(temperature_c,n,1);end
assert(numel(temperature_c)==n&&all(isfinite(temperature_c)),'acDLR:Temperature','Supply one temperature per segment.');
[ok,ci]=ismember(string(segments.catalog_id),string(conductors.catalog_id));assert(all(ok));
rows=unique(segments.branch_row);
for k=1:numel(rows)
    use=find(segments.branch_row==rows(k));ohms=0;
    for j=use'
        assert(temperature_c(j)>=segments.temperature_min_c(j)&&temperature_c(j)<=segments.temperature_max_c(j), ...
            'acDLR:TemperatureRange','Thermal state exceeds the declared study range.');
        rr=nylatest_conductor_resistance(conductors(ci(j),:),temperature_c(j));
        ohms=ohms+rr*segments.segment_length_m(j)/(segments.circuits(j)*segments.bundle_count(j));
    end
    kv=segments.base_kv(use(1));mpc.branch(rows(k),3)=ohms/(kv^2/mpc.baseMVA);
end
end
