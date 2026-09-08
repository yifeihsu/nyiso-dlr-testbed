"""Check P58C hour labels against independently posted P58B load samples.

Uses all July2025 zones/hours with full adjacent sample coverage. It tests
timestamp interpretation using load data only, never interface-flow targets.
This empirical comparison corroborates an interval convention; it does not
assert that our interpolation reproduces NYISO's unpublished integration.
"""
from pathlib import Path
import hashlib
import io
import json
import zipfile
import numpy as np
import pandas as pd
import urllib.request

ROOT = Path(__file__).resolve().parent
FOLDER = ROOT / 'output/compact_ny_2025/generation_sources/time_alignment'
CACHE = ROOT / 'tmp/nyiso_time_audit'


def load_zip(path, suffix, value):
    with zipfile.ZipFile(path) as z:
        pieces = [pd.read_csv(io.BytesIO(z.read(n))) for n in z.namelist() if n.endswith(suffix)]
    if not pieces:
        raise ValueError('No matching daily CSV members in source archive.')
    d = pd.concat(pieces, ignore_index=True)
    assert set(d['Time Zone']) == {'EDT'}, 'This audit is limited to July2025 EDT.'
    d['utc'] = pd.to_datetime(d['Time Stamp']).dt.tz_localize('America/New_York').dt.tz_convert('UTC')
    if not np.isfinite(pd.to_numeric(d[value], errors='raise')).all():
        raise ValueError('Nonfinite source load value.')
    return d


def integrate_hourly_samples(seconds, values, max_gap_seconds=600):
    """Time-weighted [hour start, hour end) averages without extrapolation.

    ``seconds`` is strictly increasing UTC Unix time. A complete source
    interval is rejected if its bracketing samples are more than max_gap
    apart, even when only a small part of that interval overlaps an hour.
    All three conventions use identical coverage. Incomplete averages are
    NaN and cannot accidentally enter the label comparison.
    """
    t = np.asarray(seconds, dtype=float)
    v = np.asarray(values, dtype=float)
    if (t.ndim != 1 or v.ndim != 1 or len(t) != len(v) or len(t) < 2
            or not np.isfinite(t).all() or not np.isfinite(v).all()
            or not np.all(np.diff(t) > 0)):
        raise ValueError('At least two finite, unique, increasing paired samples are required.')
    if not np.isfinite(max_gap_seconds) or max_gap_seconds <= 0:
        raise ValueError('max_gap_seconds must be finite and positive.')
    hours = np.arange(np.ceil(t[0] / 3600) * 3600,
                      np.floor(t[-1] / 3600) * 3600 + 1, 3600)
    grid = np.unique(np.r_[t, hours])
    left = np.searchsorted(t, grid[:-1], side='right') - 1
    duration = np.diff(grid)
    gap = t[left + 1] - t[left]
    valid = gap <= max_gap_seconds
    bins = np.floor(grid[:-1] / 3600) * 3600
    linear_start = v[left] + (v[left + 1] - v[left]) * (grid[:-1] - t[left]) / gap
    linear_end = v[left] + (v[left + 1] - v[left]) * (grid[1:] - t[left]) / gap
    segments = pd.DataFrame({'second': bins, 'covered_seconds': duration * valid,
                             'source_span_seconds': duration, 'source_gap_seconds': gap,
                             'rejected_gap_seconds': duration * ~valid})
    result = segments.groupby('second').agg(
        coverage_seconds=('covered_seconds', 'sum'),
        source_span_seconds=('source_span_seconds', 'sum'),
        rejected_gap_seconds=('rejected_gap_seconds', 'sum'),
        maximum_bracketing_gap_seconds=('source_gap_seconds', 'max'))
    result['complete_coverage'] = np.isclose(result.coverage_seconds, 3600, atol=1e-8, rtol=0)
    conventions = {'forward_sample_hold': v[left], 'backward_sample_hold': v[left + 1],
                   'linear_between_samples': (linear_start + linear_end) / 2}
    for method, point_values in conventions.items():
        integral = pd.Series(point_values * duration * valid, index=bins).groupby(level=0).sum()
        result[method] = (integral / 3600).where(result.complete_coverage)
    result.index.name = 'hour_start_unix_seconds'
    return result.reset_index()


