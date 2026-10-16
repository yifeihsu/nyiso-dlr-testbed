# Boundary-consistent 2025 AC replay

This separately versioned study uses the existing 148 retained voltage buses and
recovers the original physical-network bus voltages, branch powers, and currents.
It preserves the earlier models and results. It does not certify an as-built
New York network, observed dispatch, conductor ratings, or operational feasibility.

## Run one hour

MATLAB and the verified MATPOWER 8.1 installation must be on the path.

```matlab
cd('C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems');
addpath('System Matpower Format');
[r, audit, recovered, allocation] = run_nygrid_2025_loss_consistent_acpf(8508);
assert(r.success && audit.reduction_and_equation_gate);
assert(audit.loss_allocation_gate);
Iseries_A = r.recovered_line_current_A(:, 3);
```

`r.bus` contains the 148 retained buses. `recovered.bus` and `recovered.branch`
contain all original buses and runtime branch sections for that topology state.
The current columns are from-terminal, to-terminal, and series amperes; their row
axis is `recovered.branch`, not a compact-network edge list. Never divide amperes
by the public-data power scale `gamma`.

`r.success` means the AC equations and the declared loss policy passed. It is
deliberately separate from `audit.VQ_and_generator_assumption_gate` and
`audit.passed`, which also require the stated voltage and capability limits.
Always inspect these flags. A failed run can return a last numerical iterate for
diagnosis; it is not a valid result for averaging or comparison.

The input may also be an **unrevised** detailed case from
`npcc_nygrid_2025_ac(hour)`. Already revised or thermally prepared cases are
rejected to prevent applying the equivalent correction twice or retaining stale
conductor-limit state.

## What changes

1. Parent branch 224, Gilboa–Buchanan, is an added Cornell NYgrid E–G network
   equivalent, not an identified direct physical line. Its released total
   `(R, X, B) = (0.02, 0.0147, 0)` pu on 100 MVA is represented by its existing
   two equal numerical sections. The paper's reactance approximation is
   reproducible; the resistance, charging, route and equipment are not physically
   validated. The former geographic-chord conductor construction is removed for
   this equivalent, including its synthetic rating and temperature/DLR claims.
   The existing case has no branch-224 reactor to remove. Other branch parameters
   and bus shunts are unchanged.
2. NYISO P58 actual zonal load is treated as generation plus net interchange,
   hence as a boundary balance including losses. In the model,
   `served_PD(zone) + assigned_NY_loss(zone) = frozen_P58_target(zone)`.
   Loss of a within-NY corridor is split equally between its endpoint zones
   (all to that zone if both endpoints share one zone). This is a declared
   ownership rule, not an observed NYISO loss or meter allocation.
3. ISONE, Ontario and PJM external generator equivalents supply their internal
   losses plus losses of their AC corridors into New York. Their delivered-load
   proxies remain fixed. Frozen regional participation weights use bounded
   allocation and the original finite parent-generator P bounds. A saturated
   generator is removed from further participation; a deficient regional budget
   fails. No balancing amount falls back to Clay.
4. Native real generation, signed HQ injection, six controlled DC transfers and
   regional net-import targets at the NY terminals remain fixed. NY Q demand
   scales with delivered P demand at the inherited power factor. External
   assumed Q circles are recomputed using their revised real generation.

This contract currently requires zero modeled DC loss, zero bus conductance,
and no AC corridor between different external regions. The solver rejects
unsupported input contracts rather than silently allocating those losses.

## Numerical formulation and failure policy

The default kernel jointly solves voltage and loss allocation. It evaluates
each original series loss as `baseMVA * R * abs(Yseries * Vfull)^2`, allocates
those losses, and solves `Snetwork(V) - Sspecified(V) = 0` with an analytic
derivative of the loss-dependent injections. Line search requires positive NY
served demand and finite regional generation capability. The global active
balance is an identity under this allocation, so the reference remains an
angle/voltage reference and its final P is independently checked against the
original schedule.

All varying injections remain on retained buses. The existing complex-admittance
voltage lift and original-branch current recovery therefore remain exact.
`options.backend = 'detailed'` solves the same coupled equations on the detailed
network for independent comparisons. The final allocated case is also checked
by a conventional detailed MATPOWER PF in the representative validation.

A line-search failure near zero delivered zonal load is recorded as
`NY_delivered_load_domain_boundary`; other numerical failures retain their own
status. Neither status proves global infeasibility. Losses are never clipped,
negative served load is never accepted, and no failed iterate is promoted.

## Diagnostic options

```matlab
% Same loss policy with the previous synthetic engineering impedance:
o = struct('impedance_mode','legacy_engineering');
[r, a] = run_nygrid_2025_loss_consistent_acpf(8508, o);

% Detailed-network verification of the revised coupled equations:
o = struct('backend','detailed');
[r, a] = run_nygrid_2025_loss_consistent_acpf(8508, o);
```

`loss_mode = 'legacy_single_slack'` retains the old imbalance treatment only for
controlled diagnostics; its loss-policy gate is false. The earlier
`loss_solver = 'outer_fixed_point'` prototype remains available as explicitly
historical diagnostic code. It is not the annual production path. This public
revision is PF-only; OPF formulation callbacks are removed from the corrected
case so the former conductor rating is not reachable as a valid OPF constraint.

## Reproduce the annual delivery

Use a new run label; the annual driver refuses to overwrite an existing run.

```matlab
addpath('scripts/nygrid_2025_ac_loss_revision/validation');
receipt = run_annual_loss_policy('released_equivalent', ...
    'boundary_consistent', 'released_equivalent_boundary_consistent_replay');
```

```powershell
python scripts/nygrid_2025_ac_loss_revision/comparison/score_revised_profiles.py --monthly output/nygrid_2025_ac_loss_revision/validation/annual/released_equivalent_boundary_consistent_replay/monthly --annual-receipt output/nygrid_2025_ac_loss_revision/validation/annual/released_equivalent_boundary_consistent_replay/annual_loss_policy_receipt.json --variant combined
```

The scorer writes the named variant's comparison directory; preserve the
delivered comparison files before intentionally rerunning that command. The
delivered run retains all 8,760 positions, attempts the original 8,651 eligible
hours, and reports its intersection with the frozen 8,494 prior successes, new
successes, lost successes and physical-qualification flags separately.

No seven-interface observations are read by the solver or used to tune the
impedance, participation or load allocation. The inherited interface cuts and
all three terminal conventions are applied afterward to recovered original
branches. WAPE uses identical hours for each old/new comparison.

See the root `NYGRID_2025_AC_LOSS_REVISION.md` and the output namespace's
`DELIVERY_MANIFEST.json` for final results, evidence and preservation checks.
