# Proposed colleague handoff: model history and DLR research scope

This outline describes saved evidence inspected at commit `8188cbec1172219a0414881121ad042b405a4044` on `codex/s13-phase1b-upny-coned`. No power flow was rerun for this inventory and no earlier model or result was modified. The accompanying [machine-readable inventory](model_and_modification_inventory.json) supplies exact source paths, line references, hashes, model counts, and API signatures.

## 1. Put the model choice and qualification boundary first

The latest entry point, `run_nygrid_2025_loss_consistent_acpf`, is a **148-retained-bus, PF-only synthetic AC replay with explicit loss accounting**. It recovers detailed voltages and original branch currents. Of 8,651 eligible 2025 hours, 8,170 pass equations, recovery, and accounting; 481 are rejected. This loses 324 prior successes and gains none. Another 109 hours remain source-excluded. **No hours pass the joint voltage/reactive/generator-capability gate.** It is a conditional research baseline, not an operationally qualified NYISO DLR case.

The separate, older `run_nygrid_2025_ac_dlr` runs full-network ACOPF with steady overhead ampacity constraints, bounded native redispatch, and fresh PF replay. Four of eight weather/operating attempts qualified. Those points use the earlier engineering parameters and operating policy. Their thermal and operating proofs cannot be transferred to the latest replay.

Sources: [latest revision](../../NYGRID_2025_AC_LOSS_REVISION.md), [engineering AC/DLR delivery](../../NYGRID_2025_AC_SYSTEM.md), and the two public API files under `System Matpower Format`.

## 2. Keep the two source families distinct

The older local ENLITEN/NPCC lineage leads through S7 to preserved S13-FULL construction checkpoints. S11 is a diagnostic reduction; S12 is a PERFORM oracle. The promoted S14-NYISO operating case remains pending; an existing 86-bus S14-labelled external-reduction diagnostic is a different artifact. Separate 51-, 66-, and 71-bus NY-only studies retain their own assumptions and results. The generic `LATEST_MODEL_CONFIGURATION.csv` still selects a 71-bus model from that family, not the current NYgrid replay.

Retain the associated historical milestones in the package: Phase 1C has 170 buses/315 branches; its external reduction has 86 buses/182 branches but no successful bounded operating qualification. Package A establishes one assumed historical PERFORM reference. Package B is an optional 878-bus/1,375-branch/595-generator regional candidate with its own bounded AC proof. Neither is a contemporary NYISO or DLR certificate. The 51-bus testbed, calibrated 66-bus case, source-generation 66-bus alternative, and 71-bus partial-SPC case are successive small NY-only experiments, with distinct scale, boundary, calibration, and thermal contracts.

The current chain starts from Cornell's pinned NYgrid release. Its original NPCC file has 140 buses and 227 branches, versus 233 branches in the local ENLITEN original. The Cornell release adds the 38–77 and 43–38 E–G aggregate paths; these pairs are absent from the inspected original and S7 cases. Common NPCC ancestry does not establish identical network response, accounting zones, dispatch, scaling, or thermal qualification.

Sources: [historical project handoff, especially lines 21–119](../../PROJECT_HANDOFF.md), [full 2019 reconstruction](../../NYGRID_2019_DLR_REBUILD.md), and [branch-224 lineage](../nygrid_2025_ac_loss_revision/impedance/branch224_lineage.csv).

## 3. Present the complete NYgrid development sequence

