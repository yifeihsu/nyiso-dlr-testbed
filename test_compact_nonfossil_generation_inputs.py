"""Focused time, identity, vintage, provenance and accounting tests.

The saved-output tests independently reconcile source-derived aggregates and
verify all recorded bytes. They never read NYISO internal interface targets.
Run: python -m unittest -v test_compact_nonfossil_generation_inputs
"""
import csv
from collections import defaultdict
from datetime import datetime,timedelta
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest

import build_compact_nonfossil_generation_inputs as n


def read(name):
    with (n.DEFAULT_OUT/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def verify_selected_nonfossil_evidence(output_dir=n.DEFAULT_OUT,repository_root=n.ROOT,check_optional_raw_cache=True):
    """Mandatory committed bytes and source linkage; optional original cache.

    The original archive SHA256 remains a provenance assertion when raw files
    are absent. This does not claim to reproduce their original-byte check.
    """
    output_dir=Path(output_dir);repository_root=Path(repository_root)
    def table(name):
        with (output_dir/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    manifest=table('source_manifest.csv');sources={r['source_id']:r for r in manifest}
    assert len(sources)==len(manifest) and sources,'Duplicate or empty source manifest'
    for r in manifest:
        assert len(r['sha256'])==64 and set(r['sha256'])<=set('0123456789abcdef'),'Invalid original source SHA256'
    artifacts=table('output_manifest.csv');linked=0;raw_checked=0
    pairs=[('source_id','source_sha256'),('capacity_source_id','capacity_source_sha256'),
           ('eia_capacity_source_id','eia_capacity_source_sha256'),
           ('monthly_source_ids','monthly_source_sha256'),('capacity_source_ids','capacity_source_sha256')]
    for item in artifacts:
        path=output_dir/item['artifact']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],'Changed committed output: '+item['artifact']
        if path.suffix!='.csv' or path.name=='source_manifest.csv':continue
        for r in table(path.name):
            for id_field,hash_field in pairs:
                if id_field not in r:continue
                ids={x for x in r[id_field].split(';') if x};hashes={x for x in r[hash_field].split(';') if x}
                assert ids<=sources.keys(),'Unknown source identity in '+path.name
                assert hashes=={sources[k]['sha256'] for k in ids},'Source ID/hash linkage changed in '+path.name
                linked+=bool(ids)
            if 'allocation_source_ids' in r:
                assert {x for x in r['allocation_source_ids'].split(';') if x}<=sources.keys(),'Unknown allocation source'
    if check_optional_raw_cache:
        for r in manifest:
            # Serialized Windows separators are metadata, not POSIX literals.
            path=Path(r['local_cache'].replace('\\','/'))
            path=path if path.is_absolute() else repository_root/path
            if path.is_file():
                assert hashlib.sha256(path.read_bytes()).hexdigest()==r['sha256'],'Changed original source: '+r['source_id']
                raw_checked+=1
    return dict(committed_artifacts=len(artifacts),linked_records=linked,original_raw_files_verified=raw_checked)


class TimeAndIdentityTests(unittest.TestCase):
    def test_irregular_duration_not_sample_mean(self):
        t=datetime(2025,1,1,12)
        # First 3 minutes at 10 MW and last 7 minutes at 30 MW = 24 MW.
        samples=[(t,999,1),(t+timedelta(minutes=3),10,2),(t+timedelta(minutes=10),30,3)]
        mean,coverage,count,gap=n.integrate_samples(samples,t,t+timedelta(minutes=10))
        self.assertAlmostEqual(mean,24);self.assertEqual((coverage,count,gap),(600,2,420))

    def test_long_gap_not_bridged(self):
        t=datetime(2025,1,1,12)
        samples=[(t,100,1),(t+timedelta(minutes=11),200,2),(t+timedelta(minutes=16),300,3)]
        mean,coverage,_,gap=n.integrate_samples(samples,t,t+timedelta(minutes=16))
        self.assertEqual(coverage,300);self.assertEqual(mean,300);self.assertEqual(gap,660)

    def test_partial_interval_clip(self):
        t=datetime(2025,1,1,12)
        self.assertEqual(n.integrate_samples([(t,0,1),(t+timedelta(minutes=5),12,2)],
                         t+timedelta(minutes=1),t+timedelta(minutes=4))[:2],(12,180))

    def test_duplicate_time_rejected(self):
        t=datetime(2025,1,1,12)
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            n.integrate_samples([(t,1,1),(t,2,2)],t,t+timedelta(hours=1))

    def test_no_future_new_capacity(self):
        d=dict(operating_year=2025,operating_month=7,source_status='OP',retirement_year=0,retirement_month=0)
        self.assertFalse(n.is_active(d,datetime(2025,7,29)))
        self.assertTrue(n.is_active(d,datetime(2025,8,1)))
        d.update(operating_year=2000,source_status='RE',retirement_year=2025,retirement_month=4)
        self.assertTrue(n.is_active(d,datetime(2025,1,1)))
        self.assertFalse(n.is_active(d,datetime(2025,4,1)))

    def test_site_identity_overrides_county(self):
        self.assertEqual(n.plant_zone(65496,'BLUES','Broome','WND')[0],'E')
        self.assertEqual(n.plant_zone(56953,'1','Wyoming','WND')[0],'C')
        self.assertEqual(n.plant_zone(2694,'','St Lawrence','WAT')[0],'D')
        self.assertEqual(n.plant_zone(6122,'1','Wayne','NUC')[0],'B')
        self.assertEqual(n.plant_zone(2691,'1','Schoharie','WAT')[0],'F')
        self.assertEqual(n.plant_zone(2692,'1','Niagara','WAT')[0],'A')

    def test_hydro_generation_capability_and_residual_storage(self):
        values,ok=n.bounded_hydro_projection([60.,40.,0.],[100.,50.,150.],180.)
        self.assertTrue(ok);self.assertEqual(values,[76.,44.,60.]);self.assertEqual(sum(values),180)
        low,ok=n.bounded_hydro_projection([60.,40.,0.],[100.,50.,150.],50.)
        self.assertEqual(low,[30.,20.,0.]);self.assertTrue(ok)

    def test_hydro_baseline_above_capacity_is_clipped(self):
        values,ok=n.bounded_hydro_projection([200.,100.,0.],[100.,50.,150.],270.)
        self.assertTrue(ok);self.assertEqual(values,[100.,50.,120.])
        values,ok=n.bounded_hydro_projection([200.,100.,0.],[100.,50.,150.],301.)
        self.assertFalse(ok);self.assertTrue(all(math.isnan(v) for v in values))
        with self.assertRaisesRegex(ValueError,'Invalid'):n.bounded_hydro_projection([-1.],[10.],1.)

    def test_nrc_status_requires_unique_and_valid_percentage(self):
        data=b'<table><tr><td>Ginna</td><td>0</td><td>Refueling</td></tr></table>'
        self.assertEqual(n.parse_nrc(data)['Ginna'],(0.,'Refueling'))
        with self.assertRaisesRegex(ValueError,'Duplicate'):n.parse_nrc(data+data)
        with self.assertRaisesRegex(ValueError,'Invalid'):n.parse_nrc(data.replace(b'<td>0',b'<td>999'))

    def test_solar_weight_dark_at_night(self):
        self.assertEqual(n.solar_weight(datetime(2025,7,25,4,30),42,-75,'EDT'),0)
        self.assertEqual(n.solar_weight(datetime(2025,1,22,18,30),42,-75,'EST'),0)
        self.assertGreater(n.solar_weight(datetime(2025,4,15,13,30),42,-75,'EDT'),.7)

    def test_metadata_projection_ignores_interface_related_columns(self):
        protocol=n.ROOT/'output/compact_ny_2025/generation_sources/generation_reconstruction_protocol.json'
        rows=[r for r in read('registered_hours.csv') if r['selection_role']=='historical_or_revisited_diagnostic']
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'meta.csv';n.write_csv(path,rows)
            expected=n.registered_hours(path,protocol)
            for r in rows:
                for k in ['interface_value','source_selection_basis','p32_source_id','selection_role']:r[k]='ADVERSARIAL_UNREAD_VALUE'
            n.write_csv(path,rows)
            self.assertEqual(n.registered_hours(path,protocol),expected)
            rows[0]['timestamp_utc']='2019-07-20T21:00:00Z';n.write_csv(path,rows)
            with self.assertRaisesRegex(ValueError,'Timestamp'):n.registered_hours(path,protocol)


class SavedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Missing source artifacts are a failure, never a silent skipped audit.
        cls.hours=read('registered_hours.csv');cls.priors=read('zonal_nonfossil_priors.csv')
        cls.hourly=read('statewide_fuelmix_hourly.csv');cls.inventory=read('eia860_nonfossil_inventory.csv')
        cls.nuclear=read('nrc_daily_reactor_inputs.csv');cls.hydro=read('eia923_monthly_hydro.csv')
        cls.hydro_plants=read('hydro_plant_hourly_estimates.csv')

    def test_registered_dimensions_and_primary_window(self):
        self.assertEqual(len(self.hours),16);self.assertEqual(len(self.priors),704)
        self.assertEqual(len(self.hourly),224)
        self.assertEqual({d['window_policy'] for d in self.priors},{'hour_beginning'})
        self.assertEqual(len({d['scenario_id'] for d in self.hours if d['selection_role']=='preregistered_calendar_validation'}),4)

    def test_preserved_fossil_categories(self):
        for h in self.hours:
            fuels={d['fuel_category'] for d in self.hourly if d['scenario_id']==h['scenario_id']}
            self.assertTrue({'Dual Fuel','Natural Gas','Other Fossil Fuels'}.issubset(fuels))

    def test_every_source_and_output_fingerprint(self):
        result=verify_selected_nonfossil_evidence()
        self.assertGreater(result['linked_records'],10000)
        self.assertGreaterEqual(result['committed_artifacts'],13)

    def test_committed_evidence_still_checked_without_raw_cache(self):
        with tempfile.TemporaryDirectory() as td:
            result=verify_selected_nonfossil_evidence(repository_root=Path(td))
            self.assertEqual(result['original_raw_files_verified'],0)
            self.assertGreater(result['linked_records'],10000)

    def test_rehashed_selected_table_cannot_change_source_identity(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'nonfossil';shutil.copytree(n.DEFAULT_OUT,out)
            path=out/'statewide_fuelmix_raw_samples.csv'
            with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
            rows[0]['source_sha256']='0'*64;n.write_csv(path,rows)
            with (out/'output_manifest.csv').open(encoding='utf-8-sig',newline='') as f:manifest=list(csv.DictReader(f))
            for r in manifest:
                if r['artifact']==path.name:r['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            n.write_csv(out/'output_manifest.csv',manifest)
            with self.assertRaisesRegex(AssertionError,'Source ID/hash linkage'):
                verify_selected_nonfossil_evidence(out,repository_root=Path(td),check_optional_raw_cache=False)

    def test_independent_public_and_benchmark_conservation(self):
        totals={(d['scenario_id'],d['fuel_category']):d for d in self.hourly if d['window_policy']=='hour_beginning'}
        groups=defaultdict(list)
        for d in self.priors:
            self.assertEqual(d['zonal_generation_observed'],'0');self.assertEqual(d['geographic_estimate'],'1')
            groups[(d['scenario_id'],d['fuel_category'])].append(d)
        for key,rows in groups.items():
            self.assertEqual({d['zone'] for d in rows},set('ABCDEFGHIJK'))
            self.assertAlmostEqual(sum(float(d['allocation_share']) for d in rows),1)
            obs=totals[key]
            if obs['coverage_qualified']=='1':
                self.assertAlmostEqual(sum(float(d['prior_public_mw']) for d in rows),float(obs['duration_weighted_generation_mw']),places=7)
                self.assertAlmostEqual(sum(float(d['prior_benchmark_mw']) for d in rows),float(obs['duration_weighted_generation_mw'])*float(rows[0]['scale_factor_gamma']),places=7)
            else:self.assertTrue(all(math.isnan(float(d['prior_public_mw'])) for d in rows))

    def test_nuclear_vintage_and_no_future_daily_report(self):
        for h in self.hours:
            units=[d for d in self.nuclear if d['scenario_id']==h['scenario_id']]
            self.assertEqual(len(units),6 if h['vintage']=='2019' else 4)
            dt=datetime.fromisoformat(h['timestamp'])
            expected=dt.date() if dt.hour>=8 else (dt-timedelta(days=1)).date()
            for d in units:
                self.assertEqual(d['nrc_report_date'],str(expected));self.assertEqual(d['hourly_output_observed'],'0')
                self.assertAlmostEqual(float(d['estimated_available_net_mw']),float(d['seasonal_net_capacity_mw'])*float(d['report_power_percent'])/100)
            if h['vintage']=='2025':self.assertFalse(any('Indian Point' in d['reactor_name'] for d in units))

    def test_hydro_monthly_sign_and_location_accounting(self):
        for y in ['2019','2025']:
            for month in ['1','4','7']:
                major=[d for d in self.hydro if d['vintage']==y and d['month']==month and d['plant_id'] in {'2693','2694'}]
                self.assertEqual(len(major),2)
                self.assertEqual({d['estimated_zone'] for d in major},{'A','D'})
                self.assertTrue(all(d['monthly_generation_observed']=='1' for d in major))
        for d in self.hydro:
            if d['prime_mover']=='PS' or d['plant_id']=='99999' or float(d['net_generation_mwh'])<=0:
                self.assertEqual(float(d['share_weight_mwh']),0);self.assertEqual(d['allocation_eligible'],'0')
            if d['respondent_frequency']!='M':self.assertEqual(d['monthly_generation_observed'],'0')

    def test_hydro_2025_july_primary_source_spot_check(self):
        # Independently inspected official EIA923 July plant row, not a formula copy.
        rows=[d for d in self.hydro if (d['vintage'],d['month'],d['plant_id'])==('2025','7','2693')]
        self.assertEqual(len(rows),1);self.assertEqual(float(rows[0]['net_generation_mwh']),1201507)

    def test_all_hydro_plant_hours_respect_capability_and_statewide_total(self):
        groups=defaultdict(list)
        for d in self.hydro_plants:
            groups[d['scenario_id']].append(d)
            value=float(d['estimated_generation_mw']);cap=float(d['seasonal_capacity_mw'])
            self.assertEqual(d['hourly_generation_observed'],'0')
            if d['generation_capability_qualified']=='1':self.assertTrue(-1e-8<=value<=cap+1e-8)
            else:self.assertTrue(math.isnan(value))
            if d['plant_id']=='2691':self.assertEqual(d['zone'],'F')
            if d['prime_mover']=='PS':
                self.assertEqual(float(d['positive_conventional_baseline_mw']),0)
                self.assertEqual(d['storage_energy_observed'],'0')
        for rows in groups.values():
            if rows[0]['allocation_qualified']=='1':
                self.assertAlmostEqual(sum(float(d['estimated_generation_mw']) for d in rows),float(rows[0]['statewide_observed_hydro_mw']),places=7)

    def test_high_hydro_hour_includes_bounded_gilboa_residual(self):
        rows=[d for d in self.hydro_plants if d['scenario_id']=='S1_2025_SUMMER_PEAK_PUBLIC']
        gilboa=next(d for d in rows if d['plant_id']=='2691')
        stlawrence=next(d for d in rows if d['plant_id']=='2694')
        self.assertGreater(float(gilboa['estimated_generation_mw']),0)
        self.assertLess(float(gilboa['monthly_mean_net_mw']),0)
        self.assertLessEqual(float(stlawrence['estimated_generation_mw']),856.)

    def test_eia_keys_and_retirement_identity(self):
        keys=[d['device_key'] for d in self.inventory];self.assertEqual(len(keys),len(set(keys)))
        sf=[d for d in self.inventory if d['plant_id']=='65561']
        self.assertEqual(len(sf),1);self.assertEqual(sf[0]['vintage'],'2025');self.assertEqual(sf[0]['estimated_zone'],'K')
        self.assertEqual(float(sf[0]['nameplate_capacity_mw']),130)
        self.assertEqual({d['release_status'] for d in self.inventory if d['vintage']=='2025'},{'early_release'})

    def test_named_south_fork_is_subset_without_double_counting(self):
        rows=read('named_renewable_priors.csv');self.assertEqual(len(rows),16)
        for d in rows:
            self.assertEqual(d['zone'],'K');self.assertEqual(d['subset_of_zone_fuel_prior'],'1')
            self.assertEqual(d['model_generator_key'],'NY2025:GEN:SOUTH_FORK:K9003')
            value=float(d['prior_public_mw']);parent=float(d['parent_zone_fuel_prior_public_mw'])
            self.assertTrue(0<=value<=parent+1e-8)
            self.assertAlmostEqual(value,float(d['statewide_observed_wind_mw'])*float(d['active_nameplate_capacity_mw'])/float(d['statewide_active_wind_capacity_mw']))
            self.assertAlmostEqual(float(d['prior_benchmark_mw']),value*float(d['scale_factor_gamma']))
            if d['vintage']=='2019':self.assertEqual(value,0);self.assertEqual(d['active_in_source_vintage'],'0')
            else:self.assertEqual(float(d['active_nameplate_capacity_mw']),130)


if __name__=='__main__':unittest.main(verbosity=2)
