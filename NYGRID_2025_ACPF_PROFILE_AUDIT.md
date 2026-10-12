# Profile-driven ACPF verification for the 2025 DLR study

The current model does **not yet satisfy all requirements for a physically qualified, NYISO-aligned annual DLR baseline**. ACPF is sufficient for the requested study; this audit uses no ACOPF. It verifies the generation/load profiles directly, rather than replaying an ACOPF operating point. Numerical solutions exist for most tested hours, but the current loss-balancing and reactive-control assumptions fail the declared operating checks. Zonal load totals agree by construction, while bus allocations and several cable/overhead identities remain unresolved.

Audited model: commit `330be1d90e6faab8d6c32c3d6c174aa364a30c73`, branch `codex/s13-phase1b-upny-coned`. This is a new audit namespace. The original model, profiles, and prior sealed results remain byte-preserved. The earlier successful OPF-seeded ACPF replays do not establish the result requested here.

## What was run and what passed

The calendar has 8,760 hourly positions in 2025, identified in UTC with the local New York year and DST preserved. Upstream generation/source qualification covers 8,657 hours; the established common replay mask excludes six more, leaving **8,651 attempted hours**. All 109 excluded positions remain in the monthly arrays with explicit false qualification flags and missing results.

Each qualified hour uses the public AC loader's profiles, initial voltage/angle state, line parameters, dated topology, and six scheduled controlled transfers. MATPOWER legacy Newton-Raphson runs with `pf.enforce_q_lims=0`, tolerance `1e-10`, and a 50-iteration limit. No previous PF/OPF solution or internal NYISO interface observation initializes the annual run. A cache was used only after 13 exact numerical parity checks against the public loader, including topology boundaries and DST cases.

- Default NR converged in **8,494 / 8,651** attempted hours.
- **8,494** hours pass independent AC nodal-balance and profile-preservation checks and enter the matched interface comparison.
- **0** of these hours passes all declared voltage, generator P/Q/S, and converter-Q checks together.
- The 157 failed hours, all in July-August, were retried with both flat initial voltages and earlier equation-qualified PF voltages, preserving the source profiles, generator voltage targets, transfer controls, and network. **0 recovered in 314 additional attempts**. They remain unresolved under these tested initializations; this is not a global infeasibility proof. The [initialization-recovery receipt](output/nygrid_2025_acpf_profile_audit/acpf/NR_recovery/NR_recovery_receipt.json) keeps the failures separate from the annual results.

| Check on converged, equation/profile-qualified hours | Passing hours |
|---|---:|
| Normal voltage limits, 0.95-1.05 pu | 0 / 8,494 |
| Generator active-power limits | 0 / 8,494 |
| Generator reactive limits | 0 / 8,494 |
| Assumed generator apparent-power capability | 0 / 8,494 |
| Six controlled transfers: stated reactive limits | 0 / 8,494 |
| All preceding V/Q/generator checks together | 0 / 8,494 |

Among the equation/profile-qualified outputs, solved voltage ranges from **0.8544 to 1.1201 pu**. The single original slack unit supplies **144.0-869.3 MW** of additional active power. At hour 8508, that adjustment is about 246.45 MW while the unit's hourly Pmax is about 2.10 MW. Non-slack PG, demand P/Q, and the six transfer P schedules are preserved. Thus it is inaccurate to say that every generator profile is unchanged after PF: the slack output necessarily changes to cover losses.

The lossless input schedules balance aggregate generation and demand before AC losses. A feasible ACPF implementation therefore needs a declared loss-allocation policy, such as bounded participation among available generators or explicit balancing resources. This does not require an economic optimizer. Generator capability limits are engineering assumptions here, not measured unit capability curves. The six-transfer PF representation also regulates terminal voltage using converter reactive injections that are not constrained by the declared zero-Q contract in ordinary Q-unlimited PF. These are operating-model issues, not just solver tolerance issues.

An additional standard PF control test enabled `pf.enforce_q_lims=1` on the same seven representative profiles, permitting PV-to-PQ conversion without OPF or parameter changes. **5 / 7 converged** and passed generator-Q and converter-Q checks, but all of those retained voltage and slack-generator capability violations. Hours 4194 and 8471 did not converge under that control variant. This shows that ordinary Q-limit handling can resolve the unlimited-Q artifact in some cases, while it does not by itself produce the requested qualified operating points. Failed-iterate voltages are excluded from the solved-voltage ranges above. See the [reactive-limit sensitivity receipt](output/nygrid_2025_acpf_profile_audit/acpf/Q_limit_sensitivity/Q_limit_sensitivity_receipt.json).

