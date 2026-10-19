"""Export full-precision current-model annual series for the offline map.

Reads sealed annual results and the latest consolidated input bundle. It does
not solve PF/OPF, retune an interface definition, or expose failed iterates as
predictions. Original sources and earlier maps are never modified.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from repair_paths import ANNUAL, COMPARISON, REPAIR, RUN_LABEL

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'output/nygrid_2025_physical_repair/delivery/map'
HANDOFF = REPAIR
ALIGNMENT = ROOT / 'output/nygrid_2025_acpf_profile_audit/alignment'
STATES = ['pre_may', 'may21', 'may30', 'post_dover']
ZONES = list('ABCDEFGHIJK')
CONVENTIONS = ['legacy_signed_literal_from', 'oriented_source_side', 'oriented_target_side']
FLAG_NAMES = ['source_qualified', 'PF_attempted', 'PF_converged', 'AC_equation_gate', 'loss_allocation_gate',
              'reduction_and_equation_gate', 'VQ_and_generator_assumption_gate', 'solver_exception']
MONTH_FIELDS = ['hour_index', 'timestamp_utc', 'gamma', 'topology_state_index',
    'branch_keys', 'branch_parent_row', 'branch_from_bus', 'branch_to_bus', 'branch_present', 'branch_active',
    'bus_id', 'base_kv', 'bus_present', 'generator_bus_id', 'external_generator_rows_1based', 'external_gen_PG',
    'PF', 'PT', 'PD', 'bus_PG', 'DC_PF', 'DC_PT', 'NY_gross_target_MW', 'NY_served_PD_MW', 'actual_budget_MW',
    'loss_status', *FLAG_NAMES]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(path):
    path = Path(path)
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size, sha256=sha(path))


def strings(value):
    return np.array(['' if isinstance(v, np.ndarray) and v.size == 0 else str(v)
                     for v in np.asarray(value, dtype=object).reshape(-1)], dtype=str)


def vector(m, field, dtype=float):
    return np.asarray(m[field], dtype=dtype).reshape(-1)


def maxabs(value):
    value = np.asarray(value, dtype=float)
    assert np.isfinite(value).all()
    return float(np.max(np.abs(value), initial=0))


def nullable(value):
    a = np.asarray(value, dtype=float)
    return [[float(v) if np.isfinite(v) else None for v in row] for row in a]


def masked(value, mask):
    a = np.asarray(value, dtype=float).copy()
    a[~mask] = np.nan
    return a


def frozen_file_check(path, entries):
    relative = path.relative_to(ROOT).as_posix()
    hits = [r for r in entries if str(r['path']).replace('\\', '/') in [relative, path.as_posix()]]
    assert len(hits) == 1, f'No unique sealed source record: {relative}'
    assert sha(path) == hits[0]['sha256'], f'Changed sealed source: {relative}'


def operator_weights(terms, keys, parents, from_bus, to_bus, names, state):
    """Join by canonical runtime key; state row positions are not reusable."""
    lookup = {key: i for i, key in enumerate(keys)}
    weights = {name: {'PF': np.zeros((7, len(keys))), 'PT': np.zeros((7, len(keys)))} for name in CONVENTIONS}
    selected = terms.loc[terms.state.eq(state)]
    assert len(selected) == 34
    for term in selected.itertuples(index=False):
        j = names.index(term.interface)
        first = lookup[term.first_runtime_branch_key]; last = lookup[term.last_runtime_branch_key]
        assert parents[first] == parents[last] == term.original_branch_row
        assert from_bus[first] == term.original_from_bus and to_bus[last] == term.original_to_bus
        sign = int(term.coefficient); assert sign in (-1, 1)
        weights[CONVENTIONS[0]]['PF'][j, first] += sign
        if sign > 0:
            weights[CONVENTIONS[1]]['PF'][j, first] += 1
            weights[CONVENTIONS[2]]['PT'][j, last] -= 1
        else:
            weights[CONVENTIONS[1]]['PT'][j, last] += 1
            weights[CONVENTIONS[2]]['PF'][j, first] -= 1
    return weights, selected.original_branch_row.to_numpy(int)


def apply_weights(pf, pt, weights):
    answer = {}
    for convention, matrices in weights.items():
        result = np.zeros((len(pf), 7))
        for port, array in [('PF', pf), ('PT', pt)]:
            for j in range(7):
                take = np.flatnonzero(matrices[port][j])
                # Never multiply absent nonmember NaNs by mathematically zero weights.
                result[:, j] += array[:, take] @ matrices[port][j, take]
        assert np.isfinite(result).all()
        answer[convention] = result
    return answer


def check_metrics(flows, observed, good, hours, timestamps, states, gamma, names):
    saved = pd.read_csv(COMPARISON / 'public_interface_metrics.csv', float_precision='round_trip')
    saved = saved.loc[saved.model.eq('candidate') & saved.cohort.eq('candidate_all_success')]
    months = pd.to_datetime(timestamps, utc=True).tz_convert('America/New_York').month.to_numpy()
    periods = {'annual': good, **{f'month_{m:02d}': good & (months == m) for m in range(1, 13)},
               'post_Dover': good & (states == 'post_dover')}
    rows = []; error = 0.
    for convention in CONVENTIONS:
        public = flows[convention] / gamma
        for period, use in periods.items():
            for j, interface in enumerate(names):
                difference = public[use, j] - observed[use, j]
                metrics = {'mae_public_MW': float(np.mean(np.abs(difference))),
                    'rmse_public_MW': float(np.sqrt(np.mean(difference ** 2))),
                    'bias_public_MW': float(np.mean(difference)),
                    'wape_percent': float(100 * np.abs(difference).sum() / np.abs(observed[use, j]).sum())}
                row = saved.loc[saved.convention.eq(convention) & saved.period.eq(period) & saved.interface.eq(interface)]
                assert len(row) == 1 and int(row.iloc[0].hours) == int(use.sum())
                for field, actual in metrics.items():
                    delta = abs(actual - float(row.iloc[0][field])); error = max(error, delta)
                    assert delta < 1e-8, (convention, period, interface, field, delta)
                rows.append(dict(convention=convention, period=period, interface=interface, hours=int(use.sum()), **metrics))
    return rows, error


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    contract_path = ROOT / 'output/nygrid_2025_ac_loss_revision/comparison/comparison_contract.json'
    contract = json.loads(contract_path.read_text())
    scoring_path = COMPARISON / 'scoring_receipt.json'
    scoring = json.loads(scoring_path.read_text()); assert scoring['passed'] and scoring['completed']
    annual_receipt_path = ANNUAL / 'annual_receipt.json'
    annual_receipt = json.loads(annual_receipt_path.read_text())
    assert annual_receipt['completed'] and annual_receipt['months_complete'] == 12
    arrays_path = COMPARISON / 'comparison_arrays.npz'
    frozen_file_check(arrays_path, scoring['outputs'])
    metrics_path = COMPARISON / 'public_interface_metrics.csv'; frozen_file_check(metrics_path, scoring['outputs'])
    with np.load(arrays_path, allow_pickle=False) as a:
        reference = {key: a[key].copy() for key in a.files}
    hours = reference['hour_index'].astype(int); timestamps = reference['timestamp_utc'].astype(str)
    names = reference['interface_names'].astype(str).tolist(); gamma = float(reference['gamma'])
    source = reference['source_qualified'].astype(bool); expected_good = reference['candidate_qualified'].astype(bool)
    assert np.array_equal(hours, np.arange(1, 8761)) and source.sum() == 8651
    assert names == contract['interface_names'] and gamma == contract['gamma']
    cohort_path = ROOT / 'output/nygrid_2025_ac_loss_revision/comparison/frozen_comparison_cohort.csv'
    cohort = pd.read_csv(cohort_path);states = cohort.dated_state.to_numpy(str)
    assert np.array_equal(cohort.hour_index, hours) and np.array_equal(cohort.timestamp_utc, timestamps)
    assert np.array_equal(cohort.frozen_source_qualified.to_numpy(bool), source)
    model_receipt_path = HANDOFF / 'model/model_receipt.json'
    model_receipt = json.loads(model_receipt_path.read_text())
    bundle_paths = [HANDOFF / 'model' / r['name'] for r in model_receipt['model_files']]
    for path, expected in zip(bundle_paths, model_receipt['model_files']):
        assert path.stat().st_size == expected['bytes'] and sha(path) == expected['sha256']
    model = loadmat(bundle_paths[0], simplify_cells=True)['model']
    assert float(model['scale_factor_gamma']) == gamma
    assert np.array_equal(vector(model['axis'], 'hour_index', int), hours)
    assert np.array_equal(vector(model['axis'], 'source_qualified', bool), source)
    assert np.array_equal(vector(model['axis'], 'state_index', int), np.array([STATES.index(s) + 1 for s in states]))
    templates = model['templates'];policies = model['loss_static']
    canonical = templates[-1]
    bus_ids = canonical['bus'][:, 0].astype(int)
    keys = np.asarray(canonical['userdata']['ac_system']['branch_keys']).astype(str)
    parents = vector(canonical['userdata']['ac_system'], 'branch_parent_row', int)
    fbus = canonical['branch'][:, 0].astype(int);tbus = canonical['branch'][:, 1].astype(int)
    gen_buses = vector(model, 'generator_bus_ids', int);external = vector(model['external'], 'generator_mask', bool)
    native = ~external;assert len(gen_buses) == 1464 and native.sum() == 1436 and external.sum() == 28
    bus_zone_weights = {};gen_zone_weights = None
    for state, m, policy in zip(STATES, templates, policies):
        lookup = dict(zip(m['bus'][:, 0].astype(int), vector(policy, 'bus_group', int)))
        weights = np.column_stack([[lookup.get(int(b), 0) == j for b in bus_ids] for j in range(1, 12)]).astype(float)
        bus_zone_weights[state] = weights
        gen_groups = np.array([lookup[int(b)] for b in gen_buses])
        assert np.all((gen_groups[native] >= 1) & (gen_groups[native] <= 11))
        current = np.column_stack([(gen_groups == j) & native for j in range(1, 12)]).astype(float)
        if gen_zone_weights is None: gen_zone_weights = current
        else: assert np.array_equal(gen_zone_weights, current)
    gross = np.full((8760, 11), np.nan);native_generation = gross.copy();fixed_transfers = np.full((8760, 6), np.nan)
    for shard in model_receipt['profile_shards']:
        path = HANDOFF / 'model' / shard['name'];block = loadmat(path, simplify_cells=True)['profiles']
        take = np.arange(int(shard['first_hour']) - 1, int(shard['last_hour']))
        native_generation[take] = np.asarray(block['generator_PG_MW']) @ gen_zone_weights
        fixed_transfers[take] = block['fixed_transfer_PF_MW']
        for state in np.unique(states[take]):
            use = states[take] == state
            weights = bus_zone_weights[state][np.array([int(b) <= 140 for b in bus_ids])]
            assert weights.shape == (140, 11)
            gross[take[use]] = np.asarray(block['bus_PD_MW'])[use] @ weights
        del block
    assert np.isfinite(gross[source]).all() and np.isfinite(native_generation[source]).all() and np.isfinite(fixed_transfers[source]).all()
    gross = masked(gross, source);native_generation = masked(native_generation, source);fixed_transfers = masked(fixed_transfers, source)
    terms_path = ALIGNMENT / 'interface_operator_terms.csv';terms = pd.read_csv(terms_path)
    operator_contract_path = ALIGNMENT / 'interface_operator_contract.json'
    operator_contract = json.loads(operator_contract_path.read_text())
    assert operator_contract['primary_convention'] == CONVENTIONS[0]
    operators = {state: operator_weights(terms, keys, parents, fbus, tbus, names, state) for state in STATES}
    paths = [ANNUAL / 'monthly' / f'profile_PF_2025_{month:02d}.mat' for month in range(1,13)]
    assert all(path.is_file() for path in paths)
    inputs = [Path(__file__), arrays_path, metrics_path, scoring_path, contract_path, cohort_path, annual_receipt_path,
        model_receipt_path, *bundle_paths, terms_path, operator_contract_path, *paths,
        ALIGNMENT / 'profile_alignment_summary.json', OUT / 'interface_flow_reference.npz']
    before = [record(p) for p in inputs]
    flows = {name: np.full((8760, 7), np.nan) for name in CONVENTIONS}
    flags = {name: np.zeros(8760, bool) for name in FLAG_NAMES}
    reasons = np.full(8760, '', dtype=object);seen = np.zeros(8760, bool);qualified = seen.copy()
    served = np.full((8760, 11), np.nan);losses = served.copy()
    maxima = Counter();month_records = []
    for path in paths:
        frozen_file_check(path, scoring['dependencies'])
        m = loadmat(path, simplify_cells=True, variable_names=MONTH_FIELDS)
        assert set(MONTH_FIELDS) <= set(m)
        ix = vector(m, 'hour_index', int) - 1;assert not seen[ix].any()
        assert np.array_equal(strings(m['timestamp_utc']), timestamps[ix]) and float(m['gamma']) == gamma
        assert np.array_equal(strings(m['branch_keys']), keys) and np.array_equal(vector(m, 'branch_parent_row', int), parents)
        assert np.array_equal(vector(m, 'branch_from_bus', int), fbus) and np.array_equal(vector(m, 'branch_to_bus', int), tbus)
        assert np.array_equal(vector(m, 'bus_id', int), bus_ids) and np.array_equal(vector(m, 'generator_bus_id', int), gen_buses)
        assert np.array_equal(vector(m, 'external_generator_rows_1based', int), np.flatnonzero(external) + 1)
        for name in FLAG_NAMES: flags[name][ix] = vector(m, name, bool)
        assert np.array_equal(flags['source_qualified'][ix], source[ix])
        good = source[ix] & flags['PF_converged'][ix] & flags['AC_equation_gate'][ix] & flags['loss_allocation_gate'][ix] & flags['reduction_and_equation_gate'][ix]
        assert np.array_equal(good, expected_good[ix]);qualified[ix] = good;reasons[ix] = strings(m['loss_status'])
        seen[ix] = True
        for state in np.unique(states[ix]):
            local = np.flatnonzero((states[ix] == state) & good)
            if not len(local): continue
            take = ix[local];weights, member_parents = operators[state]
            relevant = np.isin(parents, member_parents)
            assert np.asarray(m['branch_present'], bool)[local][:, relevant].all()
            assert np.asarray(m['branch_active'], bool)[local][:, relevant].all()
            solved = apply_weights(np.asarray(m['PF'])[local], np.asarray(m['PT'])[local], weights)
            for convention, value in solved.items(): flows[convention][take] = value
            present = np.asarray(m['bus_present'], bool)[local]
            pd_mw = np.asarray(m['PD'])[local];pg_mw = np.asarray(m['bus_PG'])[local]
            assert np.isfinite(pd_mw[present]).all() and np.isfinite(pg_mw[present]).all()
            zonal_served = np.where(present, pd_mw, 0) @ bus_zone_weights[state]
            budget = np.asarray(m['actual_budget_MW'])[local]
            served[take] = zonal_served;losses[take] = budget[:, :11]
            maxima['served_export_error_model_MW'] = max(maxima['served_export_error_model_MW'], maxabs(zonal_served - np.asarray(m['NY_served_PD_MW'])[local]))
            maxima['gross_input_error_model_MW'] = max(maxima['gross_input_error_model_MW'], maxabs(gross[take] - np.asarray(m['NY_gross_target_MW'])[local]))
            maxima['NY_gross_served_loss_closure_model_MW'] = max(maxima['NY_gross_served_loss_closure_model_MW'], maxabs(gross[take] - zonal_served - budget[:, :11]))
            native_by_bus = np.where(present, pg_mw, 0).copy()
            ext_pg = np.asarray(m['external_gen_PG'])[local]
            for column, generator in enumerate(np.flatnonzero(external)):
                row = int(np.flatnonzero(bus_ids == gen_buses[generator])[0]);native_by_bus[:, row] -= ext_pg[:, column]
            maxima['native_generation_input_vs_solved_model_MW'] = max(maxima['native_generation_input_vs_solved_model_MW'], maxabs(native_by_bus @ bus_zone_weights[state] - native_generation[take]))
            maxima['fixed_control_input_vs_solved_model_MW'] = max(maxima['fixed_control_input_vs_solved_model_MW'], maxabs(np.asarray(m['DC_PF'])[local] - fixed_transfers[take]), maxabs(np.asarray(m['DC_PT'])[local] - fixed_transfers[take]))
            maxima['global_generation_demand_loss_closure_model_MW'] = max(maxima['global_generation_demand_loss_closure_model_MW'], maxabs(np.sum(np.where(present, pg_mw - pd_mw, 0), axis=1) - budget.sum(axis=1)))
        month_records.append(dict(file=path.name, hours=len(ix), source_qualified=int(source[ix].sum()), qualified=int(good.sum())))
        print(f'EXPORTED {path.name}: {int(good.sum())}/{int(source[ix].sum())} qualified', flush=True)
    assert seen.all() and np.array_equal(qualified, expected_good)
    assert np.array_equal(flags['PF_attempted'], source)
    operating = qualified & flags['VQ_and_generator_assumption_gate'];assert np.array_equal(operating, reference['operating_qualified'])
    for convention in CONVENTIONS:
        delta = maxabs(flows[convention][qualified] / gamma - reference['candidate_' + convention][qualified])
        maxima[convention + '_frozen_scorer_error_public_MW'] = delta;assert delta < 1e-8
    with np.load(OUT / 'interface_flow_reference.npz', allow_pickle=False) as independent:
        assert np.array_equal(independent['hour_index'], hours) and np.array_equal(independent['timestamp_utc'].astype(str), timestamps)
        assert np.array_equal(independent['qualified'].astype(bool), qualified) and np.array_equal(independent['source_qualified'].astype(bool), source)
        assert independent['interface_names'].astype(str).tolist() == names and float(independent['gamma']) == gamma
        for convention in CONVENTIONS:
            assert np.array_equal(np.isnan(flows[convention]), np.isnan(independent[convention]))
            delta = maxabs(flows[convention][qualified] - independent[convention][qualified])
            maxima[convention + '_independent_reconstruction_error_model_MW'] = delta;assert delta < 1e-8
    maxima['frozen_gross_input_error_model_MW'] = maxabs(gross[source] - reference['NY_gross_target_MW'][source])
    maxima['frozen_served_error_model_MW'] = maxabs(served[qualified] - reference['NY_served_PD_MW'][qualified])
    maxima['frozen_loss_error_model_MW'] = maxabs(losses[qualified] - reference['NY_allocated_loss_MW'][qualified])
    for name, error in maxima.items(): assert error < (1e-8 if name.endswith('public_MW') else 1e-5), (name, error)
    observed = reference['observed'];metrics, metric_error = check_metrics(flows, observed, qualified, hours, timestamps, states, gamma, names)
    pd.DataFrame(metrics).to_csv(OUT / 'recomputed_interface_metrics.csv', index=False, lineterminator='\n')
    hour_records = []
    for k, hour in enumerate(hours):
        status = 'source_excluded' if not source[k] else 'solution_failed' if not qualified[k] else 'operating_qualified' if operating[k] else 'equation_loss_qualified'
        hour_records.append(dict(hour=int(hour), timestamp=str(timestamps[k]), state=str(states[k]),
            sourceQualified=bool(source[k]), qualified=bool(qualified[k]), operatingQualified=bool(operating[k]), status=status,
            PFConverged=bool(flags['PF_converged'][k]), equationQualified=bool(flags['AC_equation_gate'][k]),
            lossQualified=bool(flags['loss_allocation_gate'][k]), reductionQualified=bool(flags['reduction_and_equation_gate'][k]),
            failureReason=str(reasons[k]) if source[k] and not qualified[k] else None))
    payload = dict(schemaVersion=1, hours=hour_records, interfaceNames=names, zoneNames=ZONES,
        interfaceFlowsModelMW=nullable(flows[CONVENTIONS[0]]), observationsPublicMW=nullable(observed),
        zoneSeriesModelMW=dict(gross=nullable(gross), served=nullable(served), loss=nullable(losses), generation=nullable(native_generation)),
        fixedTransferFlowsModelMW=nullable(fixed_transfers),
        fixedTransferNames=['CSC','NEPTUNE','HTP','VFT','ONTARIO_PAR_25118','ONTARIO_PAR_25119'],
        metadata=dict(gamma=gamma, defaultUnits='Model MW', publicScaleFormula='aggregate model MW / gamma',
            primaryConvention=CONVENTIONS[0], primaryFormula='sum(coefficient * PF at original corridor from terminal)',
            interfaceOrderFrozen=True, interfaceMembershipTermsPerState=34, interfaceTermsJoinedByRuntimeKey=True,
            originalPhysicalTerminalsUsed=True, reducedCouplingEdgesUsedForInterfaceFlow=False,
            physicalP32MeterCorrespondenceCertified=False, alternativeConventionsAreSensitivityNotConfidenceBounds=True,
            branchCurrentGammaDivisionApplied=False, interfaceUnit='synthetic model MW', observationUnit='public MW',
            observationUnitPolicy='Preserved frozen numeric-as-MW interpretation of published NYISO P32 Flow(MWH); no unit factor fitted and no independent physical meter certification.',
            generationDefinition='Source-informed reconstructed net native generator PG aggregated by current NY accounting zone, not measured unit dispatch; excludes all28 external equivalents including HQ; negative storage pumping is preserved.',
            fixedTransferDefinition='Four prescribed DC-transfer records and two ideal PAR-control equivalents; signed positive from each recorded from_bus toward to_bus; not six physical HVDC assets.',
            fieldAvailability={'interfaceFlowsModelMW':'qualified', 'observationsPublicMW':'independently available public observations',
                'zoneSeriesModelMW.gross':'sourceQualified input', 'zoneSeriesModelMW.generation':'sourceQualified prescribed native input',
                'zoneSeriesModelMW.served':'qualified', 'zoneSeriesModelMW.loss':'qualified', 'fixedTransferFlowsModelMW':'sourceQualified prescribed input'},
            nullMeans='Unavailable under the stated field mask; never zero-fill or interpolate failed/source-excluded model predictions.',
            failedIteratesShownAsPredictions=False, solverFailureProvesGlobalInfeasibility=False,
            counts=dict(hours=8760, sourceQualified=int(source.sum()), sourceExcluded=int((~source).sum()), qualified=int(qualified.sum()),
                failed=int((source & ~qualified).sum()), operatingQualified=int(operating.sum()), publicObservationRows=int(np.isfinite(observed).all(axis=1).sum())),
            failedStatusCounts=dict(Counter(str(v) for v in reasons[source & ~qualified])),
            computationStatus='Completed fresh annual coupled-PF replay of the frozen physical repair; map freshly re-exported and independently rescored.',
            sourceModelCommit=str(model['source_model_commit']), sourceModelCommitRole='preserved_baseline',
            physicalRepairCandidateSha256=model_receipt['physical_repair']['candidate_receipt_sha256'],
            compiledModelSha256=model_receipt['model_file']['sha256'],
            exportRepoCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            annualRun=RUN_LABEL, exportedUTC=datetime.now(timezone.utc).isoformat(),
            wholeSystemOperatingQualification=False, validation=dict(scoringMetricRowsCompared=len(metrics), maximumSavedMetricDifference=metric_error,
                maximumNumericalDifferences=dict(maxima)), sources=before))
    output = OUT / 'annual_data.json';output.write_text(json.dumps(payload, separators=(',', ':'), allow_nan=False) + '\n', encoding='utf-8')
    # Verify JSON round-trip retains every finite double, null mask and hour.
    roundtrip = json.loads(output.read_text())
    for key, source_array in [('interfaceFlowsModelMW',flows[CONVENTIONS[0]]),('observationsPublicMW',observed),('fixedTransferFlowsModelMW',fixed_transfers)]:
        assert np.array_equal(np.asarray(roundtrip[key],float),source_array,equal_nan=True), key
    for key, source_array in [('gross',gross),('served',served),('loss',losses),('generation',native_generation)]:
        assert np.array_equal(np.asarray(roundtrip['zoneSeriesModelMW'][key],float),source_array,equal_nan=True), key
    after = [record(p) for p in inputs];assert before == after, 'A sealed or current source changed while exporting'
    receipt = dict(passed=True, scope='Current annual offline-map data export; full-axis masks and precision; no simulation',
        createdUTC=datetime.now(timezone.utc).isoformat(), output=record(output), counts=payload['metadata']['counts'],
        failureStatusCounts=payload['metadata']['failedStatusCounts'], exactJSONRoundtrip=True, inputsUnchanged=True,
        PFRun=False, OPFRun=False, annualRerun=False, monthlyCoverage=month_records,
        maximumNumericalDifferences=dict(maxima), savedMetricRowsCompared=len(metrics), maximumSavedMetricDifference=metric_error,
        interfaceConvention=CONVENTIONS[0], publicScaleFormula='model_MW/gamma', generationExcludesAllExternalEquivalents=True,
        sourceReceipts=before, recomputedMetrics=record(OUT/'recomputed_interface_metrics.csv'))
    (OUT / 'scientific_data_receipt.json').write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True, outputBytes=output.stat().st_size, **payload['metadata']['counts'], metricRows=len(metrics), metricError=metric_error)))


if __name__ == '__main__':
    main()
