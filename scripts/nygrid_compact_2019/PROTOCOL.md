# Matched 2019 comparison protocol

This experiment applies the released NYgrid historical-input DC methodology to the compact NPCC-derived New York network. It does not replace the preferred 71-bus year-end-2025 AC/DLR case.

## Scope fixed before running the new comparisons

- Use all 8,760 saved 2019 local-clock NYgrid hours, including previously identified poor hours and source-quality flags. These hours have already been examined: results are retrospective diagnostics, not an untouched test set.
- Reproduce NYgrid with a New York-only internal network and explicitly extracted NY-side boundary injections. These boundary injections are model-derived, not observed terminal telemetry.
- Preserve all 46 original New York bus identities and the compact model's 200-bus ceiling. The pre-2025, 51-bus compact construction is the historical comparison parent.
- Use the existing fixed 2019 benchmark multiplier, 0.358662225381536, consistently for all P injections, targets, and interface limits. Report both benchmark MW and equivalent actual-scale MW. Do not rescale reactances.
- Keep reconstructed generator input and solved generator output separate. Carry NYgrid's explicit bus-74 balancing adjustment into the reference transfer ledger; do not label it observed Indian Point output.
- Compare the compact metering convention with a separately declared NYgrid-role convention. Build operators from bus identities, represented zones, and active endpoints. Operator changes do not count as physical network improvements.
- Test the missing Marcy South path using the published release's two X values only as a DC representation experiment. Audit existing paths before adding or retiring anything. No AC resistance, rating, or conductor claim follows from this experiment.
- Use the five previously source-qualified 2019 compact hours for the network/input A-B-C-D matrix. Keep the original unqualified sixth hour excluded with its known coverage reason. Restore the previously unrepresented H-generation role explicitly in this comparison, with its landing assumption recorded.
- Test allocation choices separately where source components are available. Do not fit per-hour interface offsets, change observations, or move balancing injections to minimize error. Any source component unavailable for a faithful ablation is reported as such.
- Rank all eligible new compact predictions by pooled absolute error divided by pooled absolute observed flow. Also report minimax rankings, every interface, actual MW, wrong-direction flags, and the annual distribution. No denominator floor or hidden near-zero exclusions.
- Attempt a separate bounded AC reconstruction for promising declared candidates. Report dispatch movement and incremental flow error. A converged DC case is not an AC- or DLR-qualified case.

No continuous parameter optimization or new holdout-accuracy claim is included in this first diagnostic package. Shared-parameter training and genuinely unexamined evaluation periods require a subsequent frozen protocol informed by these results.

## Crosswalk resolution before the B-arm calculation

The current source reconstruction places nonzero K generation at added terminal 9003, absent from NYgrid. For the common-port B arm, eliminate the five compact-only terminals exactly in the DC nodal equations and freeze the resulting injection map onto the 46 original NY ports. Terminal 9003 shares its injection equally between 78 and 80 because its two registered X values are equal. Verify retained angles and every reconstructed compact branch flow before applying this map to the reference network. C and D retain all 51 buses. B therefore includes an explicit compact-network-derived spatial aggregation; it is not a comparison with independently observed terminal generation.