Thermal or static branch overloads were **not** used to reject PF convergence: overload exposure can be the object of a DLR study. Conversely, numerical current availability does not certify conductor temperatures, voltage adequacy, equipment ratings, or a secure operating schedule. The broad 0.90-1.10 pu diagnostics are also recorded separately; the ordinary voltage gate uses the case's 0.95-1.05 pu limits.

Evidence: [annual solver receipt](output/nygrid_2025_acpf_profile_audit/acpf/annual_profile_PF_receipt.json), [hourly operating checks](output/nygrid_2025_acpf_profile_audit/acpf/annual_hour_quality.csv), [cache parity checks](output/nygrid_2025_acpf_profile_audit/acpf/cache_parity_and_benchmark.json), and [seven complete representative cases](output/nygrid_2025_acpf_profile_audit/acpf/representative_profile_PF_receipt.json). Monthly MAT files retain 267 canonical bus IDs and 488 canonical branch keys, presence/active flags, P/Q terminal flows, voltages, generation aggregates, and currents. Absent pre-Dover elements are not confused with row-position padding.

## NYISO load and generation agreement

All **96,360 hour-zone values** (8,760 hours x 11 zones) reproduce the NYISO public zonal load series within **9.09e-13 MW** after dividing aggregate synthetic power by gamma. This validates ingestion and reaggregation; it is a construction identity, not independent evidence that the within-zone bus demand is correct.

The 46 original NY bus records have 31 positive load weights. Within each zone, the inherited static weights are fixed through the year. Zone J uses a particularly coarse fallback: equal allocation to buses 81 and 82. The additional station/terminal and numerical line-section nodes have no demand. Therefore this model has not reconstructed 2025 substation-level load distribution. The 94 external bus records use historical magnitudes driven by the same statewide NY load shape; independent 2025 neighboring-region load profiles are not supplied.

The current generator input is `all_boundary_actual_dispatch.mat`: 1,436 native units and 28 regional external equivalents. The native profiles satisfy the declared hourly P bounds and the load/import accounting identities. They are a bounded reconstruction from public fuel/availability/fleet information and regional exchanges, **not observed unit-by-unit dispatch**. Commitment, ramping, reserves, and storage-energy feasibility are not established by that reconstruction. Keeping external PG and controlled-transfer P fixed does not preserve measured net AC border exchange after AC losses.

NYISO's measured load is net of behind-the-meter solar and demand response. The frozen variable name `bus_gross_pd` means that separately modeled generation is not subtracted again; it must not be read as gross end-use demand. The NYISO-authored November 2025 operations presentation independently distinguishes the June 24 HB18 measured 31,857 MW from 33,799 MW after adding BTM solar and demand response. See [load semantics and primary-source locator](output/nygrid_2025_acpf_profile_audit/alignment/load_source_semantics.json).

Evidence: [profile/source summary](output/nygrid_2025_acpf_profile_audit/alignment/profile_alignment_summary.json), [zone weights and annual reconciliation](output/nygrid_2025_acpf_profile_audit/alignment/load_zone_allocation_audit.csv), [source qualification by hour](output/nygrid_2025_acpf_profile_audit/alignment/source_comparison_cohort.csv), and [saved-case preservation checks](output/nygrid_2025_acpf_profile_audit/alignment/representative_profile_preservation.csv).

## Interface agreement: a matched diagnostic comparison

The following compares the frozen DC baseline and new profile-driven ACPF on exactly the same **8,494** equation/profile-qualified hours. Both use the existing synthetic power scale, gamma = 0.300120751753. Only aggregate interface MW is divided by gamma for comparison; no physical current or impedance is rescaled. The observed series is held out from all profile, line-parameter, and operator construction.