1. **Reproduce 2019:** pin the author repository; run the 57-bus, 94-branch, 271-generator, four-DC model; repair five plotting-index errors without altering solved physics. Verify load preparation and investigate shared western errors.
2. **Restore the full network:** create the unreduced 140-bus, 225-AC-branch counterpart with all 8,760 prepared 2019 states, branch lineage, and initial synthetic thermal-exposure screens.
3. **Build 2025 operating inputs:** establish a physical UTC/DST hour axis and source masks; assemble the 2,245-identity fleet register; map 1,436 admitted native and 28 external/HQ generator rows; project hourly priors into finite active-power bounds. The initial 8,663-hour dispatch cohort later becomes 8,651 after external-source qualification.
4. **Add Downstate detail:** expand to 191 buses and 410 records with 51 additional terminals, 97 historical PERFORM circuits, nine registered predecessor replacements, explicit attachment assumptions, and dated RCC/Dover events. Keep optional NYES and asset-placement cases diagnostic.
5. **Build the smaller DC case:** retain all 140 original buses plus eight named 345-kV stations; eliminate only 43 added zero-injection nodes. The 148-bus case has 274 records, including 30 DC equivalent edges, with detailed-source branch recovery.
6. **Repair operating-source mappings:** apply confirmed Moses hydro and western/Lewiston corrections. Preserve the corrected generator-landing vector, which differs from the raw dispatch template on 81 rows. Use consistently signed actual regional exchanges while retaining the declared source-prior reconstruction.
7. **Represent Ontario controls:** replace aggregate branch 211 electrically with separate PS33 and PS34 transfer equivalents, keeping its inactive provenance record. The original four DC schedules remain; six `dcline` records do not mean six physical HVDC assets.
8. **Audit source definitions:** archive seasonal physical flowgate definitions and P34 direction, unit, time, and signal-origin qualifications. No complete physical 2025 mapping is established for the seven inherited model gates.
9. **Apply project parameters:** update F84 and the Staten cable route estimate, then introduce Dover's explicit parallel PAR banks, regulated port, heterogeneous line sections, and conditional bounded phase reconstruction. Its detailed reference becomes 192 buses/413 records; the retained DC case stays 148/274.
10. **Construct engineering AC/DLR:** add finite R/X/B, conductor/cable/equipment metadata, Q/S assumptions, current constraints, 75 numerical section nodes, and declared fixed-reactor assumptions. The detailed cases have 266 buses/485 records before Dover and 267/488 afterward.
11. **Audit unchanged-profile ACPF:** obtain 8,494 numerical equation/profile-qualified hours and 157 failed NR hours, but zero joint operating-qualified hours. Inventory cable conflicts and all bus lineage.
12. **Reduce AC exactly:** implement a general complex-admittance 148-bus solver with original-current recovery. Validate all 8,494 paired hours plus mutation and control guards. Reduction does not create physical reduced edges or an OPF model.
13. **Diagnose Central East:** separate network-construction effects from same-network AC effects using controlled DC bridges and posthoc reconstructions from solved losses. Preserve those experiments as diagnostics, not implicit repairs.
14. **Implement the latest revision:** restore parent 224's complete released tuple `(0.02, 0.0147, 0)` as an explicitly unresolved network equivalent, remove its conductor/DLR claims, and implement the coupled loss-aware Newton policy. Preserve the complete 8,170-hour qualified replay and its failures.

The inventory links each stage to its root report and evidence. “Historical source circuit,” “added model record,” “numerical section,” and “newly commissioned physical asset” must remain distinct terms.

## 4. Explain the numerical and operating contracts

All current electrical cases use a 100-MVA base. The 2025 public-to-model power factor is `gamma = 0.30012075175285535`. Apply it once to aggregate power inputs/comparisons. **Do not rescale per-unit impedance or divide solved AC amperes by gamma.** The older compact-2019 comparison uses a different gamma.

The compact AC model eliminates passive interiors from a general complex admittance matrix and recovers full voltages plus `Yf*V`, `Yt*V`, and `Yseries*V`. Resistance, charging, fixed shunts, taps, and phase shifts are included before reduction. New interior injections or controls require retained ports. A change in R(T), status, tap, phase, or shunt requires a fresh valid reduction. Do not confuse this matrix model with the older DC-only Schur branch table.

The latest loss policy enforces `NY gross demand = served PD + assigned NY loss`. Within-NY corridor losses are split between endpoint zones. External generator equivalents supply their regional and NY-border losses under finite bounds; native PG, HQ, and six transfers stay fixed. NY Q demand scales with served P demand and external Q-circle assumptions change with PG. These are declared modeling choices, not measured zonal losses. The maximum qualified allocated loss fraction is 95.45%, a major physical-interpretation limitation despite exact accounting.

