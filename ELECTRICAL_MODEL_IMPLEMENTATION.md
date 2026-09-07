# Electrical work from the September 2026 review

The review correctly separates electrical qualification from assumed conductor
realization. This change implements the electrical construction, input,
reconstruction, residual-fit and external-reduction workflows. It does **not**
claim that the contemporary NYISO model or every roadmap completion gate is
finished. Thermal dynamics, weather, conductor sizing and estimator changes
are outside this change.

Run from the repository root with MATLAB, MATPOWER and Optimization Toolbox:

```matlab
out = run_electrical_model_reproduction;
```

The historical `run_handoff_reproduction` and Phase 1A/1B artifacts remain
available. The new runner writes its own evidence under
`output/electrical_model_review`; it never changes the promoted-case pointer.
Implementation regressions and scientific qualification gates are separate
CSV tables. A failed bounded solve is not a proof of physical infeasibility.

The verified run passes **130 registered implementation checks** and the
historical Phase 1A/1B artifact checks. The 170-bus Phase 1C inherited snapshot
reduces to **86 buses and 182 branches**, eliminating 84 external buses. Its
independent same-state replay has maximum voltage error about `1.1e-16 pu`.
This numerical identity does not qualify its operating limits: inherited
generation and branch-rating violations remain. All six bounded historical
reconstruction attempts fail to find a feasible point. Frozen 5/10-MW A-to-J
load transfers pass the reduction-response tolerances; 25–100 MW transfers
fail. Source capability is unqualified for all six transfer diagnostics.

The final generator-control export contains 402 records (67 per scenario),
including relocated downstate support and generation; its bounds and priors
are taken after the allocation transformation. It is not the pre-allocation
capability register. See `s14_direct_replay.csv` for separate source/reduced
P/Q, voltage, both-end MVA and angle-limit checks.

| Review stage | Implemented electrical work | Remaining completion condition |
|---|---|---|
| 1. Research contract | Historical/contemporary modes; source provenance; physical, synthetic and nonthermal classes | Thermal eligibility still requires an explicit realization and consistency tests |
| 2. Contemporary assets/inputs | Nine dated asset records; inherited generator inventory; 792 authentic zonal load observations over 72 August 2026 hours; actual-MW allocator and accounting validation | Electrical asset replacement parameters, unit crosswalk, and matched generation/interchange observations |
| 3. Downstate construction/controls | 21 terminals and 53 source electrical elements; source identity and passive-admittance checks; bounded AC reconstruction; conserved operating-device redistribution; explicit regional meters | Resolve aggregate overlaps, source voltage-support assumptions and demonstrate feasible representative public operating points |
| 4. Calibration/reduction | Registered passive residual fitter; NPCC-only external Schur reduction with passive tap synthesis; fixed bounded snapshot injections; independent PF replay and frozen transfer diagnostics | Approved same-vintage port-admittance calibration targets and independent behavior gates |
| 6. Reproduction/evidence | One runner, source hashes, adversarial tests and separate qualification ledger | Current-vintage and independently held-out evidence adequate for research conclusions |

## Review corrections and claim boundaries

The source places Dunwoodie and Sprain Brook in Zone I. The Phase 1C operator
therefore distinguishes H–I northern approaches, I–J receiving paths and K–J
paths; it does not assert a direct H–J circuit cut. Existing UPNY–ConEd and
downstate operators remain partial model operators. Their public missing terms
are not set to zero or used as exact calibration targets.

The legacy hours are scaled **operating patterns**, not a mathematical
similarity transform of network admittance. Historical availability is a
declared `gamma × PERFORM installed capacity` assumption, separate from
dispatch priors and observed generation. It replaces the inherited A/B/C
participation restriction only in the new research input transformation.
Generation location weights and the initial 0.9-power-factor Q envelope are
explicit assumptions. The downstate allocation moves existing zonal totals
and bounded capability rather than adding source devices on top of them.

The public project sources support dates and facility types; they do not
provide a complete MATPOWER R/X/B, controls and replacement mapping. The
contemporary register therefore does not silently instantiate those projects
with invented impedances. CHPE remains a controlled DC import; cables,
transformers and boundary equivalents are outside overhead DLR. The source
URLs, vintage distinctions and raw-load hashes are recorded in
`System Matpower Format/NY_Lite/research_model_contract.md` and the associated
`contemporary_*` registers.

## Electrical algorithms

`reconstruct_ac_operating_point` minimizes uncertainty-weighted departure from
generation priors with weak bounded voltage/reactive regularization. AC nodal
balance, P/Q limits for every online generator including the reference,
voltage limits, branch apparent-power ratings and angle constraints are hard
constraints. Regional interchange meters have explicit from/to terminal
coefficients and tolerance bands. MATPOWER's angle-limit conventions are
used directly. The electrical network is fixed throughout the solve. An
independent fixed-input Q-limit PF checks the final dispatch and setpoints.
Excluded demand cannot disappear from accounting. The formulation uses finite
rectangular generator capability envelopes, not undocumented machine curves.

`audit_electrical_boundary_feasibility` works on connected external graph
components. It issues a necessary active-power infeasibility certificate only
when all component boundary controls and passive losses are accounted for.
Area-local capacity arithmetic is insufficient when other external areas are
connected. Missing control coverage is reported as unavailable, not infeasible.

`fit_registered_residual_network` fits only registered residual R/X/B inside
finite passive bounds, penalizes deviation from the initial parameters and
compares consistently eliminated terminal admittance. Targets must supply
source, voltage/power bases and matching vintage. Source physical rows remain
frozen. A rejected fit is returned separately for inspection and is never
installed into the accepted candidate. No NPCC overlap is marked resolved
without the needed source-backed target; the included known-residual test
verifies the algorithm, not the real corridor calibration.

`build_s14_external_equivalent` retains NY buses, source overlay terminals
and first external tie terminals. It derives only the non-NY NPCC admittance
and injection reduction. A positive diagonal conductance scaling permits a
passive branch-and-shunt realization with synthetic real taps, avoiding
negative-conductance shunts. If necessary it retains more external detail.
Every equivalent branch, shunt, injection and loss offset has a register.
S12 data cannot enter this electrical equivalent.

Mapped external PQ injections are bounded reconstructed **snapshot sources**,
not separate observed tie schedules or a regional dispatch controller. The
direct identity and replay checks are distinct from independent public-target
validation. Frozen-network scenario remapping is labeled separately from
held-out transfer tests, which keep the baseline equivalent and its injections
unchanged. Tests reject changed source admittance, injected fake solved flags,
changed frozen mappings, and nonpassive or singular reductions.

## Outstanding model qualification

The immutable Phase 1B aggregate paths and eight additional Phase 1C overlap
candidates remain unresolved. Local source identity alone cannot remove
double-counted aggregate paths. Some source circuit identities and load/control
correspondences also remain incomplete. The dated infrastructure register and
real 2026 loads do not constitute a matched 2026 operating snapshot.

Consequently the numerical S14 artifact is an **unpromoted electrical
diagnostic**. Read `qualification_gates.csv` and `historical_scenario_status.csv`
for actual solve outcomes. The next engineering inputs are same-vintage
terminal targets for the overlap fits, source-backed contemporary asset and
generator mapping, and matched operating controls. No thermal parameter may
be used to hide an unresolved electrical-model discrepancy.