| Interface | Matched DC MAE, public MW | ACPF MAE, public MW | DC WAPE | ACPF WAPE |
|---|---:|---:|---:|---:|
| DYSINGER EAST | 258.1 | 329.0 | 30.5% | 38.9% |
| WEST CENTRAL | 254.9 | 330.5 | 46.2% | 59.9% |
| TOTAL EAST | 423.8 | 496.3 | 13.4% | 15.7% |
| MOSES SOUTH | 120.0 | 120.7 | 22.5% | 22.6% |
| CENTRAL EAST - VC | 310.6 | 755.0 | 18.5% | 45.0% |
| UPNY CONED | 230.4 | 228.5 | 7.7% | 7.7% |
| SPR/DUN-SOUTH | 175.1 | 167.2 | 9.5% | 9.1% |

MAE is mean absolute error. WAPE is `100 * sum(abs(predicted-observed)) / sum(abs(observed))`, avoiding undefined hourly percentages near zero flow. DC entries were recomputed on the matched ACPF cohort, not copied from the older full-year score. This is an end-to-end model comparison: the AC engineering layer also changed some R/X values and introduced charging and reactors, so the error difference cannot be attributed to AC losses or reactive physics alone. The complete monthly and post-Dover comparisons are in [interface metrics](output/nygrid_2025_acpf_profile_audit/comparison/interface_metrics.csv).

These are the seven **inherited NY-zone cut diagnostics**. Current branch membership was independently checked in all four dated topologies, including sectioned endpoints and retired branches. They are not yet certified physical NYISO P-32 meter definitions. The legacy public P-32 field is labeled `Flow (MWH)`; its numeric-as-MW convention remains inherited and qualified, without a fitted conversion factor. The primary AC convention sums signed flow at each original corridor's literal from terminal. Sending-side and receiving-side alternatives use the appropriate PF/PT values and differ by the included corridor losses. They are meter-convention sensitivities, not statistical confidence intervals or bounds on true NYISO flow.

Consequently, low error for an individual diagnostic cannot establish physical interface accuracy, and the larger western/central discrepancies prevent a blanket claim of close agreement. The current mapping, profiles, and physical parameters were not adjusted to improve these scores. See [operator contract](output/nygrid_2025_acpf_profile_audit/alignment/interface_operator_contract.json), [terminal-convention differences](output/nygrid_2025_acpf_profile_audit/comparison/terminal_convention_differences.csv), and [scoring receipt](output/nygrid_2025_acpf_profile_audit/comparison/scoring_receipt.json).

## Underground cables and the current classification problem

The current branch ledger contains **40 cable-like AC equivalent rows**, expanded to 42 numerical cable sections. This is not an inventory of 40 individually verified physical cables. A primary-source and identity review distinguishes:

| Evidence tier for the 40 current cable-like rows | Rows |
|---|---:|
| Documented project feeder underground identities | 3 |
| Historical utility inventory with matching underground corridor endpoints | 11 |
| Related cable corridor, terminal aliases unresolved | 7 |
| Electrical characteristics or urban-network assumption only | 16 |
| Explicit synthetic network proxy | 3 |

Electrical clues such as cable-like capacitance, impedance, or an urban location support candidate classification but do not prove underground construction. Owner/PSC inventories, feeder identities, project documents, and endpoint reconciliation provide stronger evidence. Historical corridor evidence still does not identify every equivalent row, cable count, conductor construction, or burial ampacity.

The audit found **four currently overhead-classified rows with conflicting cable-corridor evidence**: row 300 (Shore Road-Dunwoodie/Y50), rows 309 and 310 (East Garden City-Sprain Brook/Y49), and row 386 (the synthetic Goethals-Gowanus attachment). NYPA and the PSC explicitly describe Y49 as underground/submarine. The two Y49-associated model rows do not prove two real physical Y49 circuits. The Goethals-Gowanus row is itself a synthetic aggregate attachment, so assigning it one particular owner feeder would also be unsupported.

These conflicts prevent physical use of overhead weather-based thermal equations on those route representations until the classification is corrected in a versioned model. Current cable rows use assumed static cable limits; underground ampacity needs an appropriate cable/soil/duct thermal model rather than the overhead conductor weather law. Controlled-transfer cable links such as Neptune and Norwalk-Northport are outside the 40 AC-row count. The 65 unresolved mixed-voltage composite equivalents also do not reveal every internal overhead/cable asset. Therefore the current ledger cannot be described as a complete physical line inventory for NYISO-wide DLR.