## 5. Give one entry point per purpose

From the repository root in MATLAB, with the verified MATPOWER installation on the path:

```matlab
addpath('System Matpower Format');
[r, audit, recovered, allocation] = run_nygrid_2025_loss_consistent_acpf(8508);
assert(r.success && audit.reduction_and_equation_gate && audit.loss_allocation_gate);
Iseries_A = r.recovered_line_current_A(:,3);
% Check audit.VQ_and_generator_assumption_gate separately before operating claims.
```

`r.bus` contains the 148 retained states. The current row axis is `recovered.branch` and its source branch keys. Columns are from-terminal, to-terminal, and series amperes. Do not interpret matrix couplings as conductors or call generic `runpf` on the compact matrix object.

For the frozen DC comparator, use `npcc_nygrid_2025_dover_dc(h,'bounded','x_nominal')`, `rundcpf`, and `npcc_nygrid_2025_slim_interfaces`. For older full-engineering thermal snapshots, use `run_nygrid_2025_ac_dlr` and its own `audit.passed`. These APIs implement different operating policies and are not interchangeable.

## 6. State the DLR physics and asset boundaries

The OH kernel uses series current for Joule heating, explicit circuit/bundle multiplicity, manufacturer resistance points, and declared heat-capacity/surface assumptions. Separate section-end envelopes include charging. Hardware limits apply at original terminals and actual voltage. Voltage-changing composites are not direct OH conductors. Cable ampacity needs burial, soil, duct, bonding, and cable-specific thermal data.

The older AC/DLR snapshots fix reference resistance at 75°C for ACSR or 95°C for ACSS and evaluate ampacity at temperature caps. They are neither transient temperature trajectories nor solved steady electrothermal equilibria. Weather was uniform 25°C, perpendicular wind of 0.6096 or 2 m/s, 1,000 W/m² solar, and 101,325 Pa; it was not observed route weather.

Before physical DLR, exclude parent 224 and resolve OH/cable conflicts at rows 300, 309, 310, and 386. The 40 cable-like equivalent rows and 65 mixed-voltage equivalents do not identify all hidden physical assets. After 224's exclusion, the latest case retains 255 thermal segment metadata rows before Dover and 257 afterward, representing 256 post-Dover electrical rows. These are metadata counts, not physical eligibility certificates.

## 7. Keep validation and failure cohorts inspectable

Separate the 8,760 clock positions, 8,651 eligible source hours, 8,494 earlier PF successes, and 8,170 latest successes. On the same 8,170 hours, Central East WAPE changes from 43.5042% to 13.7038%. The previous 45.0359% uses all 8,494 old successes and is a different scope. WAPE is a ratio of sums, not a mean of hourly percentage errors. The three terminal conventions are different operators, not confidence bounds. Failed iterates are not predictions; failure does not establish global infeasibility.

Link the annual producer receipt, independent physics/accounting review, full metric table, P34 qualifications, asset audit, and delivery manifests. Distinguish fresh inspection of preserved evidence from a new numerical rerun.

## 8. Give a staged research plan

Freeze the electrical case, scale, topology/operating years, and loss policy. Resolve asset eligibility and source uncertainty. Establish suitable bounded operating states and route-segment weather. Implement the chosen steady or transient temperature treatment; rebuild the AC equivalent when R changes and audit recovered series, terminal, and hardware currents. Then specify redispatch/control objectives and a comparable static baseline before estimating DLR benefits. Economics, security, commitment/ramping, and storage energy each require their own validation.

The latest case is PF-only and rejects thermally prepared inputs. Combining it with the older DLR/OPF adapter is new work, not a delivered feature. Do not select resistance or allocation assumptions merely to obtain convergence or lower NYISO error.

## 9. Separate portability and source rights from scientific claims

The package owner should provide runtime/toolbox requirements, portable paths, archive layout, hashes, and source-sharing qualifications. A manifest validates bytes and provenance closure, not equipment truth. Preserve old reports as dated milestones: the earlier P34 readiness assessment predates the later engineering AC/DLR adapter, while the generic 71-bus “latest” pointer still belongs to its separate model family.
