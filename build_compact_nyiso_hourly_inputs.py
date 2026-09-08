"""Hourly NYISO inputs for the independent generation reconstruction.

Default extraction exposes only load and external schedules. Internal flow
targets require a previously frozen, verified methodology manifest. The old
point-sample electrical campaign and its source builder remain unchanged.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import zipfile
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'output/compact_ny_2025/electrical_fixed_peak'
OUT = ROOT / 'output/compact_ny_2025/generation_sources/hourly_inputs'
CACHE = ROOT / 'System Matpower Format/NY_Lite/nyiso_public_cache'
PROTOCOL = ROOT / 'output/compact_ny_2025/generation_sources/generation_reconstruction_protocol.json'
ZONES = dict(zip(['WEST', 'GENESE', 'CENTRL', 'NORTH', 'MHK VL', 'CAPITL',
                 'HUD VL', 'MILLWD', 'DUNWOD', 'N.Y.C.', 'LONGIL'], 'ABCDEFGHIJK'))
INTERFACES = dict(zip(['DYSINGER EAST', 'WEST CENTRAL', 'MOSES SOUTH', 'CENTRAL EAST - VC',
                       'TOTAL EAST', 'UPNY CONED', 'SPR/DUN-SOUTH'],
                      ['Dysinger_East', 'West_Central', 'Moses_South', 'Central_East',
                       'Total_East_proxy', 'UPNY_ConEd', 'Dunwoodie_South']))
PRIMARY = {'SCH - HQ - NY': 'HQ', 'SCH - OH - NY': 'ONTARIO',
           'SCH - NE - NY': 'ISONE', 'SCH - PJ - NY': 'PJM'}
EXTERNAL = list(PRIMARY) + ['SCH - HQ_CEDARS', 'SCH - HQ_IMPORT_EXPORT',
                          'SCH - NPX_CSC', 'SCH - NPX_1385', 'SCH - PJM_NEPTUNE',
                          'SCH - PJM_VFT', 'SCH - PJM_HTP']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(path):
    data = path.read_bytes().replace(b'\r\n', b'\n').replace(b'\r', b'\n')
    return hashlib.sha256(data).hexdigest()


def catalog():
    old = pd.read_csv(BASE / 'source_snapshots.csv', keep_default_na=False)
    cols = ['scenario_id', 'vintage', 'timestamp', 'timestamp_utc', 'source_time_zone', 'scale_factor_gamma']
    old = old[cols].copy()
    old['campaign_role'] = 'revisited_diagnostic'
    extra = pd.DataFrame(json.loads(PROTOCOL.read_text())['new_calendar_selected_2025_validation_hours'])
    extra['vintage'] = 2025
    extra['scale_factor_gamma'] = old.loc[old.vintage == 2025, 'scale_factor_gamma'].iloc[0]
    extra['campaign_role'] = 'calendar_selected_unseen_validation'
    d = pd.concat([old, extra], ignore_index=True)
    assert d.scenario_id.is_unique
    d['dataset_split'] = 'source_only_prediction'
    d['default_campaign_interface_fit_allowed'] = False
    d['temporal_policy'] = 'P58C_hour_beginning_P32_forward_hold_hour_mean_max_gap600s'
    d['load_label_convention_basis'] = 'empirical_P58B_P58C_July2025_audit_not_provider_integration_specification'
    d['boundary_q_observed'] = False
    d['zonal_generation_observed'] = False
    d['boundary_coverage_qualified'] = True
    d['boundary_coverage_failure'] = ''
    return d


def source(day, kind):
    archive = CACHE / f'{day[:6]}_{kind}' / f'{day[:6]}01{kind}_csv.zip'
    member = f'{day}{kind}.csv'
    with zipfile.ZipFile(archive) as z:
        matches = [n for n in z.namelist() if Path(n).name == member]
        assert len(matches) == 1, f'Unique archive member required: {member}'
        raw = z.read(matches[0])
    d = pd.read_csv(io.BytesIO(raw))
    d['source_csv_line'] = np.arange(len(d)) + 2
    manifest = dict(source_id=f'NYISO:{kind}:{day}', archive=str(archive.relative_to(ROOT)),
                    archive_sha256=sha(archive), member=matches[0],
                    member_sha256=hashlib.sha256(raw).hexdigest(),
                    source_url=f'https://mis.nyiso.com/public/csv/{kind}/{day[:6]}01{kind}_csv.zip')
    return d, manifest


def local_utc(values, zone):
    """Validate the separately published EST/EDT token; reject DST ambiguity."""
    parsed = pd.DatetimeIndex(pd.to_datetime(values))
    local = parsed.tz_localize('America/New_York', ambiguous='raise', nonexistent='raise')
    assert set(local.strftime('%Z')) == {zone}, 'Published timezone disagrees with civil date'
    return local.tz_convert('UTC')


def hourly_point_mean(block, start, value='Flow (MWH)', max_gap_seconds=600):
    """Forward sample hold on [start,start+1h), with bracket/coverage guards.

    This is an explicit approximation for point samples. Also returns two
    alternate interpolations without using them to choose a better fit.
    """
    b = block.sort_values('utc').copy()
    assert np.isfinite(b[value]).all(), 'Nonfinite public sample'
    # P32 rounds labels to minutes and can publish distinct points under the
    # same label. No revision chronology is provided. Give each timestamp
    # one mean value and retain its entire range as an explicit uncertainty.
    grouped = b.groupby('utc', sort=True)[value].agg(['mean', 'min', 'max', 'size'])
    b = grouped.reset_index().rename(columns={'mean': value})
    t = b.utc.dt.as_unit('ns').astype('int64').to_numpy() / 1e9
    v = b[value].to_numpy(float)
    s, e = start.timestamp(), start.timestamp() + 3600
    assert len(t) >= 2 and t[0] <= s and t[-1] >= e, 'Incomplete hourly bracket'
    grid = np.unique(np.r_[s, t[(t > s) & (t < e)], e])
    left = np.searchsorted(t, grid[:-1], side='right') - 1
    right = np.searchsorted(t, grid[1:], side='left')
    gaps = t[right] - t[left]
    assert np.all((gaps > 0) & (gaps <= max_gap_seconds)), 'Public sample gap exceeds policy'
    dur = np.diff(grid)
    assert abs(dur.sum() - 3600) < 1e-9
    means = dict(actual_hour_mean_mw=float(np.dot(v[left], dur) / 3600),
                 backward_hold_mean_mw=float(np.dot(v[right], dur) / 3600),
                 linear_mean_mw=float(np.dot((np.interp(grid[:-1], t, v) + np.interp(grid[1:], t, v))/2, dur)/3600),
                 interval_count=len(dur), max_sample_gap_seconds=float(gaps.max()),
                 duplicate_timestamp_count=int((b.iloc[np.unique(np.r_[left,right])]['size'] > 1).sum()),
                 max_duplicate_spread_mw=float((b.iloc[np.unique(np.r_[left,right])]['max']-b.iloc[np.unique(np.r_[left,right])]['min']).max()),
                 duplicate_lower_hour_mean_mw=float(np.dot(b['min'].to_numpy()[left], dur)/3600),
                 duplicate_upper_hour_mean_mw=float(np.dot(b['max'].to_numpy()[left], dur)/3600),
                 source_csv_lines=';'.join(map(str, sorted(set(block.loc[block.utc.isin(b.iloc[np.unique(np.r_[left,right])].utc)].source_csv_line)))))
    return means


def verify_freeze(path):
    freeze = json.loads(path.read_text())
    assert freeze['internal_targets_used_to_form_prior'] is False
    assert freeze['protocol_sha256_lf_normalized'] == text_sha(PROTOCOL), 'Protocol changed after freeze'
    assert freeze['files'], 'Empty freeze manifest'
    for item in freeze['files']:
        p = (ROOT / item['path']).resolve()
        assert p.is_relative_to(ROOT.resolve()), 'Frozen path escapes repository'
        digest = text_sha(p) if item['normalization'] == 'LF_text' else sha(p)
        assert digest == item['sha256'], f'Changed frozen file {p}'
    return text_sha(path)


def build(include_targets=False, freeze_manifest=None):
    freeze_hash = ''
    if include_targets:
        assert freeze_manifest is not None, 'Freeze methodology before exposing internal targets'
        freeze_hash = verify_freeze(Path(freeze_manifest))
    OUT.mkdir(parents=True, exist_ok=True)
    scenarios = catalog()
    loads, external, targets, manifests = [], [], [], {}
    for sc in scenarios.to_dict('records'):
        sid, gamma = sc['scenario_id'], sc['scale_factor_gamma']
        start = pd.Timestamp(sc['timestamp_utc'])
        day = start.tz_convert('America/New_York').strftime('%Y%m%d')
        l, lm = source(day, 'palIntegrated')
        # Only selected zonal load records and external interface records are
        # exposed before methodology freeze; internal numeric values unused.
        stamps = pd.to_datetime(l['Time Stamp'])
        selected = l.loc[stamps == pd.Timestamp(sc['timestamp'])].copy()
        assert len(selected) == 11 and set(selected.Name) == set(ZONES)
        assert set(selected['Time Zone']) == {sc['source_time_zone']}
        assert (local_utc(selected['Time Stamp'], sc['source_time_zone']) == start).all()
        values = selected['Integrated Load'].to_numpy(float)
        assert np.isfinite(values).all() and (values >= 0).all() and values.sum() > 0
        sc['actual_total_load_mw'] = values.sum()
        sc['benchmark_total_load_mw'] = values.sum() * gamma
        for row in selected.to_dict('records'):
            p = row['Integrated Load']
            loads.append(dict(scenario_id=sid, zone=ZONES[row['Name']], zone_name=row['Name'],
                              actual_load_mw=p, target_load_mw=p*gamma, load_share=p/values.sum(),
                              source_csv_line=row['source_csv_line'], source_id=lm['source_id']))
        f, fm = source(day, 'ExternalLimitsFlows')
        names = EXTERNAL + (list(INTERFACES) if include_targets else [])
        f = f.loc[f['Interface Name'].isin(names)].copy()
        f['utc'] = local_utc(f.Timestamp, sc['source_time_zone'])
        for name in names:
            block = f.loc[f['Interface Name'] == name]
            assert block['Point ID'].nunique() == 1, f'Missing/ambiguous public identity: {name}'
            try:
                avg = hourly_point_mean(block, start)
                avg.update(coverage_qualified=True, coverage_failure='')
            except AssertionError as err:
                if str(err) not in ['Public sample gap exceeds policy', 'Incomplete hourly bracket']:
                    raise
                avg = dict(actual_hour_mean_mw=np.nan, backward_hold_mean_mw=np.nan, linear_mean_mw=np.nan,
                           coverage_qualified=False, coverage_failure=str(err))
                if name in EXTERNAL:
                    scenarios.loc[scenarios.scenario_id == sid, 'boundary_coverage_qualified'] = False
                    scenarios.loc[scenarios.scenario_id == sid, 'boundary_coverage_failure'] = str(err)
            item = dict(scenario_id=sid, public_interface_name=name,
                        point_id=int(block['Point ID'].iloc[0]), source_id=fm['source_id'], **avg)
            if name in EXTERNAL:
                item.update(external_region=PRIMARY.get(name, name),
                            default_primary_scope=name in PRIMARY,
                            default_channel_include=name != 'SCH - HQ_IMPORT_EXPORT',
                            actual_import_mw=avg['actual_hour_mean_mw'],
                            target_import_mw=avg['actual_hour_mean_mw'] * gamma)
                external.append(item)
            else:
                item.update(interface_name=INTERFACES[name], actual_flow_mw=avg['actual_hour_mean_mw'],
                            target_flow_mw=avg['actual_hour_mean_mw']*gamma,
                            used_in_prior=False, used_in_optimizer=False, methodology_freeze_sha256=freeze_hash)
                targets.append(item)
        if not include_targets:
            for name, model in INTERFACES.items():
                targets.append(dict(scenario_id=sid, public_interface_name=name, interface_name=model,
                                    target_flow_mw=np.nan, actual_flow_mw=np.nan,
                                    used_in_prior=False, used_in_optimizer=False))
        for m in [lm, fm]:
            manifests[m['source_id']] = m
        scenarios.loc[scenarios.scenario_id == sid, 'actual_total_load_mw'] = values.sum()
        scenarios.loc[scenarios.scenario_id == sid, 'benchmark_total_load_mw'] = values.sum() * gamma
    ext = pd.DataFrame(external)
    data = dict(snapshots=scenarios, loads=pd.DataFrame(loads), external_records=ext,
                boundaries=ext.loc[ext.default_primary_scope], interfaces=pd.DataFrame(targets),
                source_manifest=pd.DataFrame(manifests.values()))
    prefix = 'scored_' if include_targets else ''
    for name, table in data.items():
        table.to_csv(OUT / f'{prefix}{name}.csv', index=False, lineterminator='\n')
    status = dict(scenario_count=len(scenarios), hour_convention='hour_beginning',
                  boundary_qualified_scenarios=int(scenarios.boundary_coverage_qualified.sum()),
                  p32_mean_policy='forward_sample_hold', max_sample_gap_seconds=600,
                  duplicate_timestamp_policy='mean_with_timestamp_range_and_hourly_bounds_retained',
                  p32_header='Flow (MWH)', p32_unit_interpretation='published_interface_power_MW_no_energy_conversion',
                  internal_targets_extracted=include_targets, internal_targets_used_in_optimizer=False,
                  methodology_freeze_sha256=freeze_hash, protocol_sha256=sha(PROTOCOL))
    (OUT / f'{prefix}extraction_manifest.json').write_bytes((json.dumps(status, indent=2)+'\n').encode())
    print(json.dumps(status, indent=2))
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--include-targets', action='store_true')
    parser.add_argument('--freeze-manifest', type=Path)
    args = parser.parse_args()
    build(args.include_targets, args.freeze_manifest)
