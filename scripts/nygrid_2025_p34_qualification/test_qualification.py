"""Check that documentary uncertainty cannot silently become physical evidence."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from qualification import CONTRACT, OUT, PTIDS, inspect_use, load_contract, sha


class QualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = load_contract()

    def test_conditional_research_is_available(self):
        result = inspect_use(self.contract, 'conditional_dc')
        self.assertTrue(result['allowed'])
        self.assertEqual(result['retained_policy']['interval_energy_multiplier'], 1)
        self.assertFalse(result['numeric_data_changed'])

    def test_units_cannot_be_promoted_by_plausibility(self):
        for ptid in PTIDS:
            with self.subTest(ptid=ptid):
                self.assertFalse(inspect_use(self.contract, 'verified_native_MW', [ptid])['allowed'])

    def test_four_channels_are_not_certified_meters(self):
        for ptid in PTIDS:
            with self.subTest(ptid=ptid):
                self.assertFalse(inspect_use(self.contract, 'measured_physical_telemetry', [ptid])['allowed'])

    def test_effective_date_is_device_specific(self):
        self.assertTrue(inspect_use(self.contract, 'historically_verified_sign', [25118, 25119])['allowed'])
        self.assertFalse(inspect_use(self.contract, 'historically_verified_sign', [625149, 625150])['allowed'])
        self.assertFalse(inspect_use(self.contract, 'historically_verified_sign')['allowed'])

    def test_active_flow_does_not_certify_thermal_state(self):
        hypothetical = deepcopy(self.contract)
        hypothetical['native_numeric_MW_unit_verified'] = True
        hypothetical['actual_measurement_origin_verified'] = True
        hypothetical['native_timestamp_support_verified'] = True
        for channel in hypothetical['channels']:
            channel['historical_2025_sign_verified'] = True
        result = inspect_use(hypothetical, 'physical_thermal_validation')
        self.assertFalse(result['allowed'])
        self.assertEqual(len(result['reasons']), 1)
        self.assertIn('active flow alone', result['reasons'][0])

    def test_unknown_device_or_policy_refused(self):
        for use, ptids in [('conditional_dc', [999]), ('conditional_dc', []), ('automatic_factor12', [25118])]:
            with self.subTest(use=use, ptids=ptids), self.assertRaises(ValueError):
                inspect_use(self.contract, use, ptids)

    def test_bad_contract_refused(self):
        variants = []
        bad = deepcopy(self.contract); bad['channels'].append(bad['channels'][0]); variants.append(bad)
        bad = deepcopy(self.contract); bad['channels'][0]['raw_to_NY_export_multiplier'] = 1; variants.append(bad)
        bad = deepcopy(self.contract); bad['raw_numeric_policy']['interval_energy_multiplier'] = 12; variants.append(bad)
        bad = deepcopy(self.contract); bad['dependencies'][next(iter(bad['dependencies']))] = '0' * 64; variants.append(bad)
        bad = deepcopy(self.contract); bad['dependencies'] = {}; variants.append(bad)
        bad = deepcopy(self.contract); bad['native_numeric_MW_unit_verified'] = True; variants.append(bad)
        bad = deepcopy(self.contract); bad['actual_measurement_origin_verified'] = True; variants.append(bad)
        bad = deepcopy(self.contract); bad['native_timestamp_support_verified'] = True; variants.append(bad)
        bad = deepcopy(self.contract); bad['channels'][2]['historical_2025_sign_verified'] = True; variants.append(bad)
        bad = deepcopy(self.contract); bad['channels'][2]['explicit_effective_date'] = '2024-12-03'; variants.append(bad)
        bad = deepcopy(self.contract); bad['raw_numeric_policy']['gamma'] = 1; variants.append(bad)
        bad = deepcopy(self.contract); bad['raw_numeric_policy']['time_aggregation'] = 'fill_missing_zero'; variants.append(bad)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'contract.json'
            for i, bad in enumerate(variants):
                path.write_text(json.dumps(bad), encoding='utf-8')
                with self.subTest(variant=i), self.assertRaises(ValueError):
                    load_contract(path)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(QualificationTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = dict(passed=result.wasSuccessful(), tests=result.testsRun,
                   contract_sha256=sha(CONTRACT),
                   dependencies={str(p.relative_to(OUT.parents[1])).replace('\\', '/'): sha(p)
                                 for p in [CONTRACT, Path(__file__), Path(__file__).with_name('qualification.py')]})
    (OUT / 'qualification_validation.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