Evidence: [cable evidence tiers](output/nygrid_2025_acpf_profile_audit/structure/cable_evidence_tiers.csv), [four overhead/cable conflicts](output/nygrid_2025_acpf_profile_audit/structure/overhead_cable_classification_conflicts.csv), [controlled-transfer cable scope](output/nygrid_2025_acpf_profile_audit/structure/controlled_transfer_cable_scope.csv), and [primary source receipts](output/nygrid_2025_acpf_profile_audit/structure/source_receipts.csv). Sources are archived and their cited PDF pages were visually inspected. This audit records the conflicts without silently changing the sealed electrical model.

## Bus count and why it increased

| Model stage | Bus count | Explanation |
|---|---:|---|
| Original NPCC parent | 140 | Original bus records |
| Previous reduced model | 148 | Original 140 plus 8 retained additions |
| Restored full reference | 191 | Restore the other 43 of the full model's 51 additions |
| Full reference after Dover | 192 | One additional regulated device terminal |
| AC case before Dover | 266 | 191 plus 75 numerical line-section nodes |
| AC case after Dover | **267** | 192 plus those 75 numerical line-section nodes |

The 75 numerical additions comprise 73 overhead-section nodes and two cable-section nodes. They permit finite-section AC pi representations of long corridors and distributed charging; they are not additional substations or demand centers. All 75 have zero P/Q demand and zero bus shunt conductance/susceptance. The 51 full-reference additions also have no demand or relocated generators. The original buses are preserved. More nodes therefore reflect topology restoration and AC numerical representation, not a larger observed load or a higher-resolution reconstruction of customer demand.

The full lineage is in [all 267 bus records](output/nygrid_2025_acpf_profile_audit/structure/bus_lineage_all267.csv); the [8 retained additions](output/nygrid_2025_acpf_profile_audit/structure/retained_8_added_buses.csv), [43 restored nodes](output/nygrid_2025_acpf_profile_audit/structure/restored_43_buses.csv), and [75 numerical nodes](output/nygrid_2025_acpf_profile_audit/structure/numerical_75_buses.csv) are separately listed.

## What is needed for a usable ACPF-based DLR baseline

1. Adopt explicit loss participation with bounded generator headroom and an auditable reference-bus policy; preserve the intended profile shape and record the required balancing adjustments.
2. Represent PV/PQ switching, generator Q capability, and controlled-transfer reactive behavior consistently, then rerun ACPF and independently check KCL and voltage/capability bounds. Do not infer infeasibility from a single solver/control variant.
3. Resolve the identified overhead/cable conflicts before applying overhead DLR to real routes, and keep unresolved aggregate branches explicitly qualified.
4. Improve or independently validate within-zone bus-load allocation and physical interface membership/terminal conventions before claiming NYISO alignment. Keep engineering parameter selection independent of held-out interface observations.

No ACOPF requirement follows from these findings. The immediate need is a physically consistent ACPF operating and control model. A synthetic DLR experiment can still be studied with declared assumptions, but the present default profile replay is not a validated annual NYISO operating baseline.

## Reproduction and preservation

From the repository root, MATLAB commands for the main audit are:

```matlab
addpath('System Matpower Format');
addpath('scripts/nygrid_2025_acpf_profile_audit/acpf');
validate_cache_and_benchmark;
run_representative_profiles;
run_annual_profiles;
run_Q_limit_sensitivity;
retry_failed_profile_hours;
```

Post-hoc comparison and report generation, after refreshing any source/operator receipts whose dependencies were regenerated:

```powershell
python scripts/nygrid_2025_acpf_profile_audit/score_interfaces.py
python scripts/nygrid_2025_acpf_profile_audit/build_report.py
```

To verify the archived delivery without rerunning or changing its outputs, use `python scripts/nygrid_2025_acpf_profile_audit/finalize_audit.py --verify`. Regeneration changes runtime metadata and MATLAB file-header bytes. A regenerated delivery must refresh dependent audit/review receipts, run the finalizer without `--verify` to reseal those outputs, and then run `--verify`; the old manifest is not expected to validate newly generated bytes.

The audit's [summary](output/nygrid_2025_acpf_profile_audit/audit_summary.json) and [delivery manifest](output/nygrid_2025_acpf_profile_audit/DELIVERY_MANIFEST.json) bind the evidence and unchanged baseline. The prior whole-system AC delivery is preserved and remains an implementation record; this report supplies the more restrictive profile-driven qualification requested for the DLR study.
