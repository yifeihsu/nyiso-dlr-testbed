"""Read-only source/profile audit; never solves PF or changes frozen inputs."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat
from interface_operator import ROOT, interface_definitions

OUT = ROOT / "output/nygrid_2025_acpf_profile_audit/alignment"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def maximum(values):
    return float(np.max(np.abs(values)))


def main():
    paths = {
        "inputs": "output/nygrid_2025_inputs/model/operating_inputs.mat",
        "allocation": "output/nygrid_2025_inputs/model/bus_allocation.csv",
        "public_load": "output/nygrid_2025_inputs/load_source/load_wide.csv",
        "hour_catalog": "output/nygrid_2025_inputs/load_source/hour_catalog.csv",
        "public_interfaces": "output/nygrid_2025_inputs/load_source/interface_wide.csv",
        "interface_quality": "output/nygrid_2025_inputs/load_source/interface_quality_wide.csv",
        "current_dispatch": "output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat",
        "current_replay": "output/nygrid_2025_western_audit/replay/dated_combined.mat",
        "final_replay": "output/nygrid_2025_dover_parameters/replay/bounded_x_nominal.npz",
        "original_dispatch": "output/nygrid_2025_dispatch/dispatch/dispatch.mat",
        "dispatch_priors": "output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat",
        "dispatch_bounds": "output/nygrid_2025_dispatch/dispatch/dispatch_bounds.mat",
        "generator_register": "output/nygrid_2025_dispatch/dispatch/model_generator_register.csv",
        "load_semantics_pdf": "output/nygrid_2025_acpf_profile_audit/alignment/sources/NYISO_2025_hot_weather_operations.pdf",
    }
    receipts = {name: dict(path=path, sha256=digest(ROOT / path)) for name, path in paths.items()}
    inp = loadmat(ROOT / paths["inputs"], simplify_cells=True)
    current = loadmat(ROOT / paths["current_dispatch"], simplify_cells=True)
    replay = loadmat(ROOT / paths["current_replay"], simplify_cells=True)
    final_replay = np.load(ROOT / paths["final_replay"])
    original = loadmat(ROOT / paths["original_dispatch"], simplify_cells=True)
    bounds = loadmat(ROOT / paths["dispatch_bounds"], simplify_cells=True)
    priors = loadmat(ROOT / paths["dispatch_priors"], simplify_cells=True)
    weights = pd.read_csv(ROOT / paths["allocation"])
    public_load = pd.read_csv(ROOT / paths["public_load"])
    public_if = pd.read_csv(ROOT / paths["public_interfaces"])
    public_quality = pd.read_csv(ROOT / paths["interface_quality"])
    hours = pd.read_csv(ROOT / paths["hour_catalog"])
    register = pd.read_csv(ROOT / paths["generator_register"])
    gamma = float(inp["gamma"]); qualified = current["qualified"].astype(bool)
    assert len(hours) == 8760 and np.array_equal(hours.hour_index, np.arange(1, 8761))
    for d in (inp, current, replay, original):
        assert np.array_equal(d["hour_index"], hours.hour_index)
        assert np.array_equal(d["timestamp_utc"], hours.timestamp_utc)
        assert d["gamma"] == gamma
    assert np.array_equal(replay["qualified"].astype(bool), qualified)
    assert np.array_equal(final_replay['hour_index'], hours.hour_index)
    assert np.array_equal(final_replay['timestamp_utc'].astype(str), hours.timestamp_utc)
    final_qualified = final_replay['qualified'].astype(bool)
    assert np.all(~final_qualified | qualified)
    for frame in (public_load, public_if, public_quality):
        assert np.array_equal(frame.hour_index, hours.hour_index)
        assert np.array_equal(frame.timestamp_utc, hours.timestamp_utc)
    utc = pd.to_datetime(hours.timestamp_utc, utc=True)
    assert np.all(np.diff(utc.astype('int64')) == 3600 * 10 ** 9)
    local_counts = hours.local_timestamp.value_counts()
    ny_idx = weights.bus_id.to_numpy(int) - 1
    pd_bus, qd_bus = inp["bus_gross_pd"], inp["bus_gross_qd"]
    zone_rows = []
    for j, zone in enumerate(inp["zone_names"]):
        records = weights.loc[weights.zone == zone]
        idx = records.bus_id.to_numpy(int) - 1
        public = public_load[zone].to_numpy(float)
        model = pd_bus[:, idx].sum(axis=1)
        err = maximum(model / gamma - public)
        allocation_err = maximum(pd_bus[:, idx] - public[:, None] * gamma * records.weight.to_numpy()[None, :])
        assert err < 1e-8 and allocation_err < 1e-8
        zone_rows.append(dict(zone=zone, assigned_buses=len(records), positive_weight_buses=int((records.weight > 0).sum()),
            weight_sum=float(records.weight.sum()), maximum_public_scale_reaggregation_error_MW=err,
            maximum_model_allocation_error_MW=allocation_err, mean_public_load_MW=float(public.mean()),
            peak_public_load_MW=float(public.max()), annual_public_load_MWh=float(public.sum()),
            allocation_policy='|'.join(sorted(records.allocation_policy.unique())),
            positive_bus_ids='|'.join(str(x) for x in records.loc[records.weight > 0, 'bus_id']),
            positive_bus_weights='|'.join(f'{x:.12g}' for x in records.loc[records.weight > 0, 'weight'])))
    zone_frame = pd.DataFrame(zone_rows); zone_frame.to_csv(OUT / "load_zone_allocation_audit.csv", index=False)
    weights.to_csv(OUT / "frozen_bus_allocation_reference.csv", index=False)
    assert maximum(original["bus_pd"] - pd_bus) < 1e-8
    assert maximum(original["bus_qd"] - qd_bus) < 1e-8
    public_totals = public_load[list(inp["zone_names"])].sum(axis=1).to_numpy()
    peak = int(public_totals.argmax())
    q_error = maximum(qd_bus[:, ny_idx] - pd_bus[:, ny_idx] * np.tan(np.arccos(.98)))
    assert q_error < 1e-8
    external_mask = np.ones(pd_bus.shape[1], bool); external_mask[ny_idx] = False
    ratio = inp["external_load_ratio"]
    # Rank-one time profile is independent evidence that external bus loads
    # all use the same NY load shape, irrespective of their static magnitudes.
    external_reference = pd_bus[peak, external_mask]
    external_shape_error = maximum(pd_bus[:, external_mask] - ratio[:, None] * external_reference)
    assert external_shape_error < 1e-8
    names = [d["interface"] for d in interface_definitions()]
    cohort = hours.copy()
    cohort["upstream_dispatch_and_boundary_source_qualified"] = qualified
    cohort["final_common_replay_source_qualified"] = final_qualified
    cohort["dated_state"] = np.select([utc < pd.Timestamp('2025-05-21T04:00:00Z'),
                                       utc < pd.Timestamp('2025-05-30T04:00:00Z'),
                                       utc < pd.Timestamp('2025-12-20T04:00:00Z')],
                                      ['pre_may', 'may21', 'may30'], default='post_dover')
    for name in names:
        cohort[name + "_P32_qualified"] = public_quality[name].astype(str).str.lower().eq('true').to_numpy()
    cohort["all_seven_P32_qualified"] = cohort[[n + "_P32_qualified" for n in names]].all(axis=1)
    cohort["upstream_dispatch_and_P32_comparison_cohort"] = qualified & cohort.all_seven_P32_qualified
    cohort["final_source_and_P32_comparison_cohort"] = final_qualified & cohort.all_seven_P32_qualified
    cohort.to_csv(OUT / "source_comparison_cohort.csv", index=False)
    native = current["native_generator_rows_1based"].astype(int) - 1
    ext = current["external_generator_rows_1based"].astype(int) - 1
    assert len(native) == 1436 and len(ext) == 28
    gen = current["gen_pg"]
    assert np.isfinite(gen[qualified]).all()
    actual_import_model = current['actual_regional_import_public_mw'].sum(axis=1) * gamma
    native_identity_error = maximum((gen[:, native].sum(axis=1) - pd_bus[:, ny_idx].sum(axis=1) + actual_import_model)[qualified])
    external_identity_error = maximum((gen[:, ext].sum(axis=1) - pd_bus[:, external_mask].sum(axis=1) - actual_import_model)[qualified])
    full_identity_error = maximum((gen.sum(axis=1) - pd_bus.sum(axis=1))[qualified])
    assert max(native_identity_error, external_identity_error, full_identity_error) < 1e-8
    p_error = max(float(np.maximum(bounds["gen_pmin"][qualified][:, native] - gen[qualified][:, native], 0).max()),
                  float(np.maximum(gen[qualified][:, native] - bounds["gen_pmax"][qualified][:, native], 0).max()))
    assert p_error < 1e-8
    fuel_rows = []
    for fuel in sorted(register.loc[register.role == 'native', 'fuel_category'].unique()):
        idx = register.loc[(register.role == 'native') & (register.fuel_category == fuel), 'gen_row'].to_numpy(int) - 1
        current_mw = gen[qualified][:, idx].sum(axis=1) / gamma
        prior_mw = priors["prior_pg"][qualified][:, idx].sum(axis=1) / gamma
        fuel_rows.append(dict(fuel_category=fuel, native_generator_rows=len(idx),
            mean_profile_public_scale_MW=float(current_mw.mean()),
            mean_prior_public_scale_MW=float(prior_mw.mean()),
            mean_profile_minus_prior_public_scale_MW=float((current_mw - prior_mw).mean()),
            mean_absolute_profile_minus_prior_public_scale_MW=float(np.abs(current_mw - prior_mw).mean()),
            maximum_absolute_profile_minus_prior_public_scale_MW=maximum(current_mw - prior_mw)))
    pd.DataFrame(fuel_rows).to_csv(OUT / "generation_profile_vs_prior_by_fuel.csv", index=False)
    representatives = []
    for file in sorted((ROOT / 'output/nygrid_2025_acpf_profile_audit/acpf').glob('representative_h*.mat')):
        d = loadmat(file, simplify_cells=True); m, r, a = d['m'], d['r'], d['audit']; h = int(a['hour_index']) - 1
        m_ids = m['bus'][:, 0].astype(int); r_ids = r['bus'][:, 0].astype(int)
        assert np.array_equal(m_ids, r_ids)
        original_bus_idx = np.array([np.flatnonzero(m_ids == bid)[0] for bid in inp['bus_id']])
        added = ~np.isin(m_ids, inp['bus_id'])
        delta = r['gen'][:, 1] - m['gen'][:, 1]
        slack = int(a['reference_generator_row']) - 1
        row = dict(hour_index=h + 1, timestamp_utc=str(hours.timestamp_utc.iloc[h]),
            buses=len(m_ids), added_buses=int(added.sum()),
            loader_PD_vs_original_profile_max_MW=maximum(m['bus'][original_bus_idx, 2] - pd_bus[h]),
            loader_QD_vs_original_profile_max_MVAr=maximum(m['bus'][original_bus_idx, 3] - qd_bus[h]),
            added_bus_max_abs_PD_QD=maximum(m['bus'][added, 2:4]),
            loader_PG_vs_current_profile_max_MW=maximum(m['gen'][:, 1] - gen[h]),
            corrected_generator_bus_identity_preserved=bool(np.array_equal(m['gen'][:, 0], replay['corrected_generator_buses'])),
            solved_PD_QD_vs_loader_max=maximum(r['bus'][:, 2:4] - m['bus'][:, 2:4]),
            solved_non_slack_PG_change_max_MW=maximum(np.delete(delta, slack)),
            slack_generator_row=slack + 1, slack_input_PG_MW=float(m['gen'][slack, 1]),
            slack_solved_PG_MW=float(r['gen'][slack, 1]), slack_Pmax_MW=float(m['gen'][slack, 8]),
            slack_change_MW=float(delta[slack]),
            AC_real_losses_MW=float(a['AC_real_losses_mw']),
            slack_change_minus_AC_loss_MW=float(delta[slack] - a['AC_real_losses_mw']),
            OPF_used=bool(a['OPF_used']), AC_equation_gate=bool(a['AC_equation_gate']),
            P_profile_preservation_gate_except_loss_slack=bool(a['P_profile_preservation_gate']),
            VQ_and_generator_assumption_gate=bool(a['VQ_and_generator_assumption_gate']))
        assert all(row[k] < 1e-8 for k in ['loader_PD_vs_original_profile_max_MW','loader_QD_vs_original_profile_max_MVAr',
            'added_bus_max_abs_PD_QD','loader_PG_vs_current_profile_max_MW','solved_PD_QD_vs_loader_max','solved_non_slack_PG_change_max_MW'])
        assert row['corrected_generator_bus_identity_preserved'] and not row['OPF_used']
        representatives.append(row)
    pd.DataFrame(representatives).to_csv(OUT / "representative_profile_preservation.csv", index=False)
    semantics = dict(source_url='https://www.nysrc.org/wp-content/uploads/2025/11/7.3.3-Summer-2025-NYISO-Hot-Weather-Operating-Conditions-EC-Nov-14-Attachment-7.3.3.pdf',
        author='Aaron Markham, NYISO Operations', presentation_date='2025-11-14',
        title='Summer 2025 Hot Weather Operating Conditions', evidence_pdf_pages=[7, 12],
        measured_load_semantics='NYISO measured load is net of behind-the-meter solar and NYISO/retail demand response.',
        peak_load_hour=dict(local_date='2025-06-24', hour_beginning=18, measured_load_rounded_MW=31857,
            BTM_solar_MW=947, NYISO_and_retail_DR_MW=995, reconstructed_total_demand_MW=33799),
        peak_total_demand_hour=dict(local_date='2025-06-24', hour_beginning=16, measured_load_MW=30720,
            BTM_solar_MW=2675, NYISO_and_retail_DR_MW=1096, total_demand_MW=34491),
        frozen_variable_name_qualification='bus_gross_pd / gross load in old manifests means no second subtraction of separately modeled generation. These names do not establish gross end-use demand before BTM solar and DR.',
        timing_qualification='The public peak is consistent with interpreting the frozen P58C labels as hour beginnings; this corroborates the peak label, not every provider integration convention.',
        model_action='No frozen load/generation inputs changed; semantic correction recorded only in this audit.',
        evidence_status='Primary NYISO-authored public PDF downloaded, hashed, text-extracted, and PDF pages7/12 visually inspected during this audit.')
    (OUT / 'load_source_semantics.json').write_text(json.dumps(semantics, indent=2) + '\n')
    summary = dict(created_utc=datetime.now(timezone.utc).isoformat(),
        status='fresh_read_only_profile_source_and_mapping_audit_complete', all_numeric_assertions_passed=True,
        no_PF_solved_by_this_script=True, no_frozen_input_or_model_mutations=True,
        hours=8760, timestamp_spacing_seconds=3600, local_year_2025=True,
        duplicate_local_clock_hours=int((local_counts > 1).sum()), timestamp_timezone_policy='canonical UTC with explicit New York EST/EDT and repeated-hour fold',
        gamma=gamma, model_power_base_MVA=100, peak_public_load_MW=float(public_totals[peak]),
        peak_timestamp_utc=str(hours.timestamp_utc.iloc[peak]), peak_local_timestamp=str(hours.local_timestamp.iloc[peak]),
        ny_scaled_peak_MW=float(public_totals[peak] * gamma), gamma_anchor_is_historical_model_load_not_measured_model_peak=True,
        NY_load=dict(assigned_original_buses=46, positive_weight_buses=int((weights.weight > 0).sum()),
            zones=11, complete_hour_zone_rows=8760 * 11,
            maximum_public_scale_zone_reaggregation_error_MW=float(zone_frame.maximum_public_scale_reaggregation_error_MW.max()),
            Q_assumption_power_factor=.98, maximum_Q_formula_error_MVAr=q_error,
            within_zone_load_distribution_observed_2025=False,
            zero_snapshot_zone_J_policy='uniform half allocation to original buses81 and82',
            public_annual_load_MWh=float(public_totals.sum()), model_annual_load_MWh=float(pd_bus[:, ny_idx].sum()),
            added_asset_and_section_bus_loads_zero_in_checked_cases=True),
        external_load=dict(buses=int(external_mask.sum()), positive_PD_buses=int((external_reference > 0).sum()),
            policy='static historical absolute PD magnitudes times statewide NY measured-load shape; QD retains signed snapshot ratio',
            maximum_common_shape_error_MW=external_shape_error, independent_2025_regional_loads_used=False,
            model_annual_load_MWh=float(pd_bus[:, external_mask].sum()),
            NY_load_and_external_load_are_separate_disjoint_bus_groups=True),
        generation=dict(native_rows=1436, external_equivalent_rows=28,
            source_and_dispatch_qualified_hours=int(qualified.sum()), unqualified_hours=int((~qualified).sum()),
            final_common_replay_source_qualified_hours=int(final_qualified.sum()),
            final_replay_additional_excluded_hours=int((qualified & ~final_qualified).sum()),
            finite_qualified_PG=True, native_profile_max_P_bound_violation_MW=p_error,
            native_PG_equals_NY_PD_minus_actual_import_max_error_model_MW=native_identity_error,
            external_PG_equals_external_PD_plus_actual_import_max_error_model_MW=external_identity_error,
            full_NPCC_PG_equals_total_PD_before_AC_losses_max_error_model_MW=full_identity_error,
            lossless_profile_balance_is_not_AC_net_boundary_validation=True,
            profile_is_observed_unit_dispatch=False, profile_is_bounded_source_prior_projection=True,
            current_profile_file=paths['current_dispatch'], current_generator_bus_file=paths['current_replay'],
            original_input_stage_pending_flags_are_current_operating_status=False,
            source_inputs='EPA gross weights/P63 aggregate fuel mix; NRC availability; EIA fleet and hydro; declared renewable allocations; NYIS-reported four-region actual exchange totals',
            scope='hourly continuous P-box projection with frozen priors, not unit commitment, ramping, reserve or storage-energy validation',
            external_equivalent_P_is_exact_AC_net_interchange=False),
        internal_interface_comparison=dict(names=names, P32_all_seven_qualified_hours=int(cohort.all_seven_P32_qualified.sum()),
            upstream_dispatch_and_P32_cohort_hours=int(cohort.upstream_dispatch_and_P32_comparison_cohort.sum()),
            final_source_and_P32_cohort_hours=int(cohort.final_source_and_P32_comparison_cohort.sum()),
            target_file=paths['public_interfaces'], quality_file=paths['interface_quality'],
            scope='posthoc legacy zone-cut diagnostics only; physical P32 membership and operational expression remain unestablished',
            P32_quantity_assumption='published Flow(MWH) numeric treated as MW, with no unit factor fitted',
            aggregation='forward-hold time-weighted UTC [h,h+1); duplicate timestamps averaged, complete coverage and source gap<=600s',
            observations_used_to_tune_profiles_or_operators=False),
        representative_cases_checked=len(representatives),
        representative_loader_and_non_slack_profiles_exactly_preserved=True,
        source_receipts=receipts,
        limitations=['Zonal public-load agreement is a construction identity and cannot validate within-zone bus loads.',
                     'Native generation is source-informed reconstructed dispatch, not measured unit net output.',
                     'New substation and section nodes inherit zero load; topology expansion is not load-distribution reconstruction.',
                     'ACPF slack balances active losses and can violate its small inherited generator limit.',
                     'AC equation convergence and current availability do not establish voltage/reactive/dispatch feasibility.',
                     'Physical NYISO interface membership and meter convention are not certified by legacy aggregate comparison.'])
    for name, receipt in receipts.items(): assert digest(ROOT / receipt['path']) == receipt['sha256'], f'Input changed during audit: {name}'
    (OUT / 'profile_alignment_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: summary[k] for k in ['status','gamma','NY_load','external_load','generation','internal_interface_comparison','representative_cases_checked']}, indent=2))


if __name__ == '__main__': main()
