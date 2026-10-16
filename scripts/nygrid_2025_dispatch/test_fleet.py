"""Targeted identity, landing and temporal-capability checks."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_fleet as f


class FleetTests(unittest.TestCase):
    def row(self, **overrides):
        r = dict(source_status='OP', operating_year=2020, operating_month=4,
                 retirement_year=0, retirement_month=0, summer_capacity_mw=90., winter_capacity_mw=100.)
        r.update(overrides)
        return r

    def test_status_and_month_boundaries(self):
        self.assertFalse(f.active_in_month(self.row(operating_year=2025, operating_month=4), 4))
        self.assertTrue(f.active_in_month(self.row(operating_year=2025, operating_month=4), 5))
        r = self.row(source_status='RE', retirement_year=2025, retirement_month=6)
        self.assertTrue(f.active_in_month(r, 5))
        self.assertFalse(f.active_in_month(r, 6))
        for status in ['OA', 'OS', 'CN', 'IP']:
            self.assertFalse(f.active_in_month(self.row(source_status=status), 1))
        self.assertFalse(f.active_in_month(self.row(operating_year=0), 1))

    def test_capacity_retains_source_season_not_nameplate(self):
        r = self.row(nameplate_capacity_mw=80.)
        self.assertEqual(f.seasonal_capacity(r, 1), 100.)
        self.assertEqual(f.seasonal_capacity(r, 4), 90.)
        self.assertEqual(f.seasonal_capacity(r, 11), 100.)

    def test_missing_seasonal_is_not_reported_zero(self):
        self.assertFalse(f.reported({'cap': ' '}, 'cap'))
        self.assertTrue(f.reported({'cap': 0}, 'cap'))
        r = self.row(summer_capacity_mw=0., effective_summer_capacity_mw=18.)
        self.assertEqual(f.seasonal_capacity(r, 4), 18.)

    def test_operating_grid_generator_in_other_ba_is_not_native_dispatch(self):
        r = self.row(plant_id=123, sector='IPP Non-CHP', synchronized_to_transmission_grid='Y',
                     balancing_authority_code='ISNE')
        flags = f.native_scope_flags(r)
        self.assertTrue(f.active_in_month(r, 1))
        self.assertEqual(flags['sector_synchronization_scope_eligible'], 1)
        self.assertEqual(flags['balancing_authority_scope_eligible'], 0)
        self.assertEqual(flags['reported_other_balancing_authority'], 1)
        self.assertEqual(flags['grid_scope_eligible'], 0)
        r['balancing_authority_code'] = 'NYIS'
        self.assertEqual(f.native_scope_flags(r)['grid_scope_eligible'], 1)
        r['balancing_authority_code'] = ''
        self.assertEqual(f.native_scope_flags(r)['grid_scope_eligible'], 0)
        self.assertEqual(f.native_scope_flags(r)['balancing_authority_metadata_missing'], 1)

    def test_outside_state_requires_unit_market_corroboration(self):
        r = self.row(plant_id=50006, eia_generator_id='GTG1', inventory_state='NJ',
                     sector='IPP CHP', synchronized_to_transmission_grid='X', balancing_authority_code='NYIS')
        self.assertEqual(f.native_scope_flags(r)['grid_scope_eligible'], 1)
        r['eia_generator_id'] = 'GTG6'
        flags = f.native_scope_flags(r)
        self.assertEqual(flags['balancing_authority_scope_eligible'], 1)
        self.assertEqual(flags['unit_market_scope_eligible'], 0)
        self.assertEqual(flags['grid_scope_eligible'], 0)
        r.update(plant_id=67086, eia_generator_id='P6132')
        self.assertEqual(f.native_scope_flags(r)['grid_scope_eligible'], 0)
        r.update(plant_id=56964, eia_generator_id='GT10')
        flags = f.native_scope_flags(r)
        self.assertEqual(flags['grid_scope_eligible'], 1)
        self.assertEqual(flags['nyiso_market_ptid'], '323750')
        r['eia_generator_id'] = 'UNKNOWN'
        self.assertEqual(f.native_scope_flags(r)['grid_scope_eligible'], 0)

    def test_many_to_many_is_annotation_not_capacity_expansion(self):
        epa = [dict(facility_id='1', device_key='EPA:ORIS:1:UNIT:A', associated_generators='G1 (10), G2 (20)')]
        xw = [dict(EIA_PLANT_ID='1', EIA_GENERATOR_ID='G1', CAMD_PLANT_ID='1', CAMD_UNIT_ID='A')]*3
        links, _ = f.identity_links(epa, xw)
        self.assertEqual(links[(1, 'G1')], {'EPA:ORIS:1:UNIT:A'})
        self.assertEqual(links[(1, 'G2')], {'EPA:ORIS:1:UNIT:A'})
        fleet = [dict(plant_id=1, eia_generator_id='G1', cap=10), dict(plant_id=1, eia_generator_id='G2', cap=20)]
        self.assertEqual(sum(r['cap'] for r in f.unique_inventory(fleet)), 30)
        with self.assertRaises(ValueError):
            f.unique_inventory(fleet + [fleet[0]])

    def test_cricket_valley_reporting_label_is_not_eia_id(self):
        links, _ = f.identity_links([dict(facility_id='57185', device_key='EPA:ORIS:57185:UNIT:U001',
                                         associated_generators='CT1 (236.3), ST1 (174.3)')], [])
        self.assertEqual(links[(57185, 'U001')], set())
        self.assertEqual(links[(57185, 'CT1')], {'EPA:ORIS:57185:UNIT:U001'})

    def test_same_zone_landing_and_tie_are_deterministic(self):
        row = dict(zone='G', latitude=42., longitude=-74., coordinates_available=1)
        buses = [dict(bus_id=70, zone='F', latitude=42., longitude=-74.),
                 dict(bus_id=76, zone='G', latitude=41., longitude=-74.),
                 dict(bus_id=75, zone='G', latitude=41., longitude=-74.)]
        self.assertEqual(f.nearest_bus(row, buses)[0], 75)
        self.assertEqual(f.nearest_bus(row, list(reversed(buses)))[0], 75)


if __name__ == '__main__':
    unittest.main()
