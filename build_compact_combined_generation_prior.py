"""Combine independent public sources into estimated zonal net generation.

EPA clock-hour gross output supplies geographic fossil shares; NYISO's
statewide combined fossil total supplies their net-production scale. This
is a total reconciliation, not a measured plant-level gross-to-net factor.
No load, boundary, model dispatch, or internal-interface values form priors.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / 'output/compact_ny_2025/generation_sources'
OUT = SOURCES / 'combined'
FOSSIL = {'Dual Fuel', 'Natural Gas', 'Other Fossil Fuels'}
NONFOSSIL = {'Nuclear', 'Hydro', 'Wind', 'Other Renewables'}
ZONES = list('ABCDEFGHIJK')


def truth(x):
    text = x.astype(str).str.lower()
    assert text.isin(['true', 'false', '1', '0', '1.0', '0.0']).all(), 'Missing or invalid qualification flag'
    return text.isin(['true', '1', '1.0'])


def combine(epa, nonfossil, statewide):
    assert len(epa) and len(nonfossil) and len(statewide), 'Empty generation source'
    ids = pd.to_numeric(epa.facility_id, errors='coerce')
    assert np.isfinite(ids).all() and (ids > 0).all() and (ids == np.floor(ids)).all(), 'Invalid EPA facility identity'
    units = epa.unit_id.astype('string')
    assert units.notna().all() and (units.str.len() > 0).all() and (units == units.str.strip()).all(), 'Invalid EPA unit identity'
    epa = epa.copy()
    epa['facility_id'] = ids.astype('int64')
    assert not epa.duplicated(['scenario_id', 'facility_id', 'unit_id']).any(), 'Duplicate EPA unit-hour'
    assert set(nonfossil.fuel_category) == NONFOSSIL
    assert not nonfossil.duplicated(['scenario_id', 'zone', 'fuel_category']).any()
    assert set(epa.scenario_id) == set(nonfossil.scenario_id) == set(statewide.scenario_id)
    statewide = statewide.loc[statewide.window_policy == 'hour_beginning'].copy()
    assert not statewide.duplicated(['scenario_id', 'fuel_category']).any()
    totals, zones = [], []
    for sid, nf in nonfossil.groupby('scenario_id', sort=False):
        ef = epa.loc[epa.scenario_id == sid]
        sf = statewide.loc[statewide.scenario_id == sid]
        assert set(sf.fuel_category) == FOSSIL | NONFOSSIL
        assert len(nf) == 44 and set(nf.zone) == set(ZONES)
        assert set(nf.window_policy) == {'hour_beginning'}
        for field in ['vintage', 'timestamp_local_requested', 'timestamp_utc_requested']:
            values = pd.concat([ef[field], nf[field], sf[field]], ignore_index=True)
            assert values.notna().all() and values.astype(str).nunique() == 1, 'Generation source timestamp/vintage mismatch: ' + field
        utc = pd.to_datetime(nf.timestamp_utc_requested.iloc[0], utc=True)
        local = pd.to_datetime(nf.timestamp_local_requested.iloc[0])
        assert utc.tz_convert('America/New_York').tz_localize(None) == local, 'Local and UTC source timestamps disagree'
        assert (pd.to_datetime(ef.interval_start_utc, utc=True) == utc).all(), 'EPA interval does not begin at the registered UTC hour'
        assert (pd.to_datetime(ef.interval_end_utc, utc=True) == utc + pd.Timedelta(hours=1)).all(), 'EPA interval is not one clock hour'
        assert (pd.to_datetime(sf.window_start_local) == local).all() and (pd.to_datetime(sf.window_end_local) == local + pd.Timedelta(hours=1)).all(), 'P63 interval does not match the registered hour'
        gammas = np.unique(np.r_[ef.scale_factor_gamma, nf.scale_factor_gamma, sf.scale_factor_gamma])
        assert np.isfinite(gammas).all() and (gammas > 0).all(), 'Invalid MW scale gamma'
        assert np.allclose(gammas, gammas[0], rtol=0, atol=1e-12)
        gamma = gammas[0]
        eligible = ef.loc[truth(ef.grid_fossil_share_eligible)]
        known = eligible.loc[eligible.gross_clock_hour_average_mw.notna()]
        assert np.isfinite(known.gross_clock_hour_average_mw).all()
        assert (known.gross_clock_hour_average_mw >= 0).all()
        mapped = known.loc[known.zone.isin(ZONES)]
        unmapped_mw = known.loc[~known.zone.isin(ZONES), 'gross_clock_hour_average_mw'].sum()
        gross = mapped.gross_clock_hour_average_mw.sum()
        p63fossil = sf.loc[sf.fuel_category.isin(FOSSIL), 'duration_weighted_generation_mw'].sum(min_count=3)
        qualified = bool(truth(sf.coverage_qualified).all() and truth(nf.coverage_qualified).all()
                         and np.isfinite(p63fossil) and p63fossil >= 0 and gross > 0 and unmapped_mw == 0)
        if qualified:
            assert np.isfinite(nf.prior_public_mw).all() and (nf.prior_public_mw >= 0).all()
            assert np.isfinite(sf.duration_weighted_generation_mw).all() and (sf.duration_weighted_generation_mw >= 0).all(), 'Invalid statewide fuel production'
            assert np.allclose(nf.prior_benchmark_mw, nf.prior_public_mw*gamma, rtol=0, atol=1e-8), 'Nonfossil benchmark MW applies gamma incorrectly'
            for fuel in NONFOSSIL:
                estimated = nf.loc[nf.fuel_category == fuel, 'prior_public_mw'].sum()
                observed = sf.loc[sf.fuel_category == fuel, 'duration_weighted_generation_mw'].iloc[0]
                assert abs(estimated-observed) < 1e-7, 'Nonfossil fuel total does not conserve P63: ' + fuel
        # Missing reports remain missing. The statewide normalization supplies
        # an estimate of uncovered net output using covered unit geography.
        for z in ZONES:
            g = mapped.loc[mapped.zone == z, 'gross_clock_hour_average_mw'].sum()
            nonf = nf.loc[nf.zone == z, 'prior_public_mw'].sum(min_count=4)
            fp = p63fossil*g/gross if qualified else np.nan
            prior = fp + nonf if qualified else np.nan
            zones.append(dict(scenario_id=sid, zone=z, prior_public_mw=prior, prior_benchmark_mw=prior*gamma,
                              vintage=int(nf.vintage.iloc[0]), timestamp_local_requested=nf.timestamp_local_requested.iloc[0],
                              timestamp_utc_requested=nf.timestamp_utc_requested.iloc[0],
                              coverage_qualified=qualified, scale_factor_gamma=gamma,
                              epa_covered_grid_gross_mw=g, fossil_geographic_share=g/gross if gross>0 else np.nan,
                              fossil_prior_public_mw=fp, nonfossil_prior_public_mw=nonf,
                              source_method='EPA_grid_gross_share_times_P63_combined_fossil_plus_NRC_EIA_nonfossil',
                              zonal_generation_observed=False, source_net_generation_complete=False,
                              internal_interfaces_used_in_prior=False))
        estimated_total = sum(x['prior_public_mw'] for x in zones[-11:])
        p63total = sf.duration_weighted_generation_mw.sum(min_count=7)
        err = estimated_total-p63total if qualified else np.nan
        assert not qualified or abs(err)<1e-7, 'Zonal total does not conserve statewide observed production'
        excluded = ef.loc[~truth(ef.grid_fossil_share_eligible)]
        totals.append(dict(scenario_id=sid, coverage_qualified=qualified,
                           p63_combined_fossil_mw=p63fossil, epa_covered_grid_gross_mw=gross,
                           statewide_total_reconciliation_factor=p63fossil/gross if gross>0 else np.nan,
                           eligible_unmapped_present_gross_mw=unmapped_mw,
                           excluded_reported_gross_mw=excluded.gross_clock_hour_average_mw.sum(min_count=1),
                           eligible_missing_gross_rows=int(eligible.gross_clock_hour_average_mw.isna().sum()),
                           p63_total_generation_mw=p63total, estimated_total_generation_mw=estimated_total,
                           statewide_conservation_error_mw=err,
                           reconciliation_factor_is_plant_net_conversion=False,
                           geographic_coverage_complete=False, internal_interfaces_used_in_prior=False))
    return pd.DataFrame(zones), pd.DataFrame(totals)


def main():
    paths = [SOURCES/'epa/epa_generation_hourly.csv', SOURCES/'nonfossil/zonal_nonfossil_priors.csv',
             SOURCES/'nonfossil/statewide_fuelmix_hourly.csv']
    z, s = combine(*(pd.read_csv(p, dtype={'unit_id': str}) for p in paths))
    OUT.mkdir(parents=True, exist_ok=True)
    z.to_csv(OUT/'zonal_generation_priors.csv', index=False, lineterminator='\n')
    s.to_csv(OUT/'statewide_reconciliation.csv', index=False, lineterminator='\n')
    manifest = dict(method='independent_zonal_generation_reconstruction_v1',
                    internal_targets_used_to_form_prior=False, observed_zonal_generation=False,
                    geographic_reconciliation='covered_EPA_combined_fossil_shares_normalized_to_P63_net_total',
                    missing_report_policy='missing_gross_never_measured_zero; covered_unit_geography_estimates_uncovered_net_output',
                    gross_net_policy='no_single_plant_net_conversion_is_claimed',
                    hourly_policy='EPA_clock_hour;P63_backward_sample_hold_over_same_hour_beginning_window',
                    sources=[dict(path=str(p.relative_to(ROOT)), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths])
    (OUT/'source_manifest.json').write_bytes((json.dumps(manifest, indent=2)+'\n').encode())
    print(s.to_string(index=False))


if __name__ == '__main__':
    main()
