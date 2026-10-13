"""Audit frozen active-power headroom and distinguish capability from policy.

No power-flow solve, dispatch change, parameter edit, or observed internal
interface read occurs here. Native and external eligibility are different.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_ac_loss_revision/validation/headroom'


def record(path):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=digest, bytes=path.stat().st_size)


def stats(values):
    values = np.asarray(values, dtype=float)
    assert np.isfinite(values).all()
    return dict(min=float(values.min()), mean=float(values.mean()), max=float(values.max()))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    paths = {key: ROOT / relative for key, relative in {
        'register': 'output/nygrid_2025_western_audit/corrected/model_generator_register.csv',
        'fleet': 'output/nygrid_2025_western_audit/corrected/fleet_register.csv',
        'bounds': 'output/nygrid_2025_dispatch/dispatch/dispatch_bounds.mat',
        'profiles': 'output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat',
        'source_priors': 'output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat',
        'prior_semantics': 'output/nygrid_2025_dispatch/priors/prior_summary.json',
        'states': 'output/nygrid_2025_dover_parameters/replay/operating_states.mat',
        'parent': 'output/nygrid_2025_inputs/model/operating_inputs.mat',
        'external_shares': 'output/nygrid_2025_western_audit/dispatch/all_boundary_external_generator_shares.csv',
        'old_quality': 'output/nygrid_2025_acpf_profile_audit/acpf/annual_hour_quality.csv',
        'representative': 'output/nygrid_2025_compact_ac/models/compact_ac_h8508.mat',
    }.items()}
    register = pd.read_csv(paths['register'], keep_default_na=False)
    fleet = pd.read_csv(paths['fleet'], keep_default_na=False)
    assert register.shape[0] == 1464 and register.gen_row.is_unique and register.device_key.is_unique
    assert np.array_equal(register.gen_row, np.arange(1, 1465)) and fleet.fleet_id.is_unique
    native = register.role.eq('native').to_numpy(); external = register.role.eq('fixed_external').to_numpy()
    assert native.sum() == 1436 and external.sum() == 28 and np.all(native | external)
    fields = ['fleet_id', 'plant_name', 'energy_source_code', 'prime_mover', 'technology', 'hourly_dispatch_observed',
        'hourly_availability_observed', 'availability_assumed', 'dispatch_eligible_default', 'is_storage', 'is_pumped_hydro', 'is_variable_renewable']
    details = register.loc[native].merge(fleet[fields], on='fleet_id', how='left', validate='one_to_one')
    assert len(details) == native.sum() and details.prime_mover.notna().all()
    metadata = register.copy()
    for field in fields[1:]:
        metadata[field] = ''; metadata.loc[native, field] = details[field].to_numpy()
    metadata['native_conventional_fossil_resource'] = native & metadata.fuel_category.eq('Combined Fossil').to_numpy() & ~metadata.prime_mover.eq('FC').to_numpy()
    strict_resource = metadata.native_conventional_fossil_resource.to_numpy()
    assert strict_resource.sum() == 265
    bounds = loadmat(paths['bounds'], simplify_cells=True)
    profiles = loadmat(paths['profiles'], simplify_cells=True)
    states = loadmat(paths['states'], simplify_cells=True, variable_names=['hour_index', 'timestamp_utc', 'qualified'])
    for source in [bounds, profiles, states]:
        assert np.array_equal(source['hour_index'], np.arange(1, 8761))
    assert np.array_equal(states['timestamp_utc'], profiles['timestamp_utc'])
    q = states['qualified'].astype(bool); assert q.sum() == 8651
    pg = np.asarray(profiles['gen_pg'], float)
    lower = np.asarray(bounds['gen_pmin'], float).copy(); upper = np.asarray(bounds['gen_pmax'], float).copy()
    assert pg.shape == lower.shape == upper.shape == (8760, 1464)
    # Explicitly reproduce current public-loader policy, then compare it with
    # the separate original external capability boxes below.
    lower[:, external] = pg[:, external]; upper[:, external] = pg[:, external]
    assert np.isfinite(pg[q]).all() and np.isfinite(lower[q]).all() and np.isfinite(upper[q]).all()
    assert np.max(np.maximum(lower[q] - pg[q], pg[q] - upper[q])) <= 1e-7
    online = (upper > 0) | (lower < 0)
    positive = pg > 1e-6
    source_priors = loadmat(paths['source_priors'], simplify_cells=True)
    assert np.array_equal(source_priors['hour_index'], np.arange(1, 8761))
    assert source_priors['prior_pg'].shape == pg.shape
    positive_prior = source_priors['prior_pg'] > 1e-6
    headroom = np.maximum(upper - pg, 0)
    headroom[~q] = np.nan
    policies = {
        'native_fossil_available_model_status': native[None, :] & register.fuel_category.eq('Combined Fossil').to_numpy()[None, :] & online,
        'native_fossil_positive_P': native[None, :] & register.fuel_category.eq('Combined Fossil').to_numpy()[None, :] & online & positive,
        'native_conventional_fossil_positive_P': strict_resource[None, :] & online & positive,
        'native_conventional_fossil_available_status': strict_resource[None, :] & online,
        'native_conventional_positive_source_and_modeled_P': strict_resource[None, :] & online & positive & positive_prior,
    }
    hourly = pd.DataFrame(dict(hour_index=np.arange(1, 8761), timestamp_utc=profiles['timestamp_utc'], source_qualified=q))
    policy_summary = []
    for label, eligible in policies.items():
        total = np.where(eligible, headroom, 0).sum(axis=1); total[~q] = np.nan
        hourly[label + '_headroom_model_MW'] = total
        hourly[label + '_eligible_rows'] = eligible.sum(axis=1)
        policy_summary.append(dict(policy=label, eligible_rows=stats(eligible[q].sum(axis=1)), upward_headroom_model_MW=stats(total[q])))
    fuel_summary = []
    for fuel in sorted(register.fuel_category.unique()):
        use = register.fuel_category.eq(fuel).to_numpy()
        fuel_summary.append(dict(fuel_category=fuel, model_rows=int(use.sum()),
            modeled_available_rows=stats(online[q][:, use].sum(axis=1)), positive_P_rows=stats(positive[q][:, use].sum(axis=1)),
            all_available_upward_headroom_model_MW=stats(np.where(online[q][:, use], headroom[q][:, use], 0).sum(axis=1)),
            positive_P_upward_headroom_model_MW=stats(np.where((online & positive)[q][:, use], headroom[q][:, use], 0).sum(axis=1))))
    zone_rows = []
    strict = policies['native_conventional_fossil_positive_P']
    for zone in sorted(register.loc[native, 'zone'].unique()):
        use = register.zone.eq(zone).to_numpy()
        values = np.where(strict[:, use], headroom[:, use], 0).sum(axis=1)
        zone_rows.append(dict(zone=zone, static_candidate_rows=int((strict_resource & use).sum()),
            minimum_eligible_rows=int(strict[q][:, use].sum(axis=1).min()), maximum_eligible_rows=int(strict[q][:, use].sum(axis=1).max()),
            minimum_headroom_model_MW=float(values[q].min()), mean_headroom_model_MW=float(values[q].mean()), maximum_headroom_model_MW=float(values[q].max())))
        hourly['native_conventional_' + zone + '_headroom_model_MW'] = np.where(q, values, np.nan)
    shares = pd.read_csv(paths['external_shares'], keep_default_na=False)
    assert len(shares) == 28 and shares.model_gen_row_1based.is_unique
    erow = shares.model_gen_row_1based.to_numpy(int) - 1; prow = shares.parent_gen_row.to_numpy(int) - 1
    assert np.array_equal(erow, np.flatnonzero(external))
    parent = loadmat(paths['parent'], simplify_cells=True, variable_names=['base_case'])['base_case']
    assert np.array_equal(parent['gen'][prow, 0], register.bus_id.to_numpy()[erow])
    original_lo = parent['gen'][prow, 9]; original_hi = parent['gen'][prow, 8]
    cap = np.max(abs(parent['gen'][prow, 8:10]), axis=1); apparent_cap = cap / .95
    representative = loadmat(paths['representative'], simplify_cells=True, variable_names=['model'])['model']['detailed_mpc']
    control = representative['userdata']['ac_system']
    assert np.array_equal(cap, control['generator_capability_reference'][erow])
    assert np.array_equal(apparent_cap, control['generator_assumed_s_cap'][erow])
    original_violation = np.maximum(original_lo - pg[:, erow], pg[:, erow] - original_hi)
    assert np.max(original_violation[q]) < 1e-7
    external_rows = []
    for region in shares.region.unique():
        use = shares.region.eq(region).to_numpy(); ei = erow[use]
        upward = (original_hi[use] - pg[:, ei]).sum(axis=1); downward = (pg[:, ei] - original_lo[use]).sum(axis=1)
        row = dict(region=region, equivalent_rows=int(use.sum()), frozen_generation_shares_sum=float(shares.loc[use, 'frozen_generation_share'].sum()),
            original_Pmin_total_model_MW=float(original_lo[use].sum()), original_Pmax_total_model_MW=float(original_hi[use].sum()),
            scheduled_total_PG_model_MW=stats(pg[q][:, ei].sum(axis=1)), original_Pbox_upward_headroom_model_MW=stats(upward[q]),
            original_Pbox_downward_headroom_model_MW=stats(downward[q]), current_pinned_box_headroom_model_MW=stats(headroom[q][:, ei].sum(axis=1)),
            assumed_S_proxy_total_MVA=float(apparent_cap[use].sum()), original_Pbox_violating_source_hours=int(np.any(original_violation[q][:, use] > 1e-7, axis=1).sum()),
            capability_is_historical_synthetic_equivalent_proxy_not_verified_2025_unit_reserve=True)
        external_rows.append(row)
        hourly[region + '_original_box_headroom_model_MW'] = np.where(q, upward, np.nan)
    external_ledger = shares.copy()
    external_ledger['original_Pmin_model_MW'] = original_lo; external_ledger['original_Pmax_model_MW'] = original_hi
    external_ledger['static_capability_reference_MW'] = cap; external_ledger['assumed_apparent_capability_MVA'] = apparent_cap
    external_ledger['minimum_scheduled_PG_MW'] = pg[q][:, erow].min(axis=0); external_ledger['maximum_scheduled_PG_MW'] = pg[q][:, erow].max(axis=0)
    old = pd.read_csv(paths['old_quality']); solved = old.AC_equation_gate.astype(bool) & old.P_profile_preservation_gate.astype(bool)
    ix = old.loc[solved, 'hour_index'].to_numpy(int) - 1; losses = old.loc[solved, 'AC_real_losses_mw'].to_numpy(float)
    assert len(ix) == 8494
    total = hourly.native_conventional_fossil_positive_P_headroom_model_MW.to_numpy()
    margins = total[ix] - losses; worst = int(np.argmin(margins))
    prior_check = dict(cohort='previous detailed-AC equation/profile-qualified8494 only; not a revised-PF feasibility proof',
        eligibility_policy='native_conventional_fossil_positive_P',
        hours=8494, shortfall_hours=int(np.sum(margins < -1e-7)), minimum_margin_model_MW=float(margins.min()),
        minimum_margin_hour_index=int(ix[worst] + 1), headroom_at_minimum_margin_model_MW=float(total[ix[worst]]),
        previous_AC_losses_at_minimum_margin_model_MW=float(losses[worst]))
    stricter = hourly.native_conventional_positive_source_and_modeled_P_headroom_model_MW.to_numpy()
    strict_margins = stricter[ix] - losses
    prior_check['stricter_positive_source_and_modeled_P_shortfall_hours'] = int(np.sum(strict_margins < -1e-7))
    prior_check['stricter_positive_source_and_modeled_P_minimum_margin_model_MW'] = float(strict_margins.min())
    prior_check['stricter_positive_source_and_modeled_P_shortfall_hour_indices'] = (ix[strict_margins < -1e-7] + 1).tolist()
    previous_reference = dict(original_reference_bus_ids=sorted(old.loc[solved, 'reference_bus_id'].astype(int).unique().tolist()),
        original_reference_generator_rows=sorted(old.loc[solved, 'reference_generator_row'].astype(int).unique().tolist()),
        original_reference_PG_model_MW=stats(old.loc[solved, 'reference_PG_input_MW']),
        original_reference_Pmax_model_MW=stats(old.loc[solved, 'reference_Pmax_MW']),
        original_reference_headroom_model_MW=stats(old.loc[solved, 'reference_Pmax_MW'] - old.loc[solved, 'reference_PG_input_MW']),
        previous_unbounded_reference_increment_model_MW=stats(old.loc[solved, 'reference_PG_change_MW']))
    hourly.to_csv(OUT / 'hourly_headroom.csv', index=False, lineterminator='\n')
    metadata.to_csv(OUT / 'generator_eligibility_metadata.csv', index=False, lineterminator='\n')
    pd.DataFrame(zone_rows).to_csv(OUT / 'native_conventional_zone_headroom.csv', index=False, lineterminator='\n')
    external_ledger.to_csv(OUT / 'external_capability_ledger.csv', index=False, lineterminator='\n')
    report = dict(passed=True, created_utc=datetime.now(timezone.utc).isoformat(), source_qualified_hours=8651,
        modeled_generator_rows=1464, native_rows=1436, external_equivalent_rows=28,
        join_keys_and_hour_axes_exact=True, qualified_source_PG_within_current_boxes=True,
        native_headroom_policy_candidates=policy_summary, fuel_headroom=fuel_summary, native_conventional_zone_headroom=zone_rows,
        external_original_capability_by_region=external_rows, previous_AC_loss_headroom_check=prior_check,
        previous_single_reference_generator_audit=previous_reference,
        native_conventional_resource_rows=265, native_fossil_fuel_cell_rows_excluded_from_conventional_proxy=22,
        modeled_GEN_STATUS_is_availability_not_observed_commitment=True,
        positive_baseline_P_is_model_output_proxy_not_observed_synchronized_or_AGC_status=True,
        bounded_dispatch_projection_can_make_zero_prior_units_positive=True,
        source_prior_positive_is_EPA_group_capacity_allocation_proxy_not_unit_net_telemetry=True,
        native_fleet_hourly_dispatch_observed_flags=int(details.hourly_dispatch_observed.astype(int).sum()),
        native_fleet_hourly_availability_observed_flags=int(details.hourly_availability_observed.astype(int).sum()),
        fixed_external_P_boxes_are_policy_constraints_not_zero_physical_capability=True,
        no_default_regional_loss_policy_chosen=True, external_meter_and_NY_load_loss_semantics_pending=True,
        no_production_model_or_profile_changed=True, no_PF_OPF_or_parameter_fit_run=True,
        sources=[record(p) for p in paths.values()], source_code=record(Path(__file__)))
    (OUT / 'headroom_audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=True, source_hours=8651, native_conventional_rows=265, native_positive_headroom=policy_summary[2],
        old_loss_margin=prior_check, external_by_region=external_rows)))


if __name__ == '__main__':
    main()
