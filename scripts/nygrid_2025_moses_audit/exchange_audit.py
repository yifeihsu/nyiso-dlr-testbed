"""Independent exchange-source and Ontario-routing audit; no model edits.

Preserves frozen 2019/2025 inputs, generator outputs, and network arrays. New
P34 observations are evidence only: their signed PTID values are not silently
promoted to a model boundary convention. No Moses observations are used to fit
parameters, infer the PAR sign, or choose an interchange split.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import time
import urllib.request
import zipfile

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_moses_audit/exchanges"
RAW = OUT / "raw"
TZ = "America/New_York"
PAR_IDS = [25118, 25119]
CHANNELS = ["SCH - HQ - NY", "SCH - HQ_CEDARS", "SCH - OH - NY", "SCH - NE - NY",
            "SCH - NPX_1385", "SCH - NPX_CSC", "SCH - PJ - NY", "SCH - PJM_HTP",
            "SCH - PJM_NEPTUNE", "SCH - PJM_VFT"]
REGIONS = {"ISONE": ["SCH - NE - NY", "SCH - NPX_1385", "SCH - NPX_CSC"],
           "ONTARIO": ["SCH - OH - NY"],
           "PJM": ["SCH - PJ - NY", "SCH - PJM_HTP", "SCH - PJM_NEPTUNE", "SCH - PJM_VFT"],
           "HQ": ["SCH - HQ - NY", "SCH - HQ_CEDARS"]}
PROTECTED = ["output/nygrid_2019_full_stage1/full_year.mat",
             "output/nygrid_2025_inputs/model/operating_inputs.mat",
             "output/nygrid_2025_dispatch/dispatch/dispatch.mat",
             "output/nygrid_2025_downstate/network/network_cases.mat",
             "output/nygrid_2025_slim/network/network_cases.mat"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def stats(values):
    x = np.asarray(values, float)
    x = x[np.isfinite(x)]
    return dict(hours=int(len(x)), mean=float(np.mean(x)), mean_absolute=float(np.mean(abs(x))),
                minimum=float(np.min(x)), maximum=float(np.max(x)), negative_hours=int((x < 0).sum()))


def csv(frame, name):
    path = OUT / name
    compression = {"method": "gzip", "mtime": 0} if path.suffix == ".gz" else None
    frame.to_csv(path, index=False, lineterminator="\n", compression=compression)


def acquire(url, offline=False):
    path = RAW / url.rsplit("/", 1)[-1]
    receipt_path = path.with_suffix(path.suffix + ".receipt.json")
    if path.exists():
        require(receipt_path.exists(), f"Unreceipted source: {path}")
        receipt = json.loads(receipt_path.read_text())
        require(receipt["url"] == url and receipt["sha256"] == sha(path), f"Source changed: {path}")
        return receipt
    require(not offline, f"Offline source missing: {url}")
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "NPCC-exchange-source-audit/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
                receipt = dict(url=url, http_status=response.status,
                               http_last_modified=response.headers.get("Last-Modified", ""),
                               retrieved_utc=stamp(), bytes=len(payload),
                               sha256=hashlib.sha256(payload).hexdigest())
            if path.suffix == ".zip":
                with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                    require(archive.testzip() is None, "ZIP CRC failure")
            path.write_bytes(payload)
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            return receipt
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def fetch_par_sources(offline):
    specs = [(year, month) for year in [2019, 2025] for month in range(1, 13)] + [(2020, 1), (2026, 1)]
    receipts = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(acquire, f"https://mis.nyiso.com/public/csv/ParFlows/{y}{m:02d}01ParFlows_csv.zip", offline): (y, m)
                   for y, m in specs}
        for future in as_completed(futures):
            y, m = futures[future]
            receipts.append({**future.result(), "year": y, "month": m})
            print(f"Verified P34 {y}-{m:02d}", flush=True)
    csv(pd.DataFrame(receipts).sort_values(["year", "month"]), "par_source_receipts.csv")


def probe_schedule_january(offline):
    """Bounded check of the proposed zero-schedule alternative, no sign fitting."""
    url = "https://mis.nyiso.com/public/txt/parSchedule/20250101parSchedule_txt.zip"
    acquire(url, offline)
    definition_url = "https://mis.nyiso.com/public/txt/parSchedule/defineParSchedule.doc"
    acquire(definition_url, offline)
    rows = []
    with zipfile.ZipFile(RAW / url.rsplit("/", 1)[-1]) as archive:
        members = sorted(archive.namelist())
        for member in members:
            lines = archive.read(member).decode("utf-8").splitlines()
            header = lines[0].split()
            require(header[0] == "00:00" and header[2:4] == ["60", "24"], "Unexpected January PAR schedule axis")
            selected = []
            for line in lines[1:]:
                fields = line.split()
                if fields and fields[0] in [str(i) for i in PAR_IDS]:
                    require(len(fields) == 26, "Expected two identity fields and24 hourly January values")
                    selected.append(int(fields[0]))
                    for hour, value in enumerate(fields[2:], 1):
                        rows.append(dict(source_member=member, ptid=int(fields[0]), source_side_code=fields[1],
                                         source_hour_position_1based=hour, schedule_raw_mw=float(value)))
            require(sorted(selected) == PAR_IDS, "Missing or duplicated PS33/PS34 schedule identity")
    frame = pd.DataFrame(rows)
    csv(frame, "P53A_January2025_probe.csv")
    report = dict(scope="January2025 only; full-year download not performed because zero-target hypothesis failed",
                  files=len(members), records=len(frame), nonzero_values=int(frame.schedule_raw_mw.ne(0).sum()),
                  minimum=float(frame.schedule_raw_mw.min()), maximum=float(frame.schedule_raw_mw.max()),
                  mean=float(frame.schedule_raw_mw.mean()), sign_still_unverified=True, source_url=url,
                  definition_url=definition_url,
                  definition_finding="Header specifies starting time/date, minute step, number of steps and PARs; data rows contain PTID, Control(L or G), and hourly MWs. Definition labels the control code but does not define geographic positive-flow direction.")
    require(report["nonzero_values"] > 0, "Zero-schedule hypothesis result changed; review source independently")
    (OUT / "P53A_January2025_probe.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def local_utc(local):
    probe = local.tz_localize(TZ, ambiguous="NaT", nonexistent="raise")
    ambiguous = np.asarray(probe.isna())
    flags = np.zeros(len(local), bool)
    rewinds = np.flatnonzero(np.diff(local.asi8) < -30 * 60 * 10**9) + 1
    if ambiguous.any():
        candidates = [i for i in rewinds if ambiguous[i] and ambiguous[i - 1]]
        require(len(candidates) == 1, "P34 ambiguous fall fold lacks explicit raw clock rewind")
        flags[:candidates[0]] = True
    result = local.tz_localize(TZ, ambiguous=flags, nonexistent="raise").tz_convert("UTC")
    return result, int(ambiguous.sum()), int(np.count_nonzero(np.diff(result.asi8) < 0))


def par_raw(year):
    parts, timing = [], []
    for y, month in [(year, m) for m in range(1, 13)] + [(year + 1, 1)]:
        path = RAW / f"{y}{month:02d}01ParFlows_csv.zip"
        with zipfile.ZipFile(path) as archive:
            for member in sorted(archive.namelist()):
                if y != year and member != f"{y}0101ParFlows.csv":
                    continue
                payload = archive.read(member)
                frame = pd.read_csv(io.BytesIO(payload))
                require(list(frame.columns) == ["Timestamp", "Point ID", "Flow (MWH)"], f"P34 schema: {member}")
                frame = frame.loc[frame["Point ID"].isin(PAR_IDS)].copy()
                require(set(frame["Point ID"]) == set(PAR_IDS), f"Missing P34 St Lawrence PTID: {member}")
                for ptid, group in frame.groupby("Point ID", sort=False):
                    local = pd.DatetimeIndex(pd.to_datetime(group.Timestamp, format="mixed"))
                    require((local.normalize() == pd.Timestamp(member[:8])).all(), f"P34 filename-day conflict: {member}")
                    utc, ambiguous, unordered = local_utc(local)
                    parts.append(pd.DataFrame(dict(timestamp_utc=utc, point_id=int(ptid),
                                                   original_flow_mw=pd.to_numeric(group["Flow (MWH)"], errors="raise").to_numpy(),
                                                   source_member=member, source_archive=path.name)))
                    timing.append(dict(source_member=member, point_id=ptid, rows=len(group),
                                       ambiguous_rows=ambiguous, out_of_order_utc_rows=unordered,
                                       member_sha256=hashlib.sha256(payload).hexdigest()))
    raw = pd.concat(parts, ignore_index=True)
    csv(raw, f"par_stlawrence_raw_{year}.csv.gz")
    csv(pd.DataFrame(timing), f"par_timing_receipts_{year}.csv")
    return raw


def integrate_par(raw, year, save=True):
    """Independent forward-hold integration; no missing interval interpolation."""
    hours = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01", freq="h", inclusive="left", tz=TZ).tz_convert("UTC")
    starts = hours.asi8 // 10**9
    result = pd.DataFrame(dict(timestamp_utc=hours, hour_index=np.arange(1, len(hours) + 1)))
    for ptid in PAR_IDS:
        block = raw.loc[raw.point_id.eq(ptid)]
        grouped = block.groupby("timestamp_utc", sort=True).original_flow_mw.agg(["mean", "count", "min", "max"])
        ts = grouped.index.asi8 // 10**9
        values = grouped["mean"].to_numpy(float)
        means, coverage, maxgaps, spreads = [], [], [], []
        for left in starts:
            right = left + 3600
            lo = max(0, np.searchsorted(ts, left, side="right") - 1)
            hi = min(len(ts) - 1, np.searchsorted(ts, right, side="left"))
            integral = 0.; seconds = 0.; gap = 0.; spread = 0.
            for j in range(lo, hi):
                touched = max(0, min(right, ts[j + 1]) - max(left, ts[j]))
                if not touched:
                    continue
                interval_gap = ts[j + 1] - ts[j]
                gap = max(gap, interval_gap)
                spread = max(spread, float(grouped.iloc[j]["max"] - grouped.iloc[j]["min"]))
                if interval_gap <= 600 and np.isfinite(values[j]):
                    seconds += touched
                    integral += touched * values[j]
            means.append(integral / 3600 if seconds == 3600 else np.nan)
            coverage.append(seconds); maxgaps.append(gap); spreads.append(spread)
        result[f"ptid_{ptid}_original_flow_mw"] = means
        result[f"ptid_{ptid}_coverage_seconds"] = coverage
        result[f"ptid_{ptid}_maximum_gap_seconds"] = maxgaps
        result[f"ptid_{ptid}_maximum_duplicate_spread_mw"] = spreads
    columns = [f"ptid_{i}_original_flow_mw" for i in PAR_IDS]
    result["par_sum_original_sign_mw"] = result[columns].sum(axis=1, min_count=2)
    result["coverage_qualified"] = np.isfinite(result["par_sum_original_sign_mw"])
    result["PS33_raw_mw"] = result["ptid_25118_original_flow_mw"]
    result["PS34_raw_mw"] = result["ptid_25119_original_flow_mw"]
    result["combined_raw_mw"] = result["par_sum_original_sign_mw"]
    for device, ptid in [("PS33", 25118), ("PS34", 25119)]:
        result[f"{device}_coverage_seconds"] = result[f"ptid_{ptid}_coverage_seconds"]
        result[f"{device}_coverage_qualified"] = result[f"ptid_{ptid}_coverage_seconds"].eq(3600)
    result["sign_to_ONTARIO_to_NY"] = "not_promoted_pending_independent_direction_evidence"
    if save:
        csv(result, f"par_stlawrence_hourly_{year}.csv")
    return result


def validate_source_helpers():
    """Analytical source-interval and DST cases independent of model flows."""
    frames = []
    for ptid in PAR_IDS:
        times = pd.date_range("2025-01-01 05:00Z", periods=25, freq="5min")
        frames.append(pd.DataFrame(dict(timestamp_utc=times, point_id=ptid,
                                        original_flow_mw=np.where(times.hour == 5, 10., 20.))))
    raw = pd.concat(frames, ignore_index=True)
    result = integrate_par(raw, 2025, save=False)
    require(result.loc[0, "combined_raw_mw"] == 20 and result.loc[1, "combined_raw_mw"] == 40,
            "Analytical constant-hour integration failed")
    require(not result.loc[2, "coverage_qualified"], "Unbracketed interval silently extrapolated")
    gap = raw.loc[~raw.timestamp_utc.between(pd.Timestamp("2025-01-01 05:15Z"), pd.Timestamp("2025-01-01 05:35Z"))]
    result = integrate_par(gap, 2025, save=False)
    require(not result.loc[0, "coverage_qualified"] and np.isnan(result.loc[0, "combined_raw_mw"]),
            "Long source gap silently interpolated")
    local = pd.DatetimeIndex(["2025-11-02 01:00", "2025-11-02 01:55", "2025-11-02 01:00", "2025-11-02 01:55"])
    utc, ambiguous, unordered = local_utc(local)
    require(ambiguous == 4 and unordered == 0 and utc[2] - utc[0] == pd.Timedelta(hours=1),
            "Two source-supported fall folds were not preserved")
    try:
        local_utc(local[:2])
    except ValueError:
        pass
    else:
        raise ValueError("Unsupported fall fold silently guessed")
    return dict(constant_hour_and_next_hour_boundary=True, unbracketed_hour_remains_NaN=True,
                long_gap_rejected_without_interpolation=True, two_fall_folds_preserved_from_raw_rewind=True,
                unsupported_fold_fails_closed=True)


def dc_flows(case, pg, pd_, dc):
    bus, branch = np.asarray(case["bus"], float), np.asarray(case["branch"], float)
    n = len(bus); f, t = branch[:, 0].astype(int) - 1, branch[:, 1].astype(int) - 1
    require(np.array_equal(bus[:, 0], np.arange(1, n + 1)), "Unexpected bus order")
    c = np.zeros((len(branch), n)); c[np.arange(len(branch)), f] = 1; c[np.arange(len(branch)), t] = -1
    tap = np.where(branch[:, 8] != 0, branch[:, 8], 1)
    weights = float(case["baseMVA"]) * branch[:, 10] / branch[:, 3] / tap
    bf = weights[:, None] * c; b = c.T @ bf; f0 = -weights * np.deg2rad(branch[:, 9]); p0 = c.T @ f0
    cg = np.zeros((len(case["gen"]), n)); cg[np.arange(len(cg)), np.asarray(case["gen"])[:, 0].astype(int) - 1] = 1
    inj = pg @ cg - pd_ - bus[:, 4]
    for j, row in enumerate(case["dcline"]):
        inj[:, int(row[0]) - 1] -= dc[:, j]
        inj[:, int(row[1]) - 1] += dc[:, j]
    theta = np.zeros_like(inj); theta[:, 1:] = np.linalg.solve(b[1:, 1:], (inj - p0)[:, 1:].T).T
    flows = theta @ bf.T + f0
    return flows, b, bf, p0, cg, inj


def frozen_exchange_audit():
    source = loadmat(ROOT / PROTECTED[1], simplify_cells=True)
    dispatch = loadmat(ROOT / PROTECTED[2], simplify_cells=True)
    historical = loadmat(ROOT / PROTECTED[0], simplify_cells=True,
                         variable_names=["base_case", "bus_pd", "input_pg", "result_pg", "branch_pf", "dc_pf", "timestamp_iso"])
    info = pd.read_csv(ROOT / "output/nygrid_2025_dispatch/fleet/source_parent/npcc.csv", keep_default_na=False).set_index("idx")
    interface = pd.read_csv(ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv")
    old_interface = pd.read_csv(ROOT / "output/nygrid_2019/nyiso_source_audit_hourly_reconstructed.csv")
    old_wide = old_interface.pivot(index="TimeStamp", columns="InterfaceName", values="FlowMWH")
    quality = pd.read_csv(ROOT / "output/nygrid_2025_inputs/load_source/interface_hourly.csv")
    gamma = float(dispatch["gamma"]); valid = np.asarray(dispatch["dispatch_qualified"], bool)
    expected_public = interface[CHANNELS].to_numpy(float)
    mask = np.isfinite(expected_public).all(axis=1)
    require(np.max(abs(source["boundary_public_mw"][mask] - expected_public[mask])) < 1e-8, "Source channel order/identity changed")
    require(np.max(abs(source["boundary_model_mw"][mask] - expected_public[mask] * gamma)) < 1e-8, "Boundary gamma conversion changed")
    dc_public = np.column_stack([interface[["SCH - NPX_1385", "SCH - NPX_CSC"]].sum(axis=1, min_count=2),
                                 interface["SCH - PJM_NEPTUNE"], interface["SCH - PJM_HTP"], interface["SCH - PJM_VFT"]])
    require(np.max(abs(dispatch["dc_pf"][valid] / gamma - dc_public[valid])) < 1e-8, "DC schedules dropped sign or duplicated")
    hq = interface[["SCH - HQ - NY", "SCH - HQ_CEDARS"]].sum(axis=1, min_count=2).to_numpy()
    require(np.max(abs(dispatch["gen_pg"][valid, -1] / gamma - hq[valid])) < 1e-8, "HQ clipping/sign error")
    source_hq_difference = interface["SCH - HQ - NY"] - interface["SCH - HQ_IMPORT_EXPORT"]
    channels = []
    for year, frame in [(2019, old_wide), (2025, interface)]:
        for channel in CHANNELS + ["SCH - HQ_IMPORT_EXPORT"]:
            channels.append(dict(year=year, channel=channel, **stats(frame[channel])))
    csv(pd.DataFrame(channels), "channel_summary.csv")
    # Independent annual accounting corroboration from the provider's published
    # table, not a comparison to Moses South or another fitted internal flow.
    gold_url = "https://www.nyiso.com/documents/20142/2226333/2020-Gold-Book-Final-Public.pdf/9ff426ab-e325-28bc-97cf-106d792593a1"
    annual_reference = [
        ("SCH - HQ - NY", "Chateaugay total including wheels", 9924.),
        ("SCH - HQ_CEDARS", "Cedars", 1003.),
        ("SCH - HQ_IMPORT_EXPORT", "Chateaugay imports minus exports excluding wheels", 8637. - 62.),
        ("SCH - OH - NY", "Bruce", 6298.),
        ("SCH - NE - NY", "Sandy Pond", -7151.),
        ("SCH - NPX_1385", "1385 Line", 238.),
        ("SCH - NPX_CSC", "Cross Sound Cable", 1162.),
        ("SCH - PJ - NY", "Keystone", 3265.),
        ("SCH - PJM_HTP", "HTP", 1314.),
        ("SCH - PJM_NEPTUNE", "Neptune", 5114.),
        ("SCH - PJM_VFT", "Linden VFT", 1961.)]
    annual_checks = [dict(channel=ch, proxy_bus=proxy, released_P32_hourly_integral_GWh=float(old_wide[ch].sum() / 1000),
                         Gold_Book_2019_scheduled_net_GWh=energy,
                         difference_GWh=float(old_wide[ch].sum() / 1000 - energy),
                         source_url=gold_url, source_table="2020 Gold Book Table III-3d page95; whole-GWh reporting precision")
                     for ch, proxy, energy in annual_reference]
    annual_checks.append(dict(channel="HQ_NY_minus_HQ_IMPORT_EXPORT", proxy_bus="Chateaugay wheels-in minus wheels-out",
                             released_P32_hourly_integral_GWh=float((old_wide["SCH - HQ - NY"] - old_wide["SCH - HQ_IMPORT_EXPORT"]).sum()/1000),
                             Gold_Book_2019_scheduled_net_GWh=1349.,
                             difference_GWh=float((old_wide["SCH - HQ - NY"]-old_wide["SCH - HQ_IMPORT_EXPORT"]).sum()/1000-1349),
                             source_url=gold_url, source_table="2020 Gold Book Table III-3d page95; Chateaugay wheels-in1349 and wheels-out0"))
    csv(pd.DataFrame(annual_checks), "HQ_channel_independence_GoldBook2019_check.csv")
    alternatives = []
    for channel, block in quality.groupby("channel"):
        good = block.coverage_qualified.astype(str).str.lower().eq("true")
        differences = block.loc[good, "flow_mw"] - block.loc[good, "paper_arithmetic_mean_flow_mw"]
        alternatives.append(dict(channel=channel, **stats(differences)))
    csv(pd.DataFrame(alternatives), "p32_time_weighted_minus_arithmetic.csv")
    flows25, b, bf, p0, cg, injections = dc_flows(dispatch["base_case"], dispatch["gen_pg"], dispatch["bus_pd"], dispatch["dc_pf"])
    records, region_records = [], []
    series = {}
    for year, case, pd_, pg, flows, dc, scale, good, timestamps in [
        (2019, historical["base_case"], historical["bus_pd"], historical["result_pg"], historical["branch_pf"], historical["dc_pf"], 1., np.ones(8760, bool), historical["timestamp_iso"]),
        (2025, dispatch["base_case"], dispatch["bus_pd"], dispatch["gen_pg"], flows25, dispatch["dc_pf"], gamma, valid, dispatch["timestamp_utc"])]:
        gen = np.asarray(case["gen"]); fuel = np.asarray(case["genfuel"]); d_bus = info.index[info.zone.eq("D")].to_numpy(int)
        in_d = np.isin(gen[:, 0], d_bus); hq_rows = (fuel == "Import") & (gen[:, 0] == 48)
        frame = pd.DataFrame(dict(timestamp=timestamps, source_qualified=good,
            D_native_generation_public_mw=pg[:, in_d & ~hq_rows].sum(axis=1) / scale,
            HQ_Cedars_signed_public_mw=pg[:, hq_rows].sum(axis=1) / scale,
            D_load_public_mw=pd_[:, d_bus - 1].sum(axis=1) / scale,
            Ontario_northern_to_D_public_mw=-flows[:, 210] / scale,
            Ontario_western_to_A_public_mw=-flows[:, [61, 62]].sum(axis=1) / scale,
            modeled_Moses_D_to_E_public_mw=-flows[:, [45, 50, 51]].sum(axis=1) / scale))
        residual = (frame.D_native_generation_public_mw + frame.HQ_Cedars_signed_public_mw - frame.D_load_public_mw
                    + frame.Ontario_northern_to_D_public_mw - frame.modeled_Moses_D_to_E_public_mw)
        require(np.max(abs(residual[good])) < 1e-7, "Zone-D cutset identity failed")
        frame["D_cutset_identity_residual_mw"] = residual
        for column in frame.select_dtypes("number"):
            records.append(dict(year=year, quantity=column, **stats(frame.loc[good, column])))
        for name, areas in [("ISONE", [1]), ("ONTARIO", [4]), ("PJM", [5, 6])]:
            region_buses = info.index[info.area.isin(areas)].to_numpy(int)
            gmask = np.isin(gen[:, 0], region_buses)
            net = (pg[:, gmask].sum(axis=1) - pd_[:, region_buses - 1].sum(axis=1)) / scale
            imports = (old_wide if year == 2019 else interface)[REGIONS[name]].sum(axis=1, min_count=len(REGIONS[name])).to_numpy()
            error = net - imports
            region_records.append(dict(year=year, region=name, maximum_net_minus_schedule_mw=float(np.nanmax(abs(error[good]))),
                                       mean_net_export_public_mw=float(np.mean(net[good])), reference_slack_is_in_region=name == "ISONE" and year == 2019))
            frame[f"{name}_net_export_public_mw"] = net
        csv(frame, f"regional_cut_hourly_{year}.csv.gz"); series[year] = frame
    csv(pd.DataFrame(records), "regional_cut_summary.csv")
    csv(pd.DataFrame(region_records), "regional_schedule_balance.csv")
    # Determine the exact sensitivity of northern Ontario routing to independent
    # injection categories. This is a linear decomposition, never a fit.
    transfer = np.zeros(140); transfer[1:] = np.linalg.solve(b[1:, 1:].T, -bf[210, 1:])
    genload_delta = (np.nanmean(dispatch["gen_pg"][valid] @ cg - dispatch["bus_pd"][valid], axis=0) / gamma)
    old_gen = historical["base_case"]["gen"]; oldcg = np.zeros((len(old_gen), 140)); oldcg[np.arange(len(old_gen)), old_gen[:, 0].astype(int)-1] = 1
    old_injections = historical["result_pg"] @ oldcg - historical["bus_pd"] - historical["base_case"]["bus"][:, 4]
    genload_delta -= np.mean(historical["result_pg"] @ oldcg - historical["bus_pd"], axis=0)
    for j, row in enumerate(historical["base_case"]["dcline"]):
        old_injections[:, int(row[0]) - 1] -= historical["dc_pf"][:, j]
        old_injections[:, int(row[1]) - 1] += historical["dc_pf"][:, j]
    bus_delta = np.mean(injections[valid], axis=0) / gamma - np.mean(old_injections, axis=0)
    northern_change = (series[2025].loc[valid, "Ontario_northern_to_D_public_mw"].mean()
                       - series[2019].Ontario_northern_to_D_public_mw.mean())
    require(abs(np.dot(transfer, bus_delta) - northern_change) < 1e-7, "Injection decomposition omits a control or device")
    decomposition = info.reset_index()[["idx", "name", "area", "zone"]].copy()
    decomposition["mean_injection_change_public_mw"] = bus_delta
    decomposition["generation_minus_load_change_public_mw"] = genload_delta
    decomposition["DC_and_shunt_injection_change_public_mw"] = bus_delta - genload_delta
    decomposition["northern_Ontario_flow_sensitivity"] = transfer
    decomposition["contribution_to_Ontario_D_change_public_mw"] = transfer * bus_delta
    csv(decomposition, "ontario_northern_flow_injection_decomposition.csv")
    summary = dict(signed_HQ_injection_preserved=True, signed_four_DC_schedules_preserved=True,
                   channels_counted_once=CHANNELS, HQ_IMPORT_EXPORT_is_not_added=True,
                   HQ_NY_minus_HQ_IMPORT_EXPORT_2025_public_mw=stats(source_hq_difference),
                   source_qualified_dispatch_hours=int(valid.sum()), gamma=gamma,
                   HQ_channel_interpretation="HQ-NY includes Chateaugay wheel-through; HQ_IMPORT_EXPORT overlaps that channel; Cedars is a distinct path. Independently corroborated by provider2019 annual scheduled transaction table, not Moses fitting.",
                   HQ_primary_annual_source=gold_url,
                   prescribed_regional_generation_policy="snapshot regional PG proportions of regional load plus signed aggregate schedule; no north/west Ontario tie split observation",
                   Ontario_D_control_representation="single aggregate branch211 bus48(MOSES E) to bus100(PHAS); fixed zero phase shift; no hourly StLawrence PAR control",
                   north_tie_branch211=list(map(float, np.asarray(dispatch["base_case"]["branch"])[210])),
                   modeled_yearly_means={str(y): {c: float(f.loc[f.source_qualified, c].mean()) for c in f.select_dtypes("number")} for y, f in series.items()})
    return summary, series


def main(offline=False, skip_acquire=False):
    OUT.mkdir(parents=True, exist_ok=True); RAW.mkdir(parents=True, exist_ok=True)
    fingerprints = {path: sha(ROOT / path) for path in PROTECTED}
    helper_checks = validate_source_helpers()
    summary, model = frozen_exchange_audit()
    if not skip_acquire:
        fetch_par_sources(offline)
    schedule_probe = probe_schedule_january(offline)
    par_summary = []
    for year in [2019, 2025]:
        hourly = integrate_par(par_raw(year), year)
        qualified = hourly.coverage_qualified.to_numpy(bool)
        par_summary.append(dict(year=year, ptid_sum_original_sign=stats(hourly.par_sum_original_sign_mw),
                                source_gap_hours=int((~qualified).sum()),
                                sign_not_selected_by_Moses_observations=True))
    summary.update(P34=par_summary, P53A_January_probe=schedule_probe,
                   created_utc=stamp(), audit_script_sha256=sha(Path(__file__)),
                   source_extraction_focused_checks=helper_checks, primary_sources=[
        dict(url="https://mis.nyiso.com/public/P-34list.htm", role="official PAR archive index"),
        dict(url="https://www.nyiso.com/documents/20142/3691300/Winter2016-17_Operating_Study_Approved_OC_12-15-2016_Appendices.pdf/abf1af25-5b11-8303-4a42-273c60867fef", role="page57 maps PTID25118/25119 to StLawrence PS33/PS34 and distinguishes physical line PTID25026/25037"),
        dict(url="https://www.nyiso.com/documents/20142/3691300/Summer2025-OperatingStudy-APPROVED.pdf/3aaa5eb6-9fa4-53b5-181a-189e3ac52fcb", role="2025 operating context; separate Chateaugay wheel-through and Cedars paths"),
        dict(url="https://ieso.ca/-/media/Files/IESO/Document-Library/planning-forecasts/reliability-outlook/TTCMethodology.pdf", role="section5.5 two230kVStLawrencecircuits controlled by PARs")],
        frozen_inputs=[dict(path=p, sha256=value, unchanged=sha(ROOT / p) == value) for p, value in fingerprints.items()],
        source_direction_promotion_status="pending independent P34 direction evidence; no model changes or sign tuning performed")
    require(all(row["unchanged"] for row in summary["frozen_inputs"]), "Frozen input changed during audit")
    (OUT / "exchange_audit_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ["signed_HQ_injection_preserved", "signed_four_DC_schedules_preserved", "HQ_NY_minus_HQ_IMPORT_EXPORT_2025_public_mw", "P34"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--skip-acquire", action="store_true")
    args = parser.parse_args()
    main(args.offline, args.skip_acquire)
