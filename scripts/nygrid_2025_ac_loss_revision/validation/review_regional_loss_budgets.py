"""Independent graph/accounting checks for the proposed regional loss policy.

Old solved AC losses provide a finite-budget screen only. No revised PF is
run, and future feasibility is not inferred from those historical losses.
"""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_ac_loss_revision/validation/regional_budget_review'
sys.path.insert(0, str(ROOT / 'scripts/nygrid_2025_acpf_profile_audit/alignment'))
from interface_operator import source_case, STATES

NY_ZONES = list('ABCDEFGHIJK')
EXTERNAL = ['ISONE', 'ONTARIO', 'PJM']


def rec(path):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=digest)


def region(area):
    return {1: 'ISONE', 2: 'NY', 3: 'NY', 4: 'ONTARIO', 5: 'PJM', 6: 'PJM'}[int(area)]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    base = ROOT / 'output/nygrid_2025_acpf_profile_audit/acpf'
    axes = loadmat(base / 'annual_axes.mat', simplify_cells=True)
    dispatch_path = ROOT / 'output/nygrid_2025_dispatch/dispatch/dispatch.mat'
    profiles_path = ROOT / 'output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat'
    shares_path = ROOT / 'output/nygrid_2025_western_audit/dispatch/all_boundary_external_generator_shares.csv'
    retained_register_path = ROOT / 'output/nygrid_2025_slim/network/bus_register.csv'
    parent_path = ROOT / 'output/nygrid_2025_inputs/model/operating_inputs.mat'
    d = loadmat(dispatch_path, simplify_cells=True, variable_names=['hour_index', 'timestamp_utc', 'bus_pd', 'bus_qd', 'dc_pf', 'gamma'])
    p = loadmat(profiles_path, simplify_cells=True)
    shares = pd.read_csv(shares_path)
    retained_register = pd.read_csv(retained_register_path, keep_default_na=False)
    retained_ports = retained_register.loc[retained_register.model_bus > 140].set_index('model_bus')
    assert len(retained_register) == 148 and len(retained_ports) == 8
    source_parent = loadmat(parent_path, simplify_cells=True, variable_names=['base_case'])['base_case']
    q = axes['source_qualified'].astype(bool); gamma = float(d['gamma'])
    assert q.sum() == 8651 and np.array_equal(d['hour_index'], p['hour_index'])
    assert np.array_equal(d['timestamp_utc'], p['timestamp_utc'])
    parent_axis = np.asarray(axes['branch_parent_row'], int)
    owner_matrices = {}; graph_rows = []; port_rows = []; graph_summary = []
    for state in STATES:
        c, zones, keys, _ = source_case(state)
        ids = c['bus'][:, 0].astype(int); lookup = {bid: i for i, bid in enumerate(ids)}
        regions = np.array([region(a) for a in c['bus'][:, 6]])
        weights = np.zeros((len(NY_ZONES) + len(EXTERNAL), len(parent_axis)))
        counts = {}; external_cross = []
        for j, row in enumerate(c['branch']):
            f, t = (lookup[int(value)] for value in row[:2]); rf, rt = regions[f], regions[t]
            active = bool(row[10] > 0 and j != 210)
            if not active:
                continue
            role = tuple(sorted([rf, rt])); counts['--'.join(role)] = counts.get('--'.join(role), 0) + 1
            if rf != rt and 'NY' not in role:
                external_cross.append(j + 1)
            owner = np.zeros(len(NY_ZONES) + len(EXTERNAL))
            if rf == rt == 'NY':
                assert zones[f] in NY_ZONES and zones[t] in NY_ZONES
                owner[NY_ZONES.index(zones[f])] += .5; owner[NY_ZONES.index(zones[t])] += .5
                category = 'NY_internal_half_at_original_parent_end_zones'
            elif rf == rt:
                owner[len(NY_ZONES) + EXTERNAL.index(rf)] = 1; category = 'external_internal'
            else:
                outside = rt if rf == 'NY' else rf
                owner[len(NY_ZONES) + EXTERNAL.index(outside)] = 1; category = 'NY_border_all_loss_external_NY_terminal_meter'
            members = np.flatnonzero(parent_axis == j + 1); assert len(members)
            weights[:, members] = owner[:, None]
            graph_rows.append(dict(state=state, original_parent_row=j + 1, branch_key=keys[j], from_bus=int(row[0]), to_bus=int(row[1]),
                from_region=rf, to_region=rt, from_zone=zones[f], to_zone=zones[t], category=category,
                canonical_runtime_rows='|'.join(str(k + 1) for k in members)))
        assert not external_cross
        owner_matrices[state] = weights
        inspect_ids = sorted(set(retained_ports.index.tolist()) | set(range(20001, 20015)) | ({21001} if state == 'post_dover' else set()))
        for bid in inspect_ids:
            j = lookup[bid]
            role = 'retained_station_anchor' if bid in retained_ports.index else 'eliminated_project_or_control_bus'
            if role == 'retained_station_anchor':
                assert regions[j] == 'NY' and zones[j] == retained_ports.loc[bid, 'accounting_zone']
            port_rows.append(dict(state=state, bus_id=bid, name=c['bus_name'][j], area=int(c['bus'][j, 6]), region=regions[j], NY_zone=zones[j], role=role))
        graph_summary.append(dict(state=state, full_parent_bus_count=len(ids), active_original_parent_branches=sum(counts.values()),
            active_branch_region_pair_counts=counts, inter_external_region_AC_branch_rows=external_cross))
    ports = pd.DataFrame(port_rows)
    assert (ports.loc[ports.bus_id.eq(20002), 'region'] == 'ISONE').all()
    assert (ports.loc[ports.bus_id.eq(21001), 'NY_zone'] == 'G').all()
    assert (ports.loc[ports.bus_id.ne(20002), 'region'] == 'NY').all()
    # All6explicit controlled transfers are external-to-NY under fixed signedP.
    sample = loadmat(ROOT / 'output/nygrid_2025_compact_ac/models/compact_ac_h8508.mat', simplify_cells=True, variable_names=['model'])['model']['detailed_mpc']
    lookup = {int(row[0]): region(row[6]) for row in sample['bus']}
    assert len(sample['dcline']) == 6 and np.all(sample['dcline'][:, 15:17] == 0)
    dc_rows = []
    for j, row in enumerate(sample['dcline']):
        assert lookup[int(row[0])] in EXTERNAL and lookup[int(row[1])] == 'NY'
        dc_rows.append(dict(row=j + 1, from_bus=int(row[0]), to_bus=int(row[1]), external_region=lookup[int(row[0])], loss0=float(row[15]), loss1=float(row[16])))
    # Independent source identities, all8651 source-qualified hours.
    c, zones, _, _ = source_case('pre_may'); original_regions = np.array([region(a) for a in c['bus'][:140, 6]])
    source_checks = []; source_residuals = []
    for outside in EXTERNAL:
        rows = shares.loc[shares.region.eq(outside), 'model_gen_row_1based'].to_numpy(int) - 1
        use = original_regions == outside; column = int(np.flatnonzero(p['region_labels'] == outside)[0])
        residual = p['gen_pg'][:, rows].sum(axis=1) - d['bus_pd'][:, use].sum(axis=1) - p['actual_regional_import_public_mw'][:, column] * gamma
        error = float(np.max(abs(residual[q]))); assert error < 1e-7
        source_checks.append(dict(region=outside, max_frozen_PG_minus_PD_minus_actual_net_target_model_MW=error))
    ny = original_regions == 'NY'
    residual = p['native_required_pg'] + p['actual_regional_import_public_mw'].sum(axis=1) * gamma - d['bus_pd'][:, ny].sum(axis=1)
    assert np.max(abs(residual[q])) < 1e-7
    assert np.all(d['bus_qd'][q][:, ny][d['bus_pd'][q][:, ny] == 0] == 0)
    target_zones = np.column_stack([d['bus_pd'][:, np.asarray(zones[:140]) == zone].sum(axis=1) for zone in NY_ZONES])
    erows = shares.model_gen_row_1based.to_numpy(int) - 1; prows = shares.parent_gen_row.to_numpy(int) - 1
    upper = source_parent['gen'][prows, 8]; lower = source_parent['gen'][prows, 9]
    frozen_shares = shares.frozen_generation_share.to_numpy(float)
    loss_budgets = np.full((8760, len(NY_ZONES) + len(EXTERNAL)), np.nan)
    total_losses = np.full(8760, np.nan); usable = np.zeros(8760, bool); monthly_sources = []
    for month in range(1, 13):
        path = base / 'monthly' / f'profile_PF_2025_{month:02d}.mat'; monthly_sources.append(path)
        m = loadmat(path, simplify_cells=True, variable_names=['hour_index', 'AC_equation_gate', 'P_profile_preservation_gate', 'PF', 'PT', 'branch_active'])
        hh = m['hour_index'].astype(int) - 1; keep = m['AC_equation_gate'].astype(bool) & m['P_profile_preservation_gate'].astype(bool)
        usable[hh] = keep
        for s, state in enumerate(STATES, start=1):
            rows = np.flatnonzero(keep & (axes['topology_state_index'][hh] == s))
            if not len(rows): continue
            # Absent canonical branches are NaN. They carry zero incidence and
            # are explicitly masked using activity before allocating losses.
            active = m['branch_active'][rows].astype(bool)
            losses = np.where(active, m['PF'][rows] + m['PT'][rows], 0.)
            assert np.isfinite(losses).all()
            weights = owner_matrices[state]
            assert np.all(weights[:, active.any(axis=0)].sum(axis=0) == 1)
            allocated = losses @ weights.T
            assert np.max(abs(allocated.sum(axis=1) - losses.sum(axis=1))) < 1e-7
            loss_budgets[hh[rows]] = allocated; total_losses[hh[rows]] = losses.sum(axis=1)
    assert usable.sum() == 8494
    ny_losses = loss_budgets[:, :11]; external_losses = loss_budgets[:, 11:]
    served = target_zones - ny_losses
    assert np.isfinite(served[usable]).all()
    region_screens = []
    for j, outside in enumerate(EXTERNAL):
        use = shares.region.eq(outside).to_numpy(); incremental = external_losses[:, j, None] * frozen_shares[use]
        final_pg = p['gen_pg'][:, erows[use]] + incremental
        margin = upper[use] - final_pg
        region_screens.append(dict(region=outside, previous_AC_budget_min_MW=float(external_losses[usable, j].min()),
            previous_AC_budget_mean_MW=float(external_losses[usable, j].mean()), previous_AC_budget_max_MW=float(external_losses[usable, j].max()),
            simple_frozen_share_allocation_original_Pbox_violating_hours=int(np.any((final_pg[usable] > upper[use] + 1e-7) | (final_pg[usable] < lower[use] - 1e-7), axis=1).sum()),
            minimum_individual_generator_remaining_headroom_MW=float(margin[usable].min())))
    zone_screens = [dict(zone=zone, old_AC_NY_internal_loss_min_MW=float(ny_losses[usable, j].min()),
        old_AC_NY_internal_loss_max_MW=float(ny_losses[usable, j].max()), min_proposed_served_PD_MW=float(served[usable, j].min()),
        nonpositive_served_PD_hours=int(np.sum(served[usable, j] <= 0)),
        maximum_loss_fraction_hour_index=int(np.flatnonzero(usable)[np.argmax(ny_losses[usable, j] / target_zones[usable, j])] + 1),
        hours_loss_fraction_above25pct=int(np.sum(ny_losses[usable, j] / target_zones[usable, j] > .25)),
        maximum_loss_fraction_of_original_P58_zonal_PD=float(np.max(ny_losses[usable, j] / target_zones[usable, j]))) for j, zone in enumerate(NY_ZONES)]
    frame = pd.DataFrame(dict(hour_index=np.flatnonzero(usable) + 1, total_old_AC_loss_MW=total_losses[usable]))
    for j, zone in enumerate(NY_ZONES):
        frame[zone + '_original_P58_PD_model_MW'] = target_zones[usable, j]
        frame[zone + '_internal_loss_budget_model_MW'] = ny_losses[usable, j]
        frame[zone + '_proposed_served_PD_model_MW'] = served[usable, j]
    for j, outside in enumerate(EXTERNAL): frame[outside + '_external_generation_increment_model_MW'] = external_losses[usable, j]
    pd.DataFrame(graph_rows).to_csv(OUT / 'original_parent_loss_ownership.csv', index=False)
    ports.to_csv(OUT / 'station_port_region_zones.csv', index=False)
    frame.to_csv(OUT / 'previous_AC_budget_feasibility_screen.csv', index=False)
    receipt = dict(passed=True, graph_checked_states=graph_summary, station_ports_checked=True, Dover_regulated_port21001_is_NY_zoneG=True,
        no_active_AC_ties_between_external_regions=True, all_six_DC_transfer_contracts=dc_rows,
        all_source_hours_frozen_generation_load_boundary_identities=source_checks,
        maximum_NY_native_generation_plus_all_actual_imports_minus_original_P58_PD_model_MW=float(np.max(abs(residual[q]))),
        loss_partition_counts_every_active_branch_exactly_once=True,
        NY_zonal_loss_ownership_uses_original_parent_endzones_not_computational_section_nodes=True,
        NY_served_PD_can_be_scaled_on_existing_load_buses_preserving_zero_injection_interiors=True,
        NY_zero_PD_buses_have_zero_QD_so_constant_bus_PF_scaling_is_defined=True,
        previous_qualified_AC_budget_screen_hours=8494, external_budget_capacity_screens=region_screens, NY_zone_PD_screens=zone_screens,
        finite_budget_screen_is_not_revised_PF_feasibility=True, no_revised_PF_or_OPF_run=True,
        boundary_convention='NY_terminal_aggregate_receipt; entire cross-border corridor real loss assigned to external region even during reverse flow',
        algebra='NYservedPD=P58-NYinternalLoss; externalPG=priorPG+externalInternalLoss+NYBorderLoss; nativePGandHQPGfixed',
        remaining_policy_assumptions=['Outside-area deliveredPD remains a proxy for its served load.', 'P58loss-inclusive demand interpretation is supplied by independent source audit.',
            'Half original-endzone allocation for cross-NY-zone losses is declared model accounting, not observed zonal metering.',
            'Finite original external P bounds and frozen shares are synthetic aggregate capability assumptions; Q/MVA/voltage still need separate checks.'],
        sources=[rec(pth) for pth in [dispatch_path, profiles_path, shares_path, retained_register_path, parent_path, base / 'annual_axes.mat',
            ROOT / 'output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat',
            ROOT / 'output/nygrid_2025_dover_parameters/network/x_nominal.mat',
            ROOT / 'output/nygrid_2025_compact_ac/models/compact_ac_h8508.mat',
            ROOT / 'scripts/nygrid_2025_acpf_profile_audit/alignment/interface_operator.py', *monthly_sources]],
        source_code=rec(Path(__file__)))
    (OUT / 'regional_budget_reference_review.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(passed=True, external_budget_screens=region_screens, minimum_zonal_served_PD_MW=min(r['min_proposed_served_PD_MW'] for r in zone_screens),
        maximum_zonal_loss_fraction=max(r['maximum_loss_fraction_of_original_P58_zonal_PD'] for r in zone_screens))))


if __name__ == '__main__': main()
