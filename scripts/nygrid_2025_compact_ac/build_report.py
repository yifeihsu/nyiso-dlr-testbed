"""Render the compact AC contract and report from completed paired evidence."""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_compact_ac'


def read(relative):
    return json.loads((OUT / relative).read_text(encoding='utf-8-sig'))


def table(rows, headings):
    return '\n'.join(['| ' + ' | '.join(headings) + ' |',
                      '| ' + ' | '.join(['---'] * len(headings)) + ' |'] +
                     ['| ' + ' | '.join(map(str, row)) + ' |' for row in rows])


def main():
    exports = read('models/model_exports.json')
    representative = read('validation/representative_pairs/representative_pair_receipt.json')
    annual = read('validation/annual_compact_PF_receipt.json')
    scoring = read('alignment/scoring_receipt.json')
    qlimit = read('validation/Q_limit_pairs/Q_limit_pair_receipt.json')
    assert qlimit['completed'] and qlimit['outcomes_consistent']
    qgood = [x for x in qlimit['checks'] if x['qualified_pair_equivalent']]
    assert len(qgood) == len(qlimit['both_converged_hours'])
    assert all(x['compact_max_Q_bound_violation_MVAr'] < 1e-5 and
               x['compact_max_DC_Q_bound_violation_MVAr'] < 1e-5 and
               not x['compact_normal_voltage_gate'] and not x['compact_generator_P_gate'] for x in qgood)
    core = read('independent/compact_core_review.json')
    assert representative['passed'] and annual['passed'] and scoring['passed']
    errors = pd.read_csv(OUT / 'alignment/paired_recovery_errors.csv').set_index('field')
    metrics = pd.read_csv(OUT / 'alignment/public_interface_metrics.csv')
    quality = pd.read_csv(OUT / 'validation/annual_hour_quality.csv')
    good = quality[quality.AC_equation_gate.astype(bool) & quality.P_profile_preservation_gate.astype(bool)
                   & quality.reduction_and_equation_gate.astype(bool)]
    previous_alignment = json.loads((ROOT / 'output/nygrid_2025_acpf_profile_audit/alignment/profile_alignment_summary.json').read_text())
    pairs = scoring['paired_qualified_hours']; solved = scoring['compact_equation_and_profile_qualified_hours']
    source = scoring['source_qualified_hours']; new = scoring['compact_only_success_hours']
    lost = scoring['frozen_detailed_success_lost_hours']; qualified = scoring['compact_VQ_generator_qualified_hours']
    cohort = pd.read_csv(OUT / 'alignment/comparison_cohort.csv')
    score_hours = cohort.loc[cohort.compact_equation_and_profile_qualified.astype(bool), 'hour_index']
    assert len(good) == solved and sorted(good.hour_index) == sorted(score_hours)
    topology_rows = [[x['dated_state'], x['hour_index'], x['retained_bus_count'] + x['eliminated_bus_count'],
                      x['retained_bus_count'], x['eliminated_bus_count'], x['promoted_necessary_bus_count']]
                     for x in exports['models'][:4]]
    recovery_rows = []
    for name in ['VM', 'VA_phase_gauge_aligned', 'PF', 'QF', 'PT', 'QT', 'Ifrom', 'Ito', 'Iseries', 'bus_PG', 'bus_QG']:
        row = errors.loc[name]
        recovery_rows.append([name, f"{row.maximum_absolute_error:.6g}", row.units, f"{int(row.entries):,}"])
    primary = metrics[(metrics.cohort == 'paired_frozen_detailed') & (metrics.period == 'annual') &
                      (metrics.convention == 'legacy_signed_literal_from')]
    interface_rows = []
    for name in primary.interface.drop_duplicates():
        d = primary[(primary.interface == name) & (primary.model == 'frozen_detailed')].iloc[0]
        c = primary[(primary.interface == name) & (primary.model == 'compact_recovered')].iloc[0]
        interface_rows.append([name, f'{d.wape_percent:.4f}%', f'{c.wape_percent:.4f}%', f'{c.mae_public_MW:.3f}'])
    contract = dict(schema_version=1, model_kind='compact_complex_admittance_AC', retained_bus_count=148,
        anchor_registry='output/nygrid_2025_slim/network/bus_register.csv', promoted_necessary_nodes_in_current_cases=0,
        detailed_bus_counts=[266,267], eliminated_bus_counts=[118,119],
        AC_OPF_used=False, full_network_Newton_solve_used_by_compact_solver=False,
        extra_retention_triggers=['nonzero prescribed P or Q load','generator terminal','DC terminal','PV or reference control'],
        fixed_shunts_preserved_in_admittance=True, phase_taps_preserved=True, magnitude_pruning_applied=False,
        formulas=dict(K='-Yee\\Yek',Yred='Ykk+Yke*K',Vfull='L*Vk',If='Yf*L*Vk',It='Yt*L*Vk'),
        valid_for_current_source_network_and_control_state=True, rebuild_after_physical_or_operating_input_change=True,
        current_columns=['from_terminal_A','to_terminal_A','series_A'], current_row_axis='original detailed branch rows/keys',
        model_baseMVA=100, gamma=previous_alignment['gamma'], current_divided_by_gamma=False,
        original_148_interface_preserved=True, globally_minimal_node_count_claimed=False,
        source_qualified_hours=source, compact_equation_and_profile_qualified_hours=solved,
        paired_frozen_detailed_hours=pairs, additional_compact_success_hours=new, frozen_success_lost_hours=lost,
        physical_operating_qualified_hours=qualified, NYISO_zonal_load_exact_by_construction=True,
        NYISO_bus_load_distribution_observed=False, physical_P32_meter_certified=False,
        detailed_parameters_inputs_and_prior_evidence_modified=False,
        public_constructor='npcc_nygrid_2025_compact_ac', public_solver='run_nygrid_2025_compact_acpf')
    (OUT / 'MODEL_CONTRACT.json').write_text(json.dumps(contract, indent=2) + '\n', encoding='utf-8')
    repV = max(x['maximum_full_complex_voltage_difference_pu'] for x in representative['checks'])
    repI = max(x['maximum_original_branch_current_difference_A'] for x in representative['checks'])
    text = f'''# Compact 148-bus AC model and recovered-current validation

The delivered model solves AC power flow on **148 retained buses** and recovers all detailed bus voltages and original branch currents algebraically. It eliminates all 118 pre-Dover or 119 post-Dover passive interior nodes. No additional node is necessary for the current fixed-control model. No AC OPF, parameter fitting or profile correction was performed.

The compact model is numerically equivalent to the detailed AC model on the validated paired solutions. It inherits that model's limitations: its source profiles do not yet produce operating-limit-qualified states, its bus load distribution is assumed within each NYISO zone, and several interface-flow errors remain substantial. Reduction accuracy and physical calibration are separate conclusions.

## Model and retained-node boundary

The original 148 IDs are retained in their registered order. All original loads, generators, converter terminals and controlled voltages are already on these buses. The removed states comprise 43 restored station/terminal nodes, 75 numerical section nodes, and the later fixed-tap Dover auxiliary node. They carry no prescribed P/Q injection or independent voltage control in this model. Fixed shunts remain in the admittance equations and do not require a separate retained voltage state. The [bus retention ledger](output/nygrid_2025_compact_ac/independent/bus_retention_ledger.json) records every bus name, source lineage and retention reason in all four dated states.

{table(topology_rows, ['Dated topology','Example hour','Detailed buses','Retained buses','Eliminated buses','Additional required buses'])}

If a future case puts a load, generator, DC terminal or PV/reference control on an interior node, the builder retains that node automatically. The 148 buses are the requested external interface, not a proof of a globally minimum possible network.

For retained voltages `Vk` and passive interior voltages `Ve`, the implemented identity is:

```text
0 = Yek Vk + Yee Ve
Ve = -(Yee \\ Yek) Vk = K Vk
Yred = Ykk + Yke K
Vfull = L Vk
If = Yf L Vk;  It = Yt L Vk
```

The complex network includes resistance, charging, shunts, off-nominal taps and phase shifts before elimination. Complex, non-symmetric terms are retained without magnitude pruning. The block equations above establish the reduction and voltage recovery for this passive interior. Checks cover interior connectivity, conditioning, elimination identities and the Hermitian real-power dissipation screen. The nonlinear solve uses [MATPOWER's Newton power-flow kernel](https://matpower.org/doc/ref-manual/legacy/functions/newtonpf.html), with its DC-line conversion and legacy generator/Q-limit policy.

This is a **complex-admittance matrix model**, not a fabricated physical branch case. Use its dedicated wrapper. Reduced matrix couplings must not be assigned conductor ratings or summed as physical NYISO flowgates. The model stores full branch metadata for reconstruction while solving only retained bus states. [Model contract](output/nygrid_2025_compact_ac/MODEL_CONTRACT.json), [fixed-hour matrix models](output/nygrid_2025_compact_ac/models/model_exports.json), and [independent mathematical review](output/nygrid_2025_compact_ac/independent/kron_feasibility_review.json) document the boundary.

## Fresh paired ACPF and recovery evidence

Eight fresh detailed/compact pairs cover the original seven diagnostic hours and the May 21 topology transition. All eight converge and pass full-network KCL, input-profile preservation and recovery checks. The maximum paired complex-voltage difference is {repV:.4g} pu and the maximum paired physical-branch current difference is {repI:.4g} A. A separate primitive-branch calculation validates current reconstruction without using the production reduction operators.

The annual run attempts all {source:,} source-qualified hours on the original 8,760-hour axis. Compact ACPF qualifies {solved:,} hours under the equation/profile gates; {source-solved:,} attempted hours do not qualify. The primary comparison retains {pairs:,} paired hours from the frozen detailed baseline. Additional compact successes: {new}; lost detailed successes: {lost}. The 109 source-excluded hours remain marked and are not silently simulated or filled. Numerical failure does not prove that a physical solution is impossible.

Across that complete paired cohort, the maximum complex-voltage difference is {annual['maximum_paired_complex_voltage_difference_pu']:.6g} pu and the maximum original-branch current difference is {annual['maximum_paired_original_branch_current_difference_A']:.6g} A. The runner's acceptance thresholds are 1e-7 pu for voltage, 1e-4 MW/MVAr for power components and 1e-3 A for current; these thresholds are independent of public-interface fitting errors.

Maximum compact-versus-frozen-detailed discrepancies on the paired cohort:

{table(recovery_rows, ['Quantity','Maximum absolute difference','Units','Compared values'])}

Angle differences use an explicitly common reference gauge. Currents are compared on original branch keys and active masks, including the appropriate dated topology. Terminal-current bases use the corresponding endpoint kV; series current excludes charging and uses the receiving-side winding base on transformer rows. On equal-voltage overhead conductor sections it is the current used for Joule heating. Currents are amperes on the original 100-MVA-base synthetic model and are **never divided by gamma**.

The default paired policy has reactive-limit enforcement disabled, matching the frozen detailed run. In the separate seven-hour mode-1 comparison, both models converge on {len(qlimit['both_converged_hours'])} hours and fail on the same {len(qlimit['detailed_failed_hours'])} hours. Every converged pair matches; failed iterates are not treated as equivalent solutions. Q/converter-reactive bounds pass at those converged points, while voltage and slack active-power bounds still fail. This is a control-response validation, not a refit of the default annual results. Mode 2 also matched at hour 8508 before the performance-only edits; that explicitly retained earlier test required {core['historical_mode2_comparison']['compact_outer_iterations']} control iterations.

Source and operator fingerprints reject stale cached reductions after input, tap, shunt, resistance, status, mapping or recovery-operator edits. Rebuild after each physical `R(T)` update in an electrothermal iteration. The compact implementation does not run a full-network Newton solver internally.

Evidence: [fresh paired cases](output/nygrid_2025_compact_ac/validation/representative_pairs/representative_pair_receipt.json), [independent saved-point recovery](output/nygrid_2025_compact_ac/validation/independent_reference_recovery.json), [annual replay](output/nygrid_2025_compact_ac/validation/annual_compact_PF_receipt.json), [independent annual current/KCL review](output/nygrid_2025_compact_ac/independent/annual_arrays_independent_review.json), [reactive-limit pairs](output/nygrid_2025_compact_ac/validation/Q_limit_pairs/Q_limit_pair_receipt.json), [all paired error statistics](output/nygrid_2025_compact_ac/alignment/paired_recovery_errors.csv), and [core/control/guard review](output/nygrid_2025_compact_ac/independent/compact_core_review.json).

## NYISO load and interface alignment

All 96,360 hour-zone load values in the existing 11-zone, 8,760-hour source mapping reaggregate to public NYISO measured load after the original aggregate scale conversion; the previous audit's maximum difference is {previous_alignment['NY_load']['maximum_public_scale_zone_reaggregation_error_MW']:.4g} MW. Compact recovery preserves input PD and QD exactly on the evaluated hours, with maximum source differences {scoring['maximum_recovered_PD_vs_frozen_source_error_model_MW']:.3g} MW and {scoring['maximum_recovered_QD_vs_frozen_source_error_model_MVAr']:.3g} MVAr. This is a construction identity, not an independent forecast or validation of within-zone bus allocation.

The within-zone shares remain static, including the equal split between buses 81 and 82 in Zone J. External-area demand still uses historical bus allocation and the NY statewide time shape. Native generator profiles are bounded source-prior reconstructions rather than observed unit dispatch. NYISO measured grid load is net of behind-the-meter solar and demand response; it is not gross end-use demand. These inherited source assumptions are documented in the [profile source audit](output/nygrid_2025_acpf_profile_audit/alignment/profile_alignment_summary.json).

The interface comparison uses recovered original branch terminals with the previously sealed membership, signs, UTC hours, scale and dated masks. No reduced matrix edge flows are used. The seven internal-interface comparison series are not used to initialize, tune or fit the compact solver; the prescribed boundary schedules retain their documented public-data sources. WAPE is `100 * sum(abs(model-public)) / sum(abs(public))`. On the **same {pairs:,}-hour paired cohort**, using the inherited signed literal-from convention:

{table(interface_rows, ['Interface','Detailed WAPE','Compact WAPE','Compact MAE, public MW'])}

The compact model preserves the detailed model's alignment; it does not improve those public errors. The source-side and target-side terminal conventions are also exported as separate diagnostics. They are different metering definitions, not a confidence interval. Physical P32 meter membership and the original `Flow(MWH)` field's interpretation as hourly average MW remain uncertified. Only aggregate MW is divided by the frozen gamma={previous_alignment['gamma']:.17g}; currents are not rescaled.

Evidence: [comparison contract sealed before results](output/nygrid_2025_compact_ac/alignment/comparison_contract.json), [scoring receipt](output/nygrid_2025_compact_ac/alignment/scoring_receipt.json), [annual/monthly metrics and terminal conventions](output/nygrid_2025_compact_ac/alignment/public_interface_metrics.csv), and [explicit hour cohorts](output/nygrid_2025_compact_ac/alignment/comparison_cohort.csv).

## Remaining physical qualification

**{qualified:,} of the {solved:,} compact equation/profile-qualified hours pass the inherited joint voltage/generator/converter assumption gate.** In the default solved cohort, voltage ranges from {good.min_voltage_pu.min():.6f} to {good.max_voltage_pu.max():.6f} pu. The original slack's active-power adjustment ranges from {good.reference_PG_change_MW.min():.3f} to {good.reference_PG_change_MW.max():.3f} MW to balance the AC losses omitted from the supplied lossless dispatch balance. Demand, other generators' active powers and the six transfer active-power targets remain fixed under the default policy.

These numerical currents are suitable for comparing the compact model with the detailed synthetic model. They are not measured NYISO line currents or proof that the supplied operating state satisfies real equipment capabilities. Generator Q/S capabilities are engineering assumptions, and the standard PV-converter behavior can violate the declared zero-Q transfer contract. Thermal overload is reported separately from PF convergence.

The inherited cable classification issues also remain: current overhead-labelled rows 300, 309, 310 and 386 conflict with source-documented underground/submarine corridors or proxy attachments. The 65 unresolved mixed-device equivalent rows have no verified internal conductor inventory. Compact recovery does not establish overhead DLR eligibility for them. Refer to the [asset/structure audit](output/nygrid_2025_acpf_profile_audit/structure/structure_audit.json) before assigning thermal physics.

## Use and reproduce

MATLAB and MATPOWER 8.1 must already be installed and on the path.

```matlab
cd('C:\\Users\\Holiday\\Desktop\\npcc_ny_lite_package_fixed\\WECC and NPCC Systems');
addpath('System Matpower Format');
[r, audit, recovered] = run_nygrid_2025_compact_acpf(8508);
assert(r.success && audit.reduction_and_equation_gate ...
    && audit.P_profile_preservation_gate);
assert(size(r.bus,1) == 148);
Iseries_A = r.recovered_line_current_A(:,3);
% Iseries_A(j) corresponds to recovered.branch(j,:), not a Yred coupling.
```

Check `audit.VQ_and_generator_assumption_gate` separately; it is false for this unchanged operating case. `audit.passed` additionally contains inherited equipment checks and is not a reduction-equivalence verdict. A saved example can be loaded with `load('output/nygrid_2025_compact_ac/models/compact_ac_h8508.mat','model')` and passed as the wrapper's first argument.

The [implementation README](scripts/nygrid_2025_compact_ac/README.md) explains input changes, current bases and solver scope. [Public constructor](System%20Matpower%20Format/npcc_nygrid_2025_compact_ac.m) and [PF wrapper](System%20Matpower%20Format/run_nygrid_2025_compact_acpf.m) are the supported entry points. Validation scripts are under `scripts/nygrid_2025_compact_ac/validation`; source alignment scripts are under `scripts/nygrid_2025_compact_ac/alignment`.

Verify the delivered bytes without rerunning the simulations:

```powershell
python scripts/nygrid_2025_compact_ac/finalize_delivery.py --verify
```

Rerunning numerical scripts changes timestamped receipts and MAT-file bytes; rebuild the report, repeat the final review and reseal the manifest for a new run. The [delivery manifest](output/nygrid_2025_compact_ac/DELIVERY_MANIFEST.json) binds the implementation and evidence. It also verifies that all detailed model and prior audit files are byte-identical to baseline commit `3d2d3104879815180b82804861788dd132aed729`. Unrelated working-tree changes are outside this delivery.
'''
    (ROOT / 'NYGRID_2025_COMPACT_AC.md').write_text(text, encoding='utf-8')
    print(json.dumps(dict(passed=True, report='NYGRID_2025_COMPACT_AC.md', paired_hours=pairs, compact_successes=solved)))


if __name__ == '__main__':
    main()
