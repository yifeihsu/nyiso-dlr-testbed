"""Unique EIA860 2025 NYISO fleet and explicit landing/bound assumptions.

This builder reads public-source inventory and identity metadata only. It never
reads solved generation or network flows. The complete inventory is retained;
scope/status exclusions are represented by zero dispatch bounds, not deletions.
Run using the task runtime from the repository root. No network is required.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import numpy as np
from scipy.io import savemat

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import build_compact_nonfossil_generation_inputs as nf

OUT = ROOT / 'output/nygrid_2025_dispatch/fleet'
INPUT = ROOT / 'output/nygrid_2025_inputs'
RAW = ROOT / 'tmp/nonfossil_sources/eia860_2025'
EIA_PLANT = RAW / '2___Plant_Y2025_Early_Release.xlsx'
EIA_GEN = RAW / '3_1_Generator_Y2025_Early_Release.xlsx'
PARENT = OUT / 'source_parent'
PARENT_BOOTSTRAP = ROOT / 'tmp/nygrid_full_rebuild_check/capture_runtime'
PARENT_SOURCES = {
    'npcc.csv': ('Data/npcc.csv', '3f203b94d44b95607c48b4f5a8eb78adf42cbbc600294122ac87399e53626b2d'),
    'thermalGenNotMatched_2019.csv': ('Data/thermalGenNotMatched_2019.csv', '46824bfa90f5f91940955aacf6e9b8bcde1052532568f7c351dd1543ce2e11d3'),
    'nygrid_full_updateOpCond.m': ('nygrid_full_updateOpCond.m', '2a0ad5224190194abe528a824dfd508005aa2cdf23f5b4d8845ec80e3726154a'),
}
BUS_FILE = PARENT / 'npcc.csv'
LEGACY_FILE = INPUT / 'generation_source/full_2019_generator_mapping.csv'
EPA_FILE = INPUT / 'generation_source/epa_unit_identity_register.csv'
XWALK_FILE = ROOT / 'output/compact_ny_2025/generation_sources/epa/epa_eia_crosswalk_ny.csv'
EPA_ALL_FACILITIES = ROOT / 'tmp/epa_generation_raw/facility-2025.csv'
SCOPE_RECEIPTS = OUT / 'source_scope/source_receipts.json'
CORROBORATED_OUTSIDE_PLANTS = {50006, 56964}
LINDEN_NATIVE_IDS = {'GTG1', 'GTG2', 'GTG3', 'GTG4', 'GTG5', 'STG1', 'STG2', 'STG3'}
BAYONNE_NATIVE_IDS = {f'GT{i}' for i in range(1, 11)}
GRID_SECTORS = {'Electric Utility', 'IPP Non-CHP', 'IPP CHP'}
FOSSIL = {'NG', 'DFO', 'RFO', 'KER', 'BIT', 'SUB', 'LIG', 'WC', 'PC', 'SG', 'PG', 'OG', 'JF', 'WO', 'BFG', 'COG'}
OTHER_RENEWABLE = nf.OTHER_FUELS | {'WDL', 'WDS'}
REACTOR_ROWS = {(6122, '1'): 228, (6110, '1'): 229, (2589, '1'): 230,
                (2589, '2'): 231, (2497, '2'): 232, (8907, '3'): 233}
# These two legacy hydro rows explicitly represent the corresponding major site.
# Other historical hydro rows are geographic aggregates, not unit identities.
HYDRO_PLANT_ROWS = {2693: 234, 2694: 238}


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fields, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def ident(x):
    if x is None:
        return ''
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x).strip()


def pipe(values):
    return '|'.join(str(v) for v in sorted(set(values), key=str))


def n(d, k):
    return nf.num(d.get(k))


def reported(d, key):
    return d.get(key) is not None and str(d.get(key)).strip() not in {'', '.', 'NA', 'N/A'}


def unique_inventory(rows):
    """Never expand source capacities through EPA/legacy many-to-many joins."""
    keys = [(r['plant_id'], r['eia_generator_id']) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError('Duplicate EIA plant/generator key; cannot sum capacities')
    return sorted(rows, key=lambda r: (r['plant_id'], r['eia_generator_id']))


def fuel_category(fuel):
    if fuel in FOSSIL:
        return 'Combined Fossil'
    return {'NUC': 'Nuclear', 'WAT': 'Hydro', 'WND': 'Wind', 'MWH': 'Storage'}.get(
        fuel, 'Other Renewables' if fuel in OTHER_RENEWABLE else 'Other')


def native_scope_flags(row):
    """Reported BA is a scope screen, not independently verified geography.

    Explicit non-NYIS and missing BA records stay in the inventory, with physical
    capability retained. They cannot supply native NYISO balancing generation
    while external interchange is fixed. No BA exceptions are currently used.
    """
    sector_sync_ok = row['sector'] in GRID_SECTORS and row['synchronized_to_transmission_grid'] != 'N'
    ba = row['balancing_authority_code'].strip()
    ba_ok = ba == 'NYIS'
    market = market_scope_flags(row)
    return dict(**market, sector_synchronization_scope_eligible=int(sector_sync_ok),
        balancing_authority_scope_eligible=int(ba_ok),
        reported_other_balancing_authority=int(bool(ba) and not ba_ok),
        balancing_authority_metadata_missing=int(not ba),
        balancing_authority_independently_verified=0,
        balancing_authority_scope_policy='reported_NYIS_only_no_exceptions_nonNYIS_or_missing_excluded_not_independent_physical_BA_verification',
        grid_scope_eligible=int(sector_sync_ok and ba_ok and row['plant_id'] != 52168
                               and market['unit_market_scope_eligible']))


def market_scope_flags(row):
    """A plant BA field cannot override a corroborated unit-market exclusion."""
    state = row.get('inventory_state', 'NY')
    pid, gid = row['plant_id'], row.get('eia_generator_id', '')
    result = dict(unit_market_scope_eligible=1, native_market_scope_status='NY_state_reported_BA_screen',
        native_market_scope_evidence='EIA860:2025:Plant', outside_NY_state=int(state != 'NY'),
        market_scope_primary_corroborated=0, unit_market_overrides_plant_BA=0,
        native_p63_scope_inferred=0, native_p63_unit_output_observed=0, nyiso_market_ptid='',
        boundary_generation_separation_policy='native_generation_separate_from_fixed_external_schedules')
    if state == 'NY':
        return result
    evidence = 'NYISO:GoldBook:2025|NYISO:P19:20261010'
    if pid == 56964 and gid in BAYONNE_NATIVE_IDS:
        unit = int(gid.removeprefix('GT'))
        ptid = 323681 + unit if unit <= 8 else 323740 + unit
        result.update(native_market_scope_status='primary_corroborated_outside_state_NYISO_ZoneJ',
            native_market_scope_evidence=evidence, market_scope_primary_corroborated=1,
            native_p63_scope_inferred=1, nyiso_market_ptid=str(ptid))
    elif pid == 50006 and gid in LINDEN_NATIVE_IDS:
        result.update(native_market_scope_status='primary_corroborated_Linden_NYISO_cohort_excludes_GTG6',
            native_market_scope_evidence=evidence + '|EGCO:Linden:20251216', market_scope_primary_corroborated=1,
            native_p63_scope_inferred=1, nyiso_market_ptid='23786',
            boundary_generation_separation_policy='NYISO_native_Linden_generation_separate_from_PJM_VFT_transmission_schedule')
    elif pid == 50006 and gid == 'GTG6':
        result.update(unit_market_scope_eligible=0, native_market_scope_status='excluded_PJM_unit_despite_plant_NYIS_BA',
            native_market_scope_evidence='EGCO:Linden:20251216|EIA860:2025:Generator_2002_start_date',
            market_scope_primary_corroborated=1, unit_market_overrides_plant_BA=1,
            boundary_generation_separation_policy='external_PJM_unit_not_native_NYISO_generation')
    else:
        result.update(unit_market_scope_eligible=0, native_market_scope_status='quarantined_outside_state_NYIS_label_without_unit_market_zone_corroboration',
            native_market_scope_evidence='EIA860:2025:Plant_only_no_independent_market_zone_evidence',
            unit_market_overrides_plant_BA=1)
    return result


def active_in_month(row, month):
    """End-year status is a conservative assumption, not observed hourly outage."""
    if row['source_status'] not in {'OP', 'SB', 'RE'}:
        return False
    current = (2025, month)
    start = (row['operating_year'], row['operating_month'])
    if start[0] <= 0 or not 1 <= start[1] <= 12 or start >= current:
        return False
    if row['source_status'] == 'RE':
        end = (row['retirement_year'], row['retirement_month'])
        if end[0] <= 0 or not 1 <= end[1] <= 12 or current >= end:
            return False
    return True


def seasonal_capacity(row, month):
    # Same explicit season convention as the frozen source-prior builder.
    season = 'winter' if month in {11, 12, 1, 2, 3} else 'summer'
    return row.get('effective_' + season + '_capacity_mw', row[season + '_capacity_mw'])


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1., math.sqrt(a)))


def nearest_bus(row, buses):
    candidates = [b for b in buses if b['zone'] == row['zone']]
    if not candidates:
        raise ValueError(f"No parent bus for zone {row['zone']}")
    if row['coordinates_available']:
        ranked = [(distance_km(row['latitude'], row['longitude'], b['latitude'], b['longitude']), b['bus_id'])
                  for b in candidates]
        dist, bus = min(ranked)
        return bus, dist, 'same_zone_nearest_parent_bus_geographic_proxy'
    return min(b['bus_id'] for b in candidates), '', 'same_zone_lowest_bus_id_missing_coordinates_proxy'


def identity_links(epa_rows, xwalk_rows):
    """Return annotation sets; never attach a capacity to an association row."""
    links = defaultdict(set)
    evidence = defaultdict(set)
    for d in xwalk_rows:
        if not d.get('EIA_PLANT_ID') or not d.get('EIA_GENERATOR_ID'):
            continue
        k = (int(float(d['EIA_PLANT_ID'])), ident(d['EIA_GENERATOR_ID']))
        ek = f"EPA:ORIS:{int(float(d['CAMD_PLANT_ID']))}:UNIT:{d['CAMD_UNIT_ID']}"
        links[k].add(ek)
        evidence[k].add('EPA_EIA_crosswalk_2018_basis_2022_release_identity_continuity_assumed')
    for d in epa_rows:
        # Facility-2025 associated-generator labels are a second, contemporary
        # identity source. They do not imply independent generating capacities.
        for gid in re.findall(r'(?:^|,)\s*([^,()]+?)\s*\(', d['associated_generators']):
            k = (int(d['facility_id']), gid.strip())
            links[k].add(d['device_key'])
            evidence[k].add('EPA_facility2025_associated_generator_label')
    return links, evidence


def read_inventory():
    plants = {int(d['Plant Code']): (line, d) for line, d in nf.sheet_dicts(EIA_PLANT, 'Plant', 'Plant Code')
              if d.get('State') == 'NY' or d.get('Balancing Authority Code') == 'NYIS'}
    rows = []
    digest, plant_digest = sha(EIA_GEN), sha(EIA_PLANT)
    for sheet in ['Operable', 'Retired and Canceled']:
        for line, d in nf.sheet_dicts(EIA_GEN, sheet, 'Plant Code'):
            if d.get('State') != 'NY' and d.get('Plant Code') not in plants:
                continue
            pid, gid = int(d['Plant Code']), ident(d['Generator ID'])
            plant_line, p = plants.get(pid, (0, {}))
            fuel = ident(d.get('Energy Source 1'))
            state = ident(d.get('State'))
            market = market_scope_flags(dict(plant_id=pid, eia_generator_id=gid, inventory_state=state))
            if state == 'NY':
                zone, zone_policy = nf.plant_zone(pid, gid, d['County'], fuel)
            elif market['unit_market_scope_eligible']:
                zone, zone_policy = 'J', 'NYISO_2025_GoldBook_and_current_generator_roster_corroborated_ZoneJ'
            elif pid == 50006 and gid == 'GTG6':
                zone, zone_policy = 'PJM', 'owner_primary_unit6_PJM_overrides_plant_level_NYIS_metadata'
            else:
                zone, zone_policy = 'UNVERIFIED', 'outside_state_plant_NYIS_label_has_no_corroborated_NYISO_zone'
            latitude, longitude = nf.num(p.get('Latitude'), math.nan), nf.num(p.get('Longitude'), math.nan)
            coords = math.isfinite(latitude) and math.isfinite(longitude)
            row = dict(plant_id=pid, eia_generator_id=gid, device_key=f'EIA860:2025:PLANT:{pid}:GEN:{gid}',
                plant_name=d['Plant Name'], inventory_state=state, county=d['County'], zone=zone, zone_mapping_policy=zone_policy,
                energy_source_code=fuel, fuel_category=fuel_category(fuel), prime_mover=ident(d.get('Prime Mover')),
                technology=ident(d.get('Technology')), eia_unit_code=ident(d.get('Unit Code')),
                nameplate_capacity_mw=n(d, 'Nameplate Capacity (MW)'), summer_capacity_mw=n(d, 'Summer Capacity (MW)'),
                winter_capacity_mw=n(d, 'Winter Capacity (MW)'), reported_minimum_load_mw=n(d, 'Minimum Load (MW)'),
                summer_capacity_reported=int(reported(d, 'Summer Capacity (MW)')),
                winter_capacity_reported=int(reported(d, 'Winter Capacity (MW)')),
                minimum_load_enforced=0, source_status=ident(d.get('Status')), source_sheet=sheet,
                operating_year=int(n(d, 'Operating Year')), operating_month=int(n(d, 'Operating Month')),
                retirement_year=int(n(d, 'Retirement Year')), retirement_month=int(n(d, 'Retirement Month')),
                planned_retirement_year=int(n(d, 'Planned Retirement Year')), planned_retirement_month=int(n(d, 'Planned Retirement Month')),
                sector=ident(d.get('Sector Name')), synchronized_to_transmission_grid=ident(d.get('Synchronized to Transmission Grid')),
                balancing_authority_code=ident(p.get('Balancing Authority Code')),
                latitude=latitude if coords else '', longitude=longitude if coords else '', coordinates_available=int(coords),
                source_id='EIA860:2025:3_1_Generator_Y2025_Early_Release.xlsx', source_excel_row=line,
                source_sha256=digest, source_plant_excel_row=plant_line, source_plant_sha256=plant_digest,
                inventory_kind='EIA860_2025_inventory', source_url=nf.EIA_URLS[('860', 2025)],
                release_status='retrospective_2025_early_release_retrieved_2026-09-08',
                capacity_observed=1, hourly_dispatch_observed=0, hourly_availability_observed=0, availability_assumed=1,
                is_variable_renewable=int(fuel in {'SUN', 'WND'}), is_solar=int(fuel == 'SUN'),
                is_storage=int(fuel == 'MWH' or ident(d.get('Prime Mover')) in {'BA', 'PS'}),
                is_pumped_hydro=int(ident(d.get('Prime Mover')) == 'PS'),
                scope_policy='reported_NYIS_and_utility_or_IPP_and_not_explicitly_unsynchronized_proxy_for_native_scope',
                solar_btm_scope='sector_proxy_not_verified_market_vs_BTM' if fuel == 'SUN' else 'not_solar')
            rows.append(row)
    # Indian Point is absent from this latest workbook. Retain historical units
    # as explicit zero-bound tombstones to make the 2019-to-2025 change reviewable.
    historical = read_csv(ROOT / 'output/compact_ny_2025/generation_sources/nonfossil/eia860_nonfossil_inventory.csv')
    for pid, gid in [(2497, '2'), (8907, '3')]:
        if any(r['plant_id'] == pid and r['eia_generator_id'] == gid for r in rows):
            raise ValueError('Indian Point tombstone would duplicate 2025 source identity')
        h = next(r for r in historical if r['vintage'] == '2019' and int(r['plant_id']) == pid and r['generator_id'] == gid)
        row = {k: '' for k in rows[0]}
        row.update(plant_id=pid, eia_generator_id=gid, device_key=f'EIA860:2025:PLANT:{pid}:GEN:{gid}',
            plant_name=nf.REACTORS[(pid, gid)][0], inventory_state='NY', county='Westchester', zone='H', zone_mapping_policy='explicit_reactor_site_zone',
            energy_source_code='NUC', fuel_category='Nuclear', prime_mover='ST', technology='Nuclear',
            nameplate_capacity_mw=float(h['nameplate_capacity_mw']), summer_capacity_mw=float(h['summer_capacity_mw']),
            winter_capacity_mw=float(h['winter_capacity_mw']), reported_minimum_load_mw=0., minimum_load_enforced=0,
            summer_capacity_reported=1, winter_capacity_reported=1,
            source_status='RE', source_sheet='historical_tombstone_not_2025_workbook',
            operating_year=int(h['operating_year']), operating_month=int(h['operating_month']),
            retirement_year=2020 if pid == 2497 else 2021, retirement_month=4,
            planned_retirement_year=0, planned_retirement_month=0, sector='Electric Utility',
            synchronized_to_transmission_grid='N', balancing_authority_code='NYIS',
            latitude=float(h['latitude']), longitude=float(h['longitude']), coordinates_available=1,
            source_id=h['source_id'], source_excel_row=h['source_excel_row'], source_sha256=h['source_sha256'],
            inventory_kind='historical_retired_Indian_Point_tombstone',
            source_url='https://www.nrc.gov/facilities-safety/facility-finder/reactors/ip2' if pid == 2497 else 'https://www.eia.gov/todayinenergy/detail.php?id=50619',
            release_status='2019_capacity_historical_and_known_retirement', capacity_observed=1, hourly_dispatch_observed=0,
            hourly_availability_observed=0, availability_assumed=1, is_variable_renewable=0, is_solar=0,
            is_storage=0, is_pumped_hydro=0, scope_policy='retired_zero_bounds', solar_btm_scope='not_solar')
        rows.append(row)
    return unique_inventory(rows)


def build(out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    # Preserve the exact identity/zone source bytes with the fleet. Rebuilds do
    # not depend on the lifetime of the earlier diagnostic capture directory.
    PARENT.mkdir(parents=True, exist_ok=True)
    for name, (bootstrap_path, digest) in PARENT_SOURCES.items():
        dest = PARENT / name
        if not dest.exists():
            src = PARENT_BOOTSTRAP / bootstrap_path
            if sha(src) != digest:
                raise ValueError('Unverified parent-source bootstrap: ' + str(src))
            dest.write_bytes(src.read_bytes())
        if sha(dest) != digest:
            raise ValueError('Pinned parent source fingerprint changed: ' + str(dest))
    source_paths = [EIA_PLANT, EIA_GEN, BUS_FILE, LEGACY_FILE, EPA_FILE, XWALK_FILE,
                    ROOT / 'build_compact_nonfossil_generation_inputs.py', Path(__file__),
                    PARENT / 'nygrid_full_updateOpCond.m', PARENT / 'thermalGenNotMatched_2019.csv',
                    INPUT / 'load_source/load_hourly.csv',
                    ROOT / 'output/compact_ny_2025/generation_sources/nonfossil/eia860_nonfossil_inventory.csv',
                    EPA_ALL_FACILITIES, SCOPE_RECEIPTS]
    scope_receipts = json.loads(SCOPE_RECEIPTS.read_text(encoding='utf-8'))
    if {r['source_id'] for r in scope_receipts} != {'NYISO:GoldBook:2025', 'NYISO:P19:20261010',
                                                  'EGCO:Linden:20251216', 'NYISO:VFT:FERC:20120524'}:
        raise ValueError('Incomplete outside-NY market-scope primary-source receipts')
    scope_url = {}
    for receipt in scope_receipts:
        p = ROOT / receipt['path']
        if sha(p) != receipt['sha256']:
            raise ValueError('Market scope primary source changed: ' + receipt['path'])
        source_paths.append(p)
        scope_url[receipt['path']] = receipt['source_url']
    frozen = {r['path']: r for r in read_csv(INPUT / 'generation_source/source_manifest.csv')}
    manifest = []
    for p in source_paths:
        rel, digest = p.relative_to(ROOT).as_posix(), sha(p)
        if rel in frozen and frozen[rel]['sha256'] != digest:
            raise ValueError('Frozen source fingerprint changed: ' + rel)
        manifest.append(dict(path=rel, sha256=digest, bytes=p.stat().st_size,
                             source_url=scope_url.get(rel, frozen.get(rel, {}).get('source_url', '')),
                             frozen_source_receipt_verified=int(rel in frozen)))
    rows = read_inventory()
    legacy_unmatched = {d['NYISO Name']: d for d in read_csv(PARENT / 'thermalGenNotMatched_2019.csv')}
    for name in ['74 St.  GT 1', '74 St.  GT 2']:
        d = legacy_unmatched[name]
        if d['Zone'] != 'J' or distance_km(float(d['Latitude']), float(d['Longitude']), 40.768, -73.9515) > .1:
            raise ValueError('74th Street source identity/zone evidence changed')
    buses = [dict(bus_id=int(d['idx']), name=d['name'], zone=d['zone'],
                  latitude=float(d['ycoord']), longitude=float(d['xcoord']))
             for d in read_csv(BUS_FILE) if d['zone'] in 'ABCDEFGHIJK' and len(d['zone']) == 1]
    if len(buses) != 46 or {b['bus_id'] for b in buses} != set(range(37, 83)):
        raise ValueError('Expected unchanged 46 NY buses within 140-bus parent')
    bus_by_id = {b['bus_id']: b for b in buses}
    legacy = read_csv(LEGACY_FILE)
    legacy_by_row = {int(d['source_gen_row']): d for d in legacy}
    epa_rows = read_csv(EPA_FILE)
    for d in read_csv(EPA_ALL_FACILITIES):
        if int(d['Facility ID']) in CORROBORATED_OUTSIDE_PLANTS:
            epa_rows.append(dict(facility_id=d['Facility ID'], unit_id=d['Unit ID'],
                device_key=f"EPA:ORIS:{d['Facility ID']}:UNIT:{d['Unit ID']}",
                associated_generators=d['Associated Generators & Nameplate Capacity (MWe)'], zone='J'))
    links, link_evidence = identity_links(epa_rows, read_csv(XWALK_FILE))
    epa_legacy = defaultdict(set)
    for d in legacy:
        for ek in filter(None, d['candidate_EPA_device_keys'].split('|')):
            epa_legacy[ek].add(int(d['source_gen_row']))
    plant_legacy = defaultdict(set)
    source_zone_by_eia = defaultdict(set)
    epa_by_key = {d['device_key']: d for d in epa_rows}
    for k, keys in links.items():
        for ek in keys:
            plant_legacy[k[0]].update(epa_legacy[ek])
            z = epa_by_key.get(ek, {}).get('zone', '')
            if z in 'ABCDEFGHIJK' and len(z) == 1:
                source_zone_by_eia[k].add(z)
    landings, associations = [], []
    for i, row in enumerate(rows, 1):
        row['fleet_id'] = i
        k = (row['plant_id'], row['eia_generator_id'])
        keys = links[k]
        legacy_ids = set().union(*(epa_legacy[ek] for ek in keys)) if keys else set()
        identity_method = 'EPA_EIA_to_unique_legacy_bus_identity_continuity_assumed'
        if k in REACTOR_ROWS:
            legacy_ids = {REACTOR_ROWS[k]}
            identity_method = 'explicit_reactor_identity_in_pinned_2019_constructor'
        elif row['plant_id'] in HYDRO_PLANT_ROWS:
            legacy_ids = {HYDRO_PLANT_ROWS[row['plant_id']]}
            identity_method = 'explicit_major_hydro_site_legacy_aggregate_split_unique_EIA_units'
        elif k in {(2504, 'GT1'), (2504, 'GT2')}:
            # Exact NYISO name, generator ID and coincident site coordinates;
            # these units were missing from the legacy matched-EPA workbook.
            legacy_ids = {2 if k[1] == 'GT1' else 3}
            identity_method = '74th_Street_exact_generator_name_and_site_coordinate_join'
        # Contemporary source-zone metadata improves county proxies, with no
        # change to the parent's zone labels or bus identities.
        if len(source_zone_by_eia[k]) == 1 and row['fuel_category'] == 'Combined Fossil' and row['inventory_state'] == 'NY':
            row['zone'] = next(iter(source_zone_by_eia[k]))
            row['zone_mapping_policy'] = 'EPA_NYGRID_source_identity_zone_continuity_assumed'
        if row['plant_id'] == 57185:
            row['zone'], row['zone_mapping_policy'] = 'G', 'declared_EPA_GoldBook_CricketValley_site_zone'
            # The EPA labels CT1/ST1 are not the EIA generator IDs U001..U006.
            # Preserve facility associations without inventing a unit crosswalk.
            keys = {d['device_key'] for d in epa_rows if d['facility_id'] == '57185'}
            link_evidence[k] = {'facility_level_only_EPA_CT_ST_labels_differ_from_EIA_U00x_ids'}
        if row['plant_id'] == 2504:
            row['zone'], row['zone_mapping_policy'] = 'J', 'EIA_74th_Street_New_York_County_coordinates_and_legacy_NYISO_zone_J'
        candidates = {int(legacy_by_row[j]['full_source_bus']) for j in legacy_ids}
        has_landing = row['zone'] in set('ABCDEFGHIJK')
        if not has_landing:
            bus, dist, method, proxy = 0, '', 'no_native_landing_for_excluded_external_or_unverified_market_record', 1
        elif len(candidates) == 1:
            bus = next(iter(candidates))
            method, proxy = identity_method, 0
            dist = distance_km(row['latitude'], row['longitude'], bus_by_id[bus]['latitude'], bus_by_id[bus]['longitude']) if row['coordinates_available'] else ''
        else:
            plant_rows = plant_legacy[row['plant_id']]
            plant_buses = {int(legacy_by_row[j]['full_source_bus']) for j in plant_rows}
            if not legacy_ids and len(plant_buses) == 1:
                bus, dist = next(iter(plant_buses)), ''
                method, proxy = 'same_EIA_plant_unique_legacy_bus_site_continuity_assumed', 1
            else:
                bus, dist, method = nearest_bus(row, buses)
                proxy = 1
        parent_name = bus_by_id[bus]['name'] if has_landing else ''
        parent_zone = bus_by_id[bus]['zone'] if has_landing else ''
        row.update(bus_id=bus, has_parent_landing=int(has_landing), parent_bus_name=parent_name, parent_bus_zone=parent_zone,
            mapping_method=method, bus_landing_proxy=proxy, mapping_distance_km=dist,
            source_zone_parent_bus_zone_conflict=int(has_landing and row['zone'] != parent_zone),
            legacy_source_gen_rows=pipe(legacy_ids), legacy_candidate_bus_ids=pipe(candidates),
            legacy_mapping_ambiguous=int(len(candidates) > 1),
            EPA_device_keys=pipe(keys), EPA_association_policy=pipe(link_evidence[k]),
            capacity_duplicated_by_associations=0)
        row.update(native_scope_flags(row))
        scope_ok = bool(row['grid_scope_eligible'])
        eligible = scope_ok and row['fuel_category'] in {'Combined Fossil', 'Nuclear', 'Hydro', 'Wind', 'Other Renewables'}
        active_any = any(active_in_month(row, m) for m in range(1, 13))
        row.update(grid_scope_eligible=int(scope_ok), has_active_2025_month=int(active_any),
            dispatch_eligible_default=int(eligible and active_any and not row['is_storage']),
            pumped_hydro_prior_eligible=int(eligible and active_any and row['is_pumped_hydro']),
            capability_policy='reported_seasonal_net_capacity_without_nameplate_clipping_or_missing_capacity_imputation',
            availability_policy='OP_SB_or_preretirement_RE_only_start_month_excluded_retirement_month_excluded_OA_OS_off_assumed',
            storage_policy='pumped_hydro_default_off_may_use_prior_bounded_generation_only_no_pumping_or_SOC' if row['is_pumped_hydro'] else
                           'battery_off_no_energy_or_charge_history' if row['is_storage'] else 'not_storage',
            source_conflict_note='EIA2025_early_release_130MW_differs_from_owner132MW_and_GoldBook136MW_source_values_retained' if row['plant_id'] == 65561 else '')
        for season in ['summer', 'winter']:
            row['effective_' + season + '_capacity_mw'] = row[season + '_capacity_mw']
        row['seasonal_capacity_assumption'] = 'reported_values_used_missing_values_zero_no_generic_imputation'
        row['combined_cycle_capacity_aggregation_possible'] = int(
            row['prime_mover'] in {'CA', 'CT', 'CS', 'CC'} and
            (not row['summer_capacity_reported'] or not row['winter_capacity_reported']))
        if k == (2490, 'GT1'):
            # A simple turbine retired in May2025 retains public nameplate18MW
            # but has blank seasonal fields. Do not apply this fallback to CC
            # components: their companions may already report block capacity.
            for season in ['summer', 'winter']:
                if not row[season + '_capacity_reported']:
                    row['effective_' + season + '_capacity_mw'] = row['nameplate_capacity_mw']
            row['seasonal_capacity_assumption'] = 'ArthurKill_GT1_only_nameplate18MW_proxy_before_May2025_retirement_missing_seasonal_values'
            row['capability_policy'] = 'reported_nameplate_proxy_for_missing_seasonal_ArthurKill_GT1_only'
        for ek in sorted(keys):
            associations.append(dict(fleet_id=i, device_key=row['device_key'], EPA_device_key=ek,
                association_policy=row['EPA_association_policy'], capacity_mw_assigned_to_association=0,
                use_for_generation_allocation='plant_level_only' if row['plant_id'] == 57185 else 'requires_reporting_unit_partition_no_capacity_duplication'))
        landings.append({k: row[k] for k in ['fleet_id', 'device_key', 'plant_name', 'inventory_state', 'zone', 'bus_id', 'has_parent_landing', 'parent_bus_zone',
                        'mapping_method', 'bus_landing_proxy', 'mapping_distance_km', 'source_zone_parent_bus_zone_conflict',
                        'legacy_source_gen_rows', 'legacy_candidate_bus_ids', 'legacy_mapping_ambiguous']})
    axis = {int(d['hour_index']): d for d in read_csv(INPUT / 'load_source/load_hourly.csv')}
    if set(axis) != set(range(1, 8761)):
        raise ValueError('Incomplete 2025 canonical hour axis')
    months = np.array([datetime.fromisoformat(axis[h]['local_timestamp']).month for h in range(1, 8761)])
    physical = np.zeros((8760, len(rows)), dtype=np.float64)
    for j, row in enumerate(rows):
        for month in range(1, 13):
            if active_in_month(row, month):
                physical[months == month, j] = seasonal_capacity(row, month)
    pmax = physical * np.array([r['dispatch_eligible_default'] for r in rows])[None, :]
    pmin = np.zeros_like(pmax)
    data = dict(hour_index=np.arange(1, 8761, dtype=np.int32), fleet_id=np.arange(1, len(rows) + 1, dtype=np.int32),
                pmin_actual_mw=pmin, pmax_actual_mw=pmax, physical_pmax_actual_mw=physical,
                availability_assumed=np.ones(len(rows), dtype=np.uint8))
    if not np.isfinite(physical).all() or (physical < 0).any():
        raise ValueError('Invalid capability bounds')
    np.savez_compressed(out / 'fleet_bounds.npz', **data)
    savemat(out / 'fleet_bounds.mat', data, do_compression=True, oned_as='column')
    write_csv(out / 'fleet_register.csv', rows)
    write_csv(out / 'bus_landing_register.csv', landings)
    write_csv(out / 'epa_eia_association_register.csv', associations)
    lineage = []
    for old in legacy:
        j = int(old['source_gen_row'])
        matches = [r for r in rows if str(j) in r['legacy_source_gen_rows'].split('|')]
        lineage.append(dict(**old, mapped_2025_fleet_ids=pipe(r['fleet_id'] for r in matches),
            mapped_2025_device_keys=pipe(r['device_key'] for r in matches),
            lineage_policy='identity_associations_only_capacities_owned_by_unique_EIA_keys' if matches else
                           'legacy_aggregate_or_identity_unresolved_not_reactivated_or_copied'))
    write_csv(out / 'legacy_2019_lineage_register.csv', lineage)
    write_csv(out / 'source_manifest.csv', manifest)
    named = []
    for pid in [2497, 8907, 57185, 65561, 2504, 50006, 56964, 67086, 67087]:
        rr = [r for r in rows if r['plant_id'] == pid]
        jj = [r['fleet_id'] - 1 for r in rr]
        named.append(dict(plant_id=pid, plant_name=rr[0]['plant_name'], unique_generator_count=len(rr),
            default_dispatch_eligible_count=sum(r['dispatch_eligible_default'] for r in rr),
            generator_ids=pipe(r['eia_generator_id'] for r in rr), bus_ids=pipe(r['bus_id'] for r in rr),
            nameplate_capacity_mw=sum(r['nameplate_capacity_mw'] for r in rr),
            summer_capacity_mw=sum(r['summer_capacity_mw'] for r in rr),
            winter_capacity_mw=sum(r['winter_capacity_mw'] for r in rr),
            maximum_dispatch_upper_bound_actual_mw=float(pmax[:, jj].sum(axis=1).max()),
            EPA_association_policy=pipe(r['EPA_association_policy'] for r in rr)))
    write_csv(out / 'named_asset_audit.csv', named)
    write_csv(out / 'seasonal_capacity_gap_register.csv', [
        {k: r[k] for k in ['fleet_id', 'device_key', 'plant_name', 'source_status', 'prime_mover', 'eia_unit_code',
                          'nameplate_capacity_mw', 'summer_capacity_mw', 'winter_capacity_mw',
                          'summer_capacity_reported', 'winter_capacity_reported', 'effective_summer_capacity_mw',
                          'effective_winter_capacity_mw', 'seasonal_capacity_assumption',
                          'combined_cycle_capacity_aggregation_possible', 'dispatch_eligible_default']}
        for r in rows if not r['summer_capacity_reported'] or not r['winter_capacity_reported']])
    write_csv(out / 'balancing_authority_scope_register.csv', [
        {k: r[k] for k in ['fleet_id', 'device_key', 'plant_name', 'fuel_category', 'zone', 'bus_id',
                          'balancing_authority_code', 'sector_synchronization_scope_eligible',
                          'balancing_authority_scope_eligible', 'reported_other_balancing_authority',
                          'balancing_authority_metadata_missing', 'balancing_authority_independently_verified',
                          'balancing_authority_scope_policy', 'has_active_2025_month', 'dispatch_eligible_default',
                          'summer_capacity_mw', 'winter_capacity_mw', 'source_plant_excel_row', 'source_plant_sha256']}
        for r in rows if not r['balancing_authority_scope_eligible']])
    write_csv(out / 'outside_NY_scope_register.csv', [
        {k: r[k] for k in ['fleet_id', 'device_key', 'inventory_state', 'plant_id', 'eia_generator_id', 'plant_name',
            'balancing_authority_code', 'unit_market_scope_eligible', 'native_market_scope_status',
            'native_market_scope_evidence', 'market_scope_primary_corroborated', 'unit_market_overrides_plant_BA',
            'native_p63_scope_inferred', 'native_p63_unit_output_observed', 'nyiso_market_ptid',
            'boundary_generation_separation_policy', 'zone', 'bus_id', 'has_parent_landing', 'mapping_method',
            'nameplate_capacity_mw', 'summer_capacity_mw', 'winter_capacity_mw', 'dispatch_eligible_default',
            'source_excel_row', 'source_plant_excel_row', 'source_sha256', 'source_plant_sha256', 'EPA_device_keys']}
        for r in rows if r['inventory_state'] != 'NY'])
    summary = dict(status='complete_source_inventory_with_explicit_scenario_bounds_not_observed_availability',
        inventory_rows=len(rows), eia2025_rows=sum(r['inventory_kind'] == 'EIA860_2025_inventory' for r in rows),
        geographic_NY_EIA2025_rows=sum(r['inventory_kind'] == 'EIA860_2025_inventory' and r['inventory_state'] == 'NY' for r in rows),
        outside_NY_EIA2025_rows=sum(r['inventory_state'] != 'NY' for r in rows),
        outside_NY_default_admitted_rows=sum(r['inventory_state'] != 'NY' and r['dispatch_eligible_default'] for r in rows),
        outside_NY_scope_policy='Bayonne10_and_LindenGTG1_5_STG1_3_corroborated_ZoneJ; LindenGTG6_PJM_excluded; 2NJsolar_records_quarantined_no_zone_no_landing',
        no_parent_landing_audit_rows=sum(not r['has_parent_landing'] for r in rows),
        retired_tombstone_rows=2, unique_plant_generator_keys=len({(r['plant_id'], r['eia_generator_id']) for r in rows}),
        source_status_counts=dict(Counter(r['source_status'] for r in rows)), fuel_counts=dict(Counter(r['fuel_category'] for r in rows)),
        default_dispatch_eligible_rows=sum(r['dispatch_eligible_default'] for r in rows),
        reported_balancing_authority_counts=dict(Counter(r['balancing_authority_code'] for r in rows)),
        balancing_authority_scope_excluded_rows=sum(not r['balancing_authority_scope_eligible'] for r in rows),
        balancing_authority_scope_excluded_otherwise_eligible_rows=sum(
            not r['balancing_authority_scope_eligible'] and r['sector_synchronization_scope_eligible']
            and r['has_active_2025_month'] and not r['is_storage'] for r in rows),
        balancing_authority_scope_policy='reported_NYIS_only_no_exceptions; explicit_other_BA_or_missing_excluded_from_native_dispatch; reported_BA_not_independently_verified',
        physical_active_anytime_rows=sum(r['has_active_2025_month'] for r in rows),
        pumped_hydro_prior_eligible_rows=sum(r['pumped_hydro_prior_eligible'] for r in rows),
        landing_method_counts=dict(Counter(r['mapping_method'] for r in rows)),
        source_zone_parent_conflict_rows=sum(r['source_zone_parent_bus_zone_conflict'] for r in rows),
        legacy_rows_with_identity_associations=sum(bool(r['mapped_2025_fleet_ids']) for r in lineage),
        physical_maximum_annual_capacity_actual_mw=float(physical.sum(axis=1).max()),
        maximum_default_dispatch_capacity_actual_mw=float(pmax.sum(axis=1).max()),
        missing_seasonal_capacity_rows=sum(not r['summer_capacity_reported'] or not r['winter_capacity_reported'] for r in rows),
        seasonal_capacity_gap_policy='missing_CC_component_seasonal_values_zero_to_avoid_possible_block_duplication; ArthurKill_GT1_only_18MW_nameplate_proxy_before_retirement',
        arrays_shape=list(pmax.shape), units='actual MW; no gamma scaling in fleet builder',
        parent_bus_zone_policy='pinned_npcc.csv_46_NY_buses_in_140_bus_parent_no_topology_changes',
        season_policy='winter_November_through_March_summer_April_through_October',
        commissioning_policy='exclude_start_month_include_following_month; exclude_retirement_month',
        bounds_policy='0_to_reported_seasonal_net_capability; minimum_load_not_enforced_continuous_off_on_relaxation',
        storage_policy='battery_zero; pumped_hydro_zero_until_prior_bounded_generation_only_allocation; no_energy_SOC_model',
        renewable_policy='physical_capacity_ceiling_only; weather_and_nuclear_availability_priors_are_separate',
        scope_policy='reported_NYIS_and_unit_market_scope_and_utility_or_IPP_and_no_explicit_N_synchronization; other_BA_missing_BA_PJM_unit_exceptions_unverified_outside_state_market_commercial_industrial_Riverbay_excluded; solar_BTM_scope_unverified',
        release_limitation='2025 early release retrospective; intra_year_capacity_changes_and_forced_outages_not_reconstructed',
        named_assets=named)
    (out / 'fleet_summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ['inventory_rows', 'default_dispatch_eligible_rows', 'pumped_hydro_prior_eligible_rows',
                     'source_zone_parent_conflict_rows', 'maximum_default_dispatch_capacity_actual_mw']}))
    return rows, data, summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args()
    build(args.out)
