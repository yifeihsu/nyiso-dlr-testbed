"""Reserve named generator estimates as subsets of the zonal source priors."""
import hashlib
import json
import numpy as np
import pandas as pd
from build_compact_combined_generation_prior import ROOT, SOURCES, OUT, truth


def named_subsets(epa, renewable, zonal, reconciliation):
    renewable = renewable.rename(columns={'model_generator_key':'generator_key'})
    rows = []
    for sid, z in zonal.loc[zonal.vintage == 2025].groupby('scenario_id', sort=False):
        gamma = z.scale_factor_gamma.iloc[0]
        summary = reconciliation.loc[reconciliation.scenario_id == sid]
        assert len(summary) == 1
        factor = summary.statewide_total_reconciliation_factor.iloc[0]
        c = epa.loc[(epa.scenario_id == sid) & (epa.facility_id == 57185)]
        assert len(c) == 3 and set(c.unit_id) == {'U001','U002','U003'}, 'Cricket Valley unit identity changed'
        assert set(c.zone) == {'G'} and truth(c.grid_fossil_share_eligible).all()
        assert set(c.timestamp_utc_requested) == set(z.timestamp_utc_requested), 'Named fossil timestamp mismatch'
        # Reported offline blank is an inferred zero-output PRIOR, still not
        # relabeled an observed zero in the retained source unit table.
        values = c.gross_clock_hour_average_mw.copy()
        offline_blank = values.isna() & (c.operating_time_hours == 0)
        values.loc[offline_blank] = 0
        qualified = truth(z.coverage_qualified).all() and np.isfinite(values).all() and np.isfinite(factor)
        public = values.sum()*factor if qualified else np.nan
        cp = dict(scenario_id=sid, generator_key='NY2025:GEN:CRICKET_VALLEY:PV73', zone='G',
                  prior_public_mw=public, prior_benchmark_mw=public*gamma, coverage_qualified=bool(qualified),
                  source_method='EPA_Cricket_three_clock_hour_units_times_statewide_fossil_total_reconciliation',
                  observed_plant_net_generation=False, subset_of_zone_prior=True,
                  inferred_offline_zero_prior_units=int(offline_blank.sum()))
        w = renewable.loc[(renewable.scenario_id == sid) & (renewable.generator_key == 'NY2025:GEN:SOUTH_FORK:K9003')]
        assert len(w) == 1 and w.zone.iloc[0] == 'K'
        assert set(w.timestamp_utc_requested) == set(z.timestamp_utc_requested), 'Named renewable timestamp mismatch'
        assert truth(w.subset_of_zone_fuel_prior).all()
        assert np.isclose(w.prior_benchmark_mw.iloc[0], w.prior_public_mw.iloc[0]*gamma, atol=1e-7, rtol=0)
        assert w.prior_public_mw.iloc[0] <= w.parent_zone_fuel_prior_public_mw.iloc[0]+1e-7
        wp = dict(scenario_id=sid, generator_key='NY2025:GEN:SOUTH_FORK:K9003', zone='K',
                  prior_public_mw=w.prior_public_mw.iloc[0], prior_benchmark_mw=w.prior_benchmark_mw.iloc[0],
                  coverage_qualified=bool(truth(w.coverage_qualified).all()),
                  source_method='P63_statewide_wind_times_active_EIA_SouthFork_capacity_share',
                  observed_plant_net_generation=False, subset_of_zone_prior=True, inferred_offline_zero_prior_units=0)
        for record in [cp, wp]:
            target = z.loc[z.zone == record['zone']].iloc[0]
            if record['coverage_qualified']:
                assert np.isfinite(record['prior_public_mw']) and record['prior_public_mw'] >= 0
                assert record['prior_public_mw'] <= target.prior_public_mw+1e-7, 'Named estimate exceeds its zonal total'
                if record['zone'] == 'G':
                    assert record['prior_public_mw'] <= target.fossil_prior_public_mw+1e-7
            rows.append(record)
    d = pd.DataFrame(rows)
    assert not d.duplicated(['scenario_id','generator_key']).any()
    return d


def main():
    paths = [SOURCES/'epa/epa_generation_hourly.csv', SOURCES/'nonfossil/named_renewable_priors.csv',
             OUT/'zonal_generation_priors.csv', OUT/'statewide_reconciliation.csv']
    frames = [pd.read_csv(p, dtype={'unit_id':str}) for p in paths]
    d = named_subsets(*frames)
    d.to_csv(OUT/'named_generator_priors.csv',index=False,lineterminator='\n')
    manifest = dict(subsets_of_zonal_prior=True, additional_generation_added=False,
                    plant_net_dispatch_observed=False, internal_interface_targets_used=False,
                    sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths])
    (OUT/'named_source_manifest.json').write_bytes((json.dumps(manifest,indent=2)+'\n').encode())
    print(d.to_string(index=False))


if __name__ == '__main__':
    main()
