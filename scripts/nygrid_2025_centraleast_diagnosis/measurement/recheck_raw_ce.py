"""Independently reaggregate frozen NYISO P32 CE records, without model use."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import io
import json
import zipfile
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_centraleast_diagnosis/measurement'
SOURCE = ROOT / 'output/nygrid_2025_inputs/load_source'
NAME = 'CENTRAL EAST - VC'
HEADER = ['Timestamp','Interface Name','Point ID','Flow (MWH)','Positive Limit (MWH)','Negative Limit (MWH)']


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()


def record(path):
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    receipts = pd.read_csv(SOURCE / 'source_receipts.csv')
    members = pd.read_csv(SOURCE / 'source_members.csv')
    catalog = pd.read_csv(SOURCE / 'hour_catalog.csv')
    public = pd.read_csv(SOURCE / 'interface_wide.csv', float_precision='round_trip')
    quality = pd.read_csv(SOURCE / 'interface_quality_wide.csv')
    assert np.array_equal(catalog.hour_index, np.arange(1, 8761))
    assert np.array_equal(public.timestamp_utc, catalog.timestamp_utc)
    assert np.array_equal(quality.timestamp_utc, catalog.timestamp_utc)
    archive_receipts = receipts.loc[receipts.family == 'ExternalLimitsFlows'].sort_values('month')
    assert len(archive_receipts) == 13
    raw = []; member_checks = []; dependencies = [Path(__file__)]
    for row in archive_receipts.itertuples(index=False):
        path = ROOT / row.archive
        assert sha(path) == row.sha256
        dependencies.append(path)
        with zipfile.ZipFile(path) as archive:
            names = sorted(n for n in archive.namelist() if n.endswith('ExternalLimitsFlows.csv'))
            if row.month == '2026-01': names = ['20260101ExternalLimitsFlows.csv']
            for name in names:
                payload = archive.read(name)
                existing = members[(members.family == 'ExternalLimitsFlows') & (members.source_archive == row.archive) & (members.source_member == name)]
                assert len(existing) == 1
                digest = hashlib.sha256(payload).hexdigest()
                assert digest == existing.iloc[0].member_sha256
                frame = pd.read_csv(io.BytesIO(payload))
                assert frame.columns.tolist() == HEADER
                ce = frame.loc[frame['Interface Name'] == NAME]
                assert len(ce) > 0 and (ce['Point ID'] == 23330).all()
                naive = pd.DatetimeIndex(pd.to_datetime(ce.Timestamp, format='mixed'))
                day = pd.Timestamp(name[:8])
                assert (naive.normalize() == day).all()
                rewind = np.r_[False, np.diff(naive.asi8) < 0]
                assert rewind.sum() == (1 if name.startswith('20251102') else 0)
                # First ambiguous 01:xx block is EDT; the block after the raw
                # backward clock transition is EST. No UTC lag is fitted.
                first_clock_block = np.cumsum(rewind) == 0
                utc = naive.tz_localize('America/New_York', ambiguous=first_clock_block, nonexistent='raise').tz_convert('UTC')
                seconds = utc.asi8 // 10 ** 9
                assert (np.diff(seconds) >= 0).all()
                value = ce['Flow (MWH)'].to_numpy(float)
                assert not np.isinf(value).any()
                raw.append(pd.DataFrame(dict(utc_seconds=seconds, value=value)))
                member_checks.append(dict(source_archive=row.archive, source_member=name, member_sha256=digest,
                    CE_point_id=23330, CE_rows=len(ce), raw_clock_rewinds=int(rewind.sum()), source_url=row.source_url))
    raw = pd.concat(raw, ignore_index=True)
    groups = raw.groupby('utc_seconds', sort=True).value.agg(['mean','size','min','max'])
    times = groups.index.to_numpy(np.int64); values = groups['mean'].to_numpy(float)
    starts = pd.DatetimeIndex(pd.to_datetime(catalog.timestamp_utc, utc=True)).asi8 // 10 ** 9
    assert np.all(np.diff(starts) == 3600)
    independent = np.full(8760, np.nan); qualified = np.zeros(8760, bool)
    maximum_gap = np.zeros(8760); covered = np.zeros(8760)
    for h, start in enumerate(starts):
        end = start + 3600
        k = max(0, int(np.searchsorted(times, start, side='right') - 1))
        integral = 0.; coverage = 0.; gap_max = 0.
        while k + 1 < len(times) and times[k] < end:
            left, right = max(start, times[k]), min(end, times[k + 1])
            if right > left:
                gap = int(times[k + 1] - times[k]); gap_max = max(gap_max, gap)
                if gap <= 600 and np.isfinite(values[k]):
                    integral += (right - left) * values[k]
                    coverage += right - left
            k += 1
        covered[h] = coverage; maximum_gap[h] = gap_max
        qualified[h] = coverage == 3600
        if qualified[h]: independent[h] = integral / 3600
    supplied = public[NAME].to_numpy(float)
    supplied_q = quality[NAME].to_numpy(bool)
    assert np.array_equal(qualified, supplied_q)
    assert np.array_equal(np.isnan(independent), np.isnan(supplied))
    error = np.abs(independent[qualified] - supplied[qualified])
    assert error.max() < 1e-8
    table = catalog.copy()
    table['compiled_CE_numeric_as_MW'] = supplied
    table['independent_CE_numeric_as_MW'] = independent
    table['coverage_qualified'] = qualified
    table['covered_seconds'] = covered
    table['maximum_bracketing_gap_seconds'] = maximum_gap
    table['absolute_difference'] = np.abs(independent - supplied)
    table.to_csv(OUT / 'raw_source_reaggregation.csv', index=False, lineterminator='\n')
    pd.DataFrame(member_checks).to_csv(OUT / 'raw_source_members_checked.csv', index=False, lineterminator='\n')
    dependencies += [SOURCE / p for p in ['source_receipts.csv','source_members.csv','hour_catalog.csv','interface_wide.csv','interface_quality_wide.csv']]
    receipt = dict(passed=True, created_utc=datetime.now(timezone.utc).isoformat(),
        evidence_status='Fresh independent reread of frozen historical 2025 public source archives, not live 2026 operating telemetry.',
        interface=NAME, point_id=23330, archive_count=len(archive_receipts), daily_members_checked=len(member_checks),
        raw_CE_rows_including_endpoint_day=len(raw), unique_timestamps=len(groups),
        duplicate_timestamp_groups=int((groups['size'] > 1).sum()),
        conflicting_duplicate_timestamp_groups=int(((groups['size'] > 1) & (groups['max'] != groups['min'])).sum()),
        qualified_hours=int(qualified.sum()), clock_hours=8760,
        maximum_compiled_vs_independent_hourly_difference=float(error.max()),
        actual_source_header=HEADER, source_timezone_provided=False,
        time_policy='New York calendar plus explicit raw-order fall clock rewind; first01xx=EDT, second01xx=EST; no fitted time lag.',
        quantity_policy='The existing published Flow(MWH) numeric-as-MW assumption is retained, not independently certified or rescaled.',
        aggregation='Average duplicate UTC timestamps, then forward-hold integration over [UTC hour,next hour); require3600seconds of finite coverage and all contributing source gaps<=600seconds.',
        raw_source_or_compiled_benchmark_changed=False, model_or_interface_membership_used=False,
        physical_P32_meter_binding_certified=False,
        dependencies=[record(p) for p in dependencies],
        outputs=[record(OUT / p) for p in ['raw_source_reaggregation.csv','raw_source_members_checked.csv']])
    (OUT / 'raw_source_check.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:receipt[k] for k in ['passed','archive_count','daily_members_checked','qualified_hours','maximum_compiled_vs_independent_hourly_difference']}))
    return receipt


if __name__ == '__main__': main()