def main():
    FOLDER.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    url = 'https://mis.nyiso.com/public/csv/pal/20250701pal_csv.zip'
    pal = CACHE / '20250701pal_csv.zip'
    if not pal.exists():
        with urllib.request.urlopen(url, timeout=90) as response:
            pal.write_bytes(response.read())
    integrated = ROOT / 'System Matpower Format/NY_Lite/nyiso_public_cache/202507_palIntegrated/20250701palIntegrated_csv.zip'
    samples = load_zip(pal, 'pal.csv', 'Load')
    observed = load_zip(integrated, 'palIntegrated.csv', 'Integrated Load')
    assert observed.groupby(['PTID', 'utc'])['Integrated Load'].nunique().max() == 1
    observed = observed.drop_duplicates(['PTID', 'utc']).set_index(['PTID', 'utc'])['Integrated Load']
    rows = []
    coverage_rows = []
    for ptid, block in samples.groupby('PTID'):
        block = block.sort_values('utc')
        # Multiple distinct values at one timestamp need a revision policy.
        assert block.groupby('utc').Load.nunique().max() == 1
        block = block.drop_duplicates('utc')
        t = block.utc.dt.as_unit('ns').astype('int64').to_numpy() / 1e9
        v = block.Load.to_numpy()
        hours = integrate_hourly_samples(t, v, max_gap_seconds=600)
        coverage = hours[['hour_start_unix_seconds', 'coverage_seconds', 'source_span_seconds',
                          'rejected_gap_seconds', 'maximum_bracketing_gap_seconds', 'complete_coverage']].copy()
        coverage['ptid'] = ptid
        coverage['hour_start_utc'] = pd.to_datetime(coverage.hour_start_unix_seconds, unit='s', utc=True)
        coverage_rows.append(coverage)
        for method in ['forward_sample_hold', 'backward_sample_hold', 'linear_between_samples']:
            for hour in hours.itertuples(index=False):
                if not hour.complete_coverage:
                    continue
                second = hour.hour_start_unix_seconds
                avg = getattr(hour, method)
                for meaning, shift in [('hour_beginning', 0), ('hour_ending', 3600)]:
                    stamp = pd.Timestamp(second + shift, unit='s', tz='UTC')
                    if (ptid, stamp) not in observed.index:
                        continue
                    value = observed.loc[(ptid, stamp)]
                    rows.append(dict(ptid=ptid, source_label_utc=stamp.isoformat(),
                                     label_interpretation=meaning, integration_method=method,
                                     coverage_seconds=hour.coverage_seconds,
                                     maximum_bracketing_gap_seconds=hour.maximum_bracketing_gap_seconds,
                                     independently_averaged_P58B_mw=avg, published_P58C_mw=value,
                                     residual_mw=avg - value))
    table = pd.DataFrame(rows)
    summary = table.groupby(['label_interpretation', 'integration_method']).residual_mw.agg(
        sample_count='size', mean_absolute_error_mw=lambda x: x.abs().mean(),
        root_mean_square_error_mw=lambda x: np.sqrt(np.mean(x ** 2)),
        max_absolute_error_mw=lambda x: x.abs().max()).reset_index()
    table.to_csv(FOLDER / 'p58b_p58c_interval_comparison.csv', index=False, lineterminator='\n')
    summary.to_csv(FOLDER / 'time_alignment_summary.csv', index=False, lineterminator='\n')
    pd.concat(coverage_rows, ignore_index=True).to_csv(
        FOLDER / 'p58b_hourly_coverage.csv', index=False, lineterminator='\n')
    protocol = dict(interval='[hour_start,hour_end)', max_bracketing_gap_seconds=600,
                    extrapolation_allowed=False, required_coverage_seconds=3600,
                    duplicate_policy='identical_values_collapsed_conflicting_values_rejected',
                    conventions=['forward_sample_hold', 'backward_sample_hold', 'linear_between_samples'],
                    label_convention_evidence='load_only_comparison_not_exact_NYISO_integration_reproduction')
    (FOLDER / 'integration_protocol.json').write_bytes((json.dumps(protocol, indent=2) + '\n').encode('utf-8'))
    sources = [{'source': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'url': u}
               for p, u in [(pal, url), (integrated, 'https://mis.nyiso.com/public/csv/palIntegrated/20250701palIntegrated_csv.zip')]]
    (FOLDER / 'source_manifest.json').write_bytes((json.dumps(sources, indent=2) + '\n').encode())
    print(summary.to_string(index=False))


if __name__ == '__main__':
    main()
