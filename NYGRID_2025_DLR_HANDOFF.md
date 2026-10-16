# New York grid model handoff for DLR research

Prepared 13 October 2026. Model snapshot 8188cbec1172219a0414881121ad042b405a4044.

Prepared for a colleague continuing dynamic line rating research. This package brings together the model builders, public-data reconstructions, electrical and thermal assumptions, saved experiments, and independent validation completed through 13 October 2026. The model snapshot is commit 8188cbec1172219a0414881121ad042b405a4044. Packaging utilities and this manual form a new handoff layer; the earlier research evidence is preserved.

Use the latest 148-bus loss-consistent AC solver for equation and accounting studies, and its recovered original-branch currents for explicitly assumed thermal screening. It is not a validated historical operating case: 8,170 hours satisfy its AC and loss-accounting equations, but none satisfies the joint voltage, reactive and generator-capability gate. The existing bounded AC DLR optimizer belongs to the earlier engineering case and has a separate, limited qualification record.

| Research use | Status at handoff |
| --- | --- |
| Compact versus detailed AC mathematics | Validated on the stated cases and annual saved-array checks. |
| Public profile and interface comparison | Reproducible with explicit scale, masks, terminal conventions and incomplete physical flowgate mapping. |
| Synthetic conductor and weather screening | Usable on approved same-voltage overhead candidates, with declared assumptions and operating-point flags. |
| Historical asset DLR or operational limits | Not established. Actual conductor, critical-span weather, equipment limits and feasible operating states need further evidence. |

### Read this first

Start with the setup and smoke test. Then choose one model family deliberately, inspect the bus and branch ledgers, and keep electrical qualification, physical asset evidence and thermal qualification separate. Never assign conductor physics to a reduced admittance coupling or infer an installed ampacity from a zero MATPOWER rating.

Evidence: [Loss revision](NYGRID_2025_AC_LOSS_REVISION.md) · [Engineering AC and DLR](NYGRID_2025_AC_SYSTEM.md) · [Compact AC](NYGRID_2025_COMPACT_AC.md)

## Start and verify the package

Extract the archive into a writable directory. The package root contains System Matpower Format, scripts, output and vendor folders. Paths below are relative to that root, so no original user directory is needed. Use a licensed MATLAB installation. The setup helper uses the bundled MATPOWER 8.1 code by default; an explicit compatible external MATPOWER directory may be supplied.

```text
cd('C:\research\nygrid_dlr_handoff');  % your extracted directory
addpath(fullfile(pwd,'scripts','nygrid_2025_dlr_handoff','runtime'));
env = setup_nygrid_2025_handoff(pwd);
check = smoke_nygrid_2025_handoff(fullfile(pwd,'runtime_results'));
```

The smoke test checks representative topology, loss accounting, compact/current recovery and a declared thermal screening scenario. Read its saved receipt and any failed flags before using subsequent outputs. A successful smoke test establishes the packaged workflow on that machine; it does not turn the synthetic model into an operationally qualified grid.

### Run the current AC model

```text
[r, audit, full, allocation] = ...
    run_nygrid_2025_loss_consistent_acpf(8508);
assert(r.success && audit.loss_allocation_gate);
assert(audit.reduction_and_equation_gate);
Iseries_A = r.recovered_line_current_A(:,3);
physical_ok = audit.VQ_and_generator_assumption_gate;
```

Hour 8508 is a tested post-Dover example. For this point, the accounting and equation gates pass while the physical operating gate remains false. r.bus contains 148 retained buses; full.bus and full.branch contain the detailed network for that dated state. Current columns are from terminal, to terminal and series amperes, on the row axis of full.branch. Preserve the associated branch keys and presence/status masks.

### Offline integrity

Use the package verifier before running modified experiments. It checks the package file manifest and hashes, independently of Git. Original evidence receipts may contain their historical machine paths and commits; these are provenance records, not installation instructions. The handoff includes a mapping of packaged inputs and a separate clean-directory execution receipt.

Evidence: [Loss revision](NYGRID_2025_AC_LOSS_REVISION.md) · [Retained bus ledger](output/nygrid_2025_compact_ac/independent/bus_retention_ledger.json)

## Choose the correct model family

Several preserved models have similar names and different scientific contracts. The current NYgrid pathway starts from the pinned Cornell NPCC source and retains all 140 original buses. It is separate from the older S7 to S13 construction and S14 planning pathway, and from the earlier 51, 66 and 71 bus compact calibration studies. A generic older latest-model file must not select the research case implicitly.

| Family | Structure and purpose |
| --- | --- |
| 2019 released and full reconstruction | Released 57-bus DC model; separate 140-bus full parent with 225 AC records, 271 generators and four controllable-link records. |
| 2025 source-conditioned DC | 140 original buses and 1,464 generator rows, followed by 191/192-bus Downstate detail and a 148-bus DC reduction. |
| 2025 engineering AC | 266 buses / 485 branch records before full-service Dover; 267 / 488 afterward. Complete synthetic AC parameters, numerical sections and explicit limits. |
| 148-bus compact AC | Complex-admittance elimination of passive buses. Recover the detailed network; do not reinterpret reduced couplings as lines. |
| Loss-consistent AC revision | Same 148 retained voltages with released parent-224 equivalent and jointly solved boundary-consistent loss accounting. Preferred current PF entry point. |
| Earlier bounded AC DLR | Legacy engineering case with steady weather ampacity and bounded ACOPF. Four of eight archived weather snapshots qualify. |
| Earlier S7 S13 S14 and compact studies | Preserved provenance, calibration and alternative-method evidence. Their bus counts, scales and validation do not transfer to the current family. |

A controllable MATPOWER DC record is a modeling abstraction, not necessarily a separately identified physical HVDC asset. The current six records include external-device representations and Ontario PAR flow substitutions. Select models by public function and explicit variant, not by a MAT filename containing final or latest.

Evidence: [2019 parent](NYGRID_2019_DLR_REBUILD.md) · [2025 inputs](NYGRID_2025_OPERATING_INPUTS.md) · [Small bus DC model](NYGRID_2025_SLIM_DOWNSTATE.md) · [Compact AC](NYGRID_2025_COMPACT_AC.md)

## Network coverage and dated topology

The 148 retained buses comprise all 140 original NPCC buses plus eight 345-kV transmission stations. The original set contains 46 New York buses and 94 external buses; retaining the neighboring networks preserves their electrical distribution effects. Added stations are named ports, not extra fitted loads or generator capacity.

| Station | Bus ID | Purpose |
| --- | --- | --- |
| East Fishkill | 10858 | Separates Pleasant Valley and Wood Street circuit sections. |
| Wood Street | 10902 | Preserves the junction toward Pleasant Valley, East Fishkill and Millwood. |
| Ladentown | 10774 | Keeps Ramapo and Buchanan corridor sections distinct. |
| Dunwoodie | 10593 | Westchester receiving port. |
| East Garden City | 10589 | Long Island receiving port. |
| Gowanus | 11129 | Brooklyn receiving port. |
| Rainey | 11130 | Queens receiving port. |
| Cricket Valley | 20001 | F83 and F84 junction toward New England. |

The detailed Downstate model originally added 51 terminals. Forty-three of those are passive under the frozen injection placement and are eliminated in the compact model. AC engineering adds 75 zero-injection numerical section buses; they represent line discretization, not new substations. Post-Dover adds one passive regulated port. These yield 118 or 119 eliminated voltages.

| State boundary | Interpretation |
| --- | --- |
| Before 21 May 2025 | Pre-May construction state. |
| 21 May 2025 at local midnight | Gowanus–Greenwood RCC activation under the conservative next-midnight rule. |
| 30 May 2025 at local midnight | Goethals–Fox Hills RCC activation under the same rule. |
| 19 December 2025 at 23 EST | Dover full-service boundary, equal to 20 December at 04 UTC. |

Use the stored UTC clock and topology-state index. The precise modeled boundary can be an accounting convention derived from day-level commissioning evidence. It does not certify the exact switching instant, every 2025 outage, or a complete year-end asset inventory.

Evidence: [Downstate construction](NYGRID_2025_DOWNSTATE_REFINEMENT.md) · [Small bus DC model](NYGRID_2025_SLIM_DOWNSTATE.md) · [Dover parameters](NYGRID_2025_DOVER_PARAMETERS_APPLIED.md)

## Operating data and scale

The current model uses a fixed annual power scale gamma = 0.30012075175285535. It is 9,561 MW divided by the maximum simultaneous 2025 NYISO zonal actual-load sum, 31,857.1773 MW. The numerator is a declared NPCC snapshot anchor, not proof of an observed peak. Public power and model power are retained separately.

```text
P_model = gamma * P_public
```

Divide aggregate model MW by gamma when comparing with public MW. Do not divide recovered AC amperes by gamma: those currents belong to the stated synthetic network and 100-MVA electrical base. Older DC physical-exposure proxies used a different, explicit public-power lift. Their conversion formula must not be copied into the current AC thermal workflow.

NYISO actual zonal load is a generation-plus-net-interchange boundary balance. Its 2025 definition is verified in the archived Market Participants User’s Guide. The latest loss revision partitions that balance into modeled delivered bus demand plus assigned losses. This must not be described as measured end-use demand. Static within-zone weights and the equal split between buses 81 and 82 in zone J are model assumptions.

| Input | Source and qualification |
| --- | --- |
| NY load and fuel mix | NYISO P58 actual load and statewide P63 fuel totals; within-zone spatial allocation is assumed. |
| Native generation | EPA gross-output evidence, EIA unit identities/capability, nuclear status and other bounded source priors. Not observed hourly net unit dispatch. |
| External demand | Historical external bus proportions shaped by NY load; not observed 2025 external-area demand. |
| Interchange and device controls | Frozen regional actual exchanges and separate external transfer channels, with raw sign/unit/time qualifications retained. |
| Reactive data | NY load power factor and generator/converter capability policies are assumptions, not a measured reactive history. |

The annual axis has 8,760 UTC-referenced positions spanning the local 2025 year and its daylight-saving transitions. The latest source mask qualifies 8,651 hours and excludes 109. Never replace excluded values by zero, forward-fill across those gaps, or use a failed solver iterate as a valid observation. Earlier stages used 8,663 hours; compare errors only on a named common cohort.

Evidence: [2025 inputs](NYGRID_2025_OPERATING_INPUTS.md) · [Fleet and dispatch](NYGRID_2025_BOUNDED_DISPATCH.md) · [Western source audit](NYGRID_2025_WESTERN_SOURCE_AUDIT.md) · [Final hour masks](output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_cohort.csv)

## Fleet and source corrections

The fleet register preserves 2,245 unique identities and separates identity, eligibility, electrical landing and hourly capability. The runnable case has 1,436 native rows plus 27 external regional equivalents and one HQ equivalent, totaling 1,464 generator rows. Capacity is counted once per admitted identity; many-to-many EPA reporting relationships do not create extra capacity.

| Modification | Reason and boundary |
| --- | --- |
| Indian Point retirement | Units 2 and 3 have no 2025 capability and cannot become the reference source. Retired identities remain in the inventory. |
| NYIS membership screen | Native eligibility follows reported balancing-authority scope and corroborating source evidence, not New York State location alone. |
| Bayonne and Linden mapping | Corroborated NYISO resources outside NY State are admitted once; Linden GTG6 and unresolved records are excluded. Native generation is distinct from VFT transfers. |
| Cricket Valley and South Fork | Use unique inventory records and existing statewide fuel totals; avoid adding project output twice. Capability and landing uncertainties remain explicit. |
| Hydro zone and generator landing repairs | Confirmed source corrections were applied in separate revisions and traced in source/repair ledgers. Internal interface scores did not select locations. |
| All-boundary actual interchange | Regional physical-exchange reconstruction replaced mixed scheduled/actual accounting, with a common 8,651-hour comparison cohort. |

Native hourly dispatch is capacity bounded and independently source conditioned. It is not a unit-commitment solution. Minimum stable operation, ramps, reserves, start costs, synchronized status and storage state of charge have not been established. The latest annual PF holds these native active-power schedules fixed while changing the loss-accounting contract.

The generator row index, electrical bus ID and reporting-unit identity are different axes. Use the saved corrected generator-to-bus mapping and explicit row IDs when aggregating. Reconstructing bus generation from an earlier raw mapping would undo the confirmed repairs.

Evidence: [Fleet and dispatch](NYGRID_2025_BOUNDED_DISPATCH.md) · [Moses diagnosis](NYGRID_2025_MOSES_SOUTH_DIAGNOSIS.md) · [Western source audit](NYGRID_2025_WESTERN_SOURCE_AUDIT.md) · [Profile AC audit](NYGRID_2025_ACPF_PROFILE_AUDIT.md)

## Physical detail and project parameters

Downstate construction retains all original NPCC buses and registers predecessor replacements. The detailed model includes 97 exact historical PERFORM circuit rows; they add source detail, not 97 new 2025 lines. Nine predecessor aggregate branch records are retained inactive. Other attachments and project impedances are explicitly assumed. The 30 edges in the smaller DC equivalent are mathematical couplings, not additional conductors.

| Change | Implemented treatment |
| --- | --- |
| Downstate station detail | Added 51 source or explicitly assumed terminals; retained eight critical ports in the 148-bus representation. |
| F84 Pleasant Valley to Cricket Valley | Design-backed twin Mallard ACSS family, representative geometry and 14.6-mile route; R/X/B are engineering estimates rather than measured impedance. |
| RCC receiving paths | Dated activation and cable/transformer/PAR representations. Staten route corrected to 9.4 miles; cable installation and conductor details remain unresolved. |
| Dover Y17 and 398 | Applied line estimates with distinct NY twin Mallard and CT single Bluebird sections; separate parallel PAR banks preserve equipment meaning. |
| Unbuilt or unresolved project detail | NYES overlap, western additions, exact physical gate membership and other incomplete correspondences remain qualified alternatives or omissions. |

For F84, the applied 100-MVA-base values are R = 0.0008742145129 pu, X approximately 0.0073369903 pu and total B approximately 0.1214494002 pu. Manufacturer temperature points, bundle geometry, representative phase spacing and capacitance simplifications are recorded. The 2,214-A phase rating is a design reference, not a verified terminal-limited facility rating; it is 1,107 A per subconductor for the twin bundle.

Use the full-precision CSV ledgers when modifying parameters. Preserve total corridor R/X/B when splitting numerical sections, and retain the parent-to-section map. Circuit count and bundle count are separate: parallel circuits change electrical sharing, while subconductors within a phase bundle also change conductor current and geometry.

Evidence: [Downstate construction](NYGRID_2025_DOWNSTATE_REFINEMENT.md) · [Line estimates](NYGRID_2025_LINE_PARAMETER_ESTIMATION.md) · [Dover parameters](NYGRID_2025_DOVER_PARAMETERS_APPLIED.md) · [Branch classification](output/nygrid_2025_ac_system/branches/branch_assignments.csv)

## Controlled transfers and interface definitions

The six prescribed transfer records and their signs are part of the electrical contract. Ontario’s two PAR-flow channels replace the original aggregate branch-211 transfer at runtime, which stays disabled. HQ and Cedars are accounted once. Merchant transfers already included in regional totals must not be added again as independent external supply.

The Ontario direction is supported by NYISO’s explicit 3 December 2024 effective-date note. Dover uses two separate parallel bank records and a post-cutover bounded phase reconstruction. Published ratings and angle ranges provide limited engineering information; they do not supply actual hourly tap positions, breaker states, factory R/X, full P/Q limits or emergency capability.

| Topic | Required interpretation |
| --- | --- |
| P34 raw field | The native header says Flow (MWH). Numeric-as-MW interpretation remains conditional; cadence alone does not justify multiplication by 12. |
| P34 timestamps | Forward-held hourly integration and gap limits are declared policies. Native instantaneous/start/end/average semantics are not fully certified. |
| Dover zero postings | Do not infer bypass position, zero total tie flow or duplicate sensors from equal/zero bank values. |
| Seven interface comparisons | Use frozen original-parent branch membership, signs and physical terminal convention after recovery. Do not sum compact matrix edges. |
| Physical flowgate audit | 269 printed entries in 21 seasonal definitions are archived. Complete physical model binding is not established for any of the seven gates. |

The numerical error series uses inherited diagnostic cuts named Dysinger East, West Central, Total East, Moses South, Central East–VC, UPNY ConEd and SPR/DUN South. A cut’s name does not certify membership of the current official NYISO physical flowgate. Source-side, target-side and inherited signed-literal-from conventions are separate diagnostic quantities, not a statistical confidence interval.

No internal seven-interface observations tune the current compact or loss-consistent AC solver. External reported controls still condition the electrical input. Treat the comparison as source-conditioned reconstruction, not an unconditional forecast.

Evidence: [Ontario controls](NYGRID_2025_VERIFIED_PAR_CONTROLS.md) · [Dover parameters](NYGRID_2025_DOVER_PARAMETERS_APPLIED.md) · [P34 qualifications](NYGRID_2025_P34_QUALIFICATION_AND_DLR_READINESS.md) · [Physical flowgates](NYGRID_2025_PHYSICAL_FLOWGATE_DEFINITIONS.md)

## Engineering AC construction and its limits

The AC engineering overlay supplies positive resistance/reactance, charging, fixed compensation, finite equipment assumptions and generator capability data on the detailed network. It is an explicit synthetic construction. Passing its arithmetic and matrix checks does not verify the installed asset interpretation.

| Reference class | Records | Interpretation |
| --- | --- | --- |
| Overhead corridors | 186 | Catalog/geometry realizations; 128 preserve inherited R/X and 58 use explicit engineering replacements. |
| Cable or urban equivalents | 40 | Synthetic cable parameters and static current limits; no overhead heat balance. |
| Transformer-compatible paths | 38 | Finite engineering assumptions, not verified nameplates. |
| Composite voltage-changing equivalents | 65 | Undecomposed regional/device mixtures; no verified internal conductor inventory. |
| PAR station and accounting links | 10 | Separate equipment models. |
| Inactive provenance | 74 | Preserved records, not active assets. |

These counts describe the earlier 413-record reference classification. The latest revision reclassifies parent 224 as an unresolved network equivalent and excludes it from conductor claims. Additional source conflicts at parents 300, 309, 310 and 386 prevent treating their inherited overhead labels as installed overhead evidence. The handoff screening filter excludes all five.

Numerical overhead sections are at most 100 km; selected long cable equivalents are also subdivided. The engineering design adds separate fixed reactors at selected original terminals under a declared 75% charging-compensation rule. Original shunts are preserved. Generator Q and S envelopes use assumed capability policies; voltage limits are 0.95–1.05 pu. The cost objective penalizes departure from priors, so its value is not market cost or monetary benefit.

Historical bounded validation found four of seven electrical snapshots and four of eight weather/current-constrained snapshots qualified. These finite results belong to the earlier engineering case. They are not evidence that the current annual profile replay or the revised loss formulation satisfies all operating limits.

Evidence: [Engineering AC and DLR](NYGRID_2025_AC_SYSTEM.md) · [Branch classification](output/nygrid_2025_ac_system/branches/branch_assignments.csv) · [Current physical exceptions](output/nygrid_2025_acpf_profile_audit/structure/structure_audit.json)

## Exact compact AC and current recovery

The compact solver eliminates only passive, zero-prescribed-injection interior buses. All loads, generators, DC terminals and independently controlled voltages remain retained. Fixed shunts are included in the complex admittance matrix. Resistance, charging, off-nominal taps and phase shifts enter before reduction.

```text
Ve = -(Yee \ Yek) Vk
```

```text
Yred = Ykk - Yke * (Yee \ Yek)
```

```text
Vfull = L Vk; If = Yf L Vk; It = Yt L Vk
```

The retained nonlinear AC equations use this complex matrix directly. A compact matrix coupling is not a physical branch. The saved detailed branch operators recover original from-terminal, to-terminal and series currents after solving. Their row identities, end voltages and base-current conventions remain part of the output contract.

The original compact annual replay matched all 8,494 qualified detailed solutions: maximum complex-voltage discrepancy 6.70 × 10⁻¹² pu and maximum original-branch current discrepancy 1.48 × 10⁻⁸ A. It reproduced the detailed model’s interface errors rather than improving them. In the loss revision, all 8,170 qualified annual outputs passed independent reconstructed branch/KCL/current checks; 11 qualified representative cases additionally matched detailed coupled and conventional final-allocation PF solutions.

### When to rebuild

Rebuild after changing R(T), X, B, a tap, phase shift, shunt, branch status, a source profile, mapping or retained-node contract. Fingerprints intentionally reject stale operators. If adding an injection or independent voltage controller at an eliminated bus, retain it or derive a justified projection; do not discard that device to preserve the count of 148. The loss-consistent wrapper currently asserts its registered 148-bus contract.

Evidence: [Compact AC](NYGRID_2025_COMPACT_AC.md) · [Retained bus ledger](output/nygrid_2025_compact_ac/independent/bus_retention_ledger.json) · [Final independent physics](output/nygrid_2025_ac_loss_revision/impedance/released_equivalent_boundary_consistent_annual_arrays_independent_review.json)

## Boundary consistent AC loss accounting

The earlier annual AC replay kept lossless schedules and loss-inclusive load fixed, leaving Clay to absorb the AC imbalance. The current revision instead solves voltage and the loss allocation simultaneously while holding native active generation, HQ and six controlled transfers at their original schedules.

```text
Pdelivered,z + LNY,z = PP58,z
```

Within-NY corridor losses are split equally between their endpoint zones, or wholly assigned to the common zone. Each external region supplies losses of its internal AC corridors and the AC corridors crossing into New York. Its delivered-load proxy remains fixed, and its generators share the loss increment through frozen bounded participation. This preserves net import at the NY terminals under the current external-area connectivity contract.

```text
Ploss_MW = baseMVA * Rpu * abs(Iseries_pu)^2
```

Native real power stays fixed; Q demand scales with modeled delivered P at the inherited power factor. External P limits come from the original finite parent capability boxes, and their assumed Q-circle slices update with P. These are synthetic proxy capabilities. The default PF does not enforce all Q limits or optimize dispatch. A valid electrical/accounting result can therefore fail the physical operating gate.

The solver uses analytic derivatives of the loss-dependent injections and line search within the positive delivered-load and finite-capability domain. It requires the current zero bus-conductance and zero DC-loss assumptions, and no AC connections between different external regions. Unsupported cases must receive a new explicit allocation contract. Loss clipping, negative served demand and an unlimited reference fallback are not allowed.

### Gilboa Buchanan equivalent

Parent 224 restores the released total R/X/B = 0.02/0.0147/0 pu in its two existing numerical sections. It is an added E–G network equivalent, not an identified installed direct line. The paper gives X approximately 0.0146498635 pu; the released 0.0147 differs by 0.342%, not exact four-decimal rounding. No physical R/B derivation was established. Its rating, conductor and R(T) claims are removed, and every other branch parameter and shunt is preserved.

Evidence: [Central East diagnosis](NYGRID_2025_CENTRAL_EAST_DIAGNOSIS.md) · [Loss revision](NYGRID_2025_AC_LOSS_REVISION.md)

## Annual results and interpretation

The completed loss-consistent year attempts the original 8,651 eligible hours. It qualifies 8,170 and rejects 481, with zero runtime exceptions. All qualified revised hours belong to the old 8,494-success cohort: 324 old successes are lost and none is gained. Failures comprise 465 line-search failures and 16 near-boundary delivered-load failures. Nonconvergence is not proof of global infeasibility.

| Interface | Previous WAPE percent | Revised WAPE percent |
| --- | --- | --- |
| DYSINGER EAST | 37.61 | 29.96 |
| WEST CENTRAL | 58.52 | 45.86 |
| TOTAL EAST | 14.46 | 14.70 |
| MOSES SOUTH | 23.18 | 22.94 |
| CENTRAL EAST - VC | 43.50 | 13.70 |
| UPNY CONED | 7.55 | 7.56 |
| SPR/DUN-SOUTH | 8.88 | 9.18 |

Both columns use exactly the same 8,170 hours and inherited signed-literal-from terminals. WAPE is 100 times total absolute error divided by total absolute observed flow. The previous Central East value of 45.04% uses 8,494 hours; its matched-cohort value is 43.50%, which is the correct comparison for the revised 13.70%. Monthly, post-Dover, other terminal conventions and all lost/new masks are saved.

None of the 8,170 qualified hours passes the joint V/Q/generator-capability gate. Voltage spans 0.841226–1.120005 pu. Model AC loss averages 339.503 MW and reaches 1,024.652 MW. Assigned loss fractions reach 95.45% in zone F and 94.52% in zone E; 3,131 qualified hours have at least one zone above 25%. Those extreme values reflect unresolved network/operating assumptions, not measured NYISO losses. Parent 224 alone dissipates 0.786–172.527 model MW, averaging 39.136 MW.

Independent source accounting closes served-plus-loss load within 2.43 × 10⁻¹⁰ model MW and regional net imports within 9.07 × 10⁻¹⁰ MW. Native P changes stay below 1.86 × 10⁻¹⁰ MW. These numerical closures validate the specified equations, not the physical truth of their inputs. A 14-hour four-cell diagnostic separates impedance and allocation changes on 11 common successes; it is not an annual causal or WAPE decomposition.

Evidence: [Final annual loss receipt](output/nygrid_2025_ac_loss_revision/validation/annual/released_equivalent_boundary_consistent/annual_loss_policy_receipt.json) · [Final annual comparisons](output/nygrid_2025_ac_loss_revision/comparison/combined/public_interface_metrics.csv) · [Final independent physics](output/nygrid_2025_ac_loss_revision/impedance/released_equivalent_boundary_consistent_annual_arrays_independent_review.json)

## Conductor physics and current conventions

Thermal screening uses original same-voltage overhead conductor sections with an explicit conductor catalog, route/equivalent length, number of parallel circuits and number of subconductors per phase. The screening whitelist is a synthetic-study eligibility rule; it does not certify installed equipment. Cables, transformers, PARs, mixed voltage-changing equivalents and reduced matrix couplings need different physical models.

```text
Req(T) = rsub(T) * L / (nc * nb)
```

```text
Isub = Iseries / (nc * nb)
```

```text
C dT/dt = Isub^2 r(T) + qs - qc - qr
```

The heat balance is per unit length. Use the catalog’s temperature-dependent AC resistance, not a second power-scale conversion. The thermal kernel calculates convection, radiation and absorbed solar heat under declared surface and atmospheric assumptions. Steady ampacity is evaluated at a stated conductor temperature cap; a negative net cooling margin means no valid steady ampacity under those conditions.

Series current excludes lumped pi charging and is used for the modeled Joule-loss identity. From/to terminal currents include charging and use their endpoint voltage bases. Section-end current envelopes and original-terminal hardware limits are separate checks. Material segments within one modeled series element share its phase current but can have different subconductor currents and ampacity. Successive pi sections use their own recovered currents because charging can change series current along the corridor; the limiting thermal segment governs.

The existing whole-system DLR snapshots use reference R at 75°C for ACSR or 95°C for ACSS and steady ampacity at a declared cap. They do not solve a time-dependent thermal trajectory or electrothermal fixed point. Complete IEEE 738 compliance, actual span sag/clearance, route weather, surface condition, mutual effects and installed terminal limits remain outside the qualified claims.

Evidence: [Engineering AC and DLR](NYGRID_2025_AC_SYSTEM.md) · [Thermal segments](output/nygrid_2025_ac_system/branches/thermal_segments.csv) · [Conductor catalog](output/nygrid_2025_ac_system/engineering/thermal_conductors.csv) · [Current physical exceptions](output/nygrid_2025_acpf_profile_audit/structure/structure_audit.json)

## Run a transparent DLR screening experiment

The handoff helper screens the current loss-consistent PF against steady ampacity under explicit weather. It does not change dispatch, resistance, voltage controls, or the loss-accounting equations. Its result must carry the input PF and physical-operating flags. An overload ratio is model exposure under those assumptions, not a measured violation or a mitigation benefit.

```text
weather = table(25,0.6096,90,1000,101325, ...
  'VariableNames',{'ambient_c','wind_m_s','wind_angle_deg', ...
                   'solar_w_m2','pressure_pa'});
screen = screen_nygrid_2025_loss_pf_thermal(8508,weather);
```

This uniform weather is a synthetic counterfactual: 25°C air, 0.6096 m/s wind at 90 degrees to the conductor, 1,000 W/m² irradiance and 101,325 Pa pressure. For spatially varying weather, bind each value to the exact conductor-segment key using the helper’s documented contract. Never infer that the same weather occurred at all modeled routes.

The eligibility ledger excludes parent 224, source-conflicted parents 300/309/310/386, non-overhead classes, voltage-changing paths and unsupported equipment. All exclusions remain visible. The helper checks electrical-loss versus conductor-Joule consistency and reports the current/ampacity ratios at the study’s actual AC scale. It cannot certify the unresolved interiors of regional equivalents.

### The older bounded optimizer

```text
% Explicitly historical engineering-case workflow
[result, audit] = run_nygrid_2025_ac_dlr(8508,weather, ...
                                      struct('solver','MIPS'));
```

This original API constructs npcc_nygrid_2025_ac and applies constrained ACOPF. It does not apply the latest loss revision or its filtered conductor interpretation. Archived qualification is four of eight attempted weather snapshots, with the recorded solver/environment. A different solver or machine requires inspecting the new result. Its objective is a deviation penalty, not money; current old-case results are retained for method comparison, not promoted as validated latest-model DLR benefits.

Evidence: [Engineering AC and DLR](NYGRID_2025_AC_SYSTEM.md) · [Loss revision](NYGRID_2025_AC_LOSS_REVISION.md)

## Design the next DLR research study

Define the research question before choosing a solver. Fixed-dispatch screening compares rating exposure at one supplied electrical state. A redispatch study must explicitly optimize allowed generation or controls and verify resulting AC feasibility. A transient study must carry conductor temperature and weather through time. A historical asset study additionally needs identified conductors, facility ceilings and route/critical-span weather.

| Decision | Record before the experiment |
| --- | --- |
| Electrical baseline | Model snapshot, source-hour mask, dated topology, transfer policy, P/Q controls and which operating gates are required. |
| Candidate assets | Original parent/section keys, conductor evidence, excluded classes and applicable terminal equipment ceilings. |
| Weather and thermal state | Observation or scenario, timestamp support, route/segment mapping, wind angle, thermal initialization and gap policy. |
| Perturbation | Which quantities may change; R(T), dispatch, bounds and controllers must be explicit. Preserve a control case. |
| Comparison | Common hours and assets, failed-hour counts, denominators and whether the result is exposure, feasibility, curtailment or economics. |
| Validation | Branch KCL, current/Joule identities, thermal residual or time-step checks, physical bounds and independent baseline reproduction. |

Keep load and weather on a declared common calendar basis and expose both source years. Timezone and daylight-saving handling must be explicit. Do not bridge the 109 source-excluded hours or solver failures with invented thermal state. Define whether the next valid interval is reinitialized, bounded conservatively, or omitted, and report its impact.

If temperature changes R, rebuild the detailed case and its compact operators before the next electrical solve. Reconcile the coupled loss policy with those changed parameters. A joint loss-consistent bounded ACOPF/electrothermal controller is not delivered by this handoff; the one-way screening adapter must not be mistaken for it.

Priority physical gaps are the unresolved aggregate resistances, large E/F assigned losses, reactive capability/voltage controls, exact corridor equipment and complete physical flowgate mappings. Improve them using independent engineering/source evidence. Do not select impedance, losses, signs or interface membership merely because a public error metric decreases.

Evidence: [P34 qualifications](NYGRID_2025_P34_QUALIFICATION_AND_DLR_READINESS.md) · [Physical flowgates](NYGRID_2025_PHYSICAL_FLOWGATE_DEFINITIONS.md) · [Loss revision](NYGRID_2025_AC_LOSS_REVISION.md)

## Reproduce and inspect the evidence

The runtime package supports the included entry points and smoke examples. The complete research package adds historical construction, source receipts, saved annual profiles, controlled experiments, maps, ledgers and validation. Both annual and re-scoring commands on this page require the complete research edition. Read the inventory for exact contents; MATLAB itself and unrelated dependency caches are not distributed. Keep third-party notices with redistributed code and follow each source’s terms.

### Annual replay

```text
addpath(fullfile(pwd,'scripts','nygrid_2025_ac_loss_revision', ...
                 'validation'));
receipt = run_annual_loss_policy('released_equivalent', ...
    'boundary_consistent','my_new_replay');
```

Use a new run label. The annual driver refuses to overwrite an existing attempt. It preserves all clock rows and failures, checks source/code hashes before and after the run, and writes monthly MAT arrays plus quality tables and iteration traces. The delivered 719-second timing is a historical observation on the recorded host, not a runtime guarantee.

### Post hoc comparison

```text
python scripts/nygrid_2025_dlr_handoff/portable_scoring.py
    --output-dir runs/comparison_2025
```

Enter the displayed Python command on one line from the complete research package root. This re-scores the delivered year into a new directory. The wrapper verifies the unchanged original scorer and substitutes two historical Git byte lookups with pinned package hashes. The original comparison CLI alone is not portable without Git history. The smaller runtime package omits the large annual reference arrays required for this check. A newly generated annual replay needs its own declared input/output contract rather than silently replacing the pinned reproduction inputs.

The portable scorer requires Python with NumPy, SciPy and pandas; its contract records the tested environment. Rebuilding raw public inputs may also require network services and optional tools. Frozen input/model use is offline. Old Git-dependent finalizers remain historical methods; they are not advertised as standalone commands after extraction.

Read receipts by purpose: construction and provenance; source coverage and clock; solver outcome; physical operating checks; compact/full equivalence; thermal checks; public comparisons. A receipt marked passed certifies its stated scope. A model may pass equation/recovery tests while failing the physical operating gate. Preliminary failures, superseded methods and download failures are retained as historical evidence and must not be counted as current successes.

Evidence: [Final annual loss receipt](output/nygrid_2025_ac_loss_revision/validation/annual/released_equivalent_boundary_consistent/annual_loss_policy_receipt.json) · [Final annual comparisons](output/nygrid_2025_ac_loss_revision/comparison/combined/public_interface_metrics.csv) · [Final hour masks](output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_cohort.csv) · [Final independent physics](output/nygrid_2025_ac_loss_revision/impedance/released_equivalent_boundary_consistent_annual_arrays_independent_review.json)

## Earlier structural and regional milestones

The complete archive retains the earlier local NPCC and PERFORM pathway. It is a separate lineage from the Cornell NYgrid source. Its milestones explain prior methods and decisions without supplying physical certification for the latest model. The machine-readable modification inventory includes exact source references and qualification records.

| Milestone | Saved structure | Meaning of the result |
| --- | --- | --- |
| S7 structural parent | 143 buses, 246 branches, 62 generators | Preserved local full-NPCC structural provenance. |
| S13 Phase 1A | 147 buses, 253 branches, 62 generators | Four added source terminals and seven direct branches. |
| S13 Phase 1B | 149 buses, 262 branches, 62 generators | East Fishkill and Ladentown with nine further source circuits. |
| S13 Phase 1C | 170 buses, 315 branches, 62 generators | Twenty-one additional terminals and 53 source elements, including transformers. |
| External reduction diagnostic | 86 buses, 182 branches | Same-state mathematical identity; six bounded operating reconstructions failed. |
| S11 and S12 | 49-bus diagnostic; 317-bus oracle | S12 has 3,531 branches and 615 generator records, including dense equivalents. |
| S14 planning role | Promoted NYISO operating model pending | An S14-labelled reduction diagnostic is not promotion of this planned DLR model. |

Do not use S12 dense equivalents as physical construction inputs. The Phase 1C implementation passed 130 implementation checks, but that numerical evidence did not qualify its bounded operating states. The original structural parent, construction overlays, diagnostic reductions and operating candidates remain separate objects.

### Regional reference packages

Package A establishes one assumed historical 2019 PERFORM reference with declared boundary and reactive-support assumptions. Its immutable source has 1,576 buses, 2,371 branches and 615 generator records. Package B is a distinct bounded historical candidate with 878 buses, 1,375 branch records and 595 generators: 855 source buses in zones D–K and 23 retained NPCC buses in A–C. Its accepted route uses MIPS with default initialization and fresh PF verification. Neither package establishes contemporary NYISO coverage or physical DLR readiness.

Evidence: [Earlier project hierarchy](PROJECT_HANDOFF.md) · [Phase 1C implementation](ELECTRICAL_MODEL_IMPLEMENTATION.md) · [Package A foundation](output/ny_only_package_a/NY_ONLY_FOUNDATION_RESULTS.md) · [Package B candidate](NY_ONLY_PACKAGE_B_IMPLEMENTATION.md)

## Earlier compact studies and paper reproduction

The smaller NY-only studies explored a different boundary and calibration design. Their scale factors, fixed boundary channels, generation policies and thermal qualifications are retained with each result. They must not be combined numerically with the present 148-bus network without an explicit transformation.

| Study | Structure | Preserved qualification |
| --- | --- | --- |
| Initial NY-only testbed | 51 buses, 92 records, 87 active, 35 generators | Retains 46 original NY buses with a few explicit corridor terminals. |
| Calibrated 2025 study | 66 buses, 125 records, 112 active, 37 generators | Four interface-calibration snapshots and separate unused-hour prediction errors; 23 assumed overhead realizations. |
| Source generation alternative | 66 buses | 14 source-qualified electrical snapshots pass; two are excluded for boundary gaps. Generation remains estimated. |
| Partial Smart Path Connect | 71 buses, 135 records, 117 active, 37 generators | 15 electrical/sensitivity and four thermal cases pass; two electrical hours use strict IPOPT fallback. Twenty-five assumed overhead realizations. |
| Later compact 2019 comparator | 51 buses, 94 records, 89 active | Separate 2019 comparison variant; distinct from the earlier 92-record testbed. |

The 66-bus calibration fitted selected interface proxies. Its small training errors do not establish unseen-hour accuracy. Independent generation and partial-SPC studies retain much larger interface prediction errors and a fixed year-end topology applied to earlier conditions. Those counterfactual electrical/thermal results remain useful methodological evidence, not historical asset validation. Optional IPOPT binaries are not supplied with this handoff.

### Reproducing the paper and repairing the measurement

The Cornell NYgrid release provides the later 2019 source pathway: 140 original buses, 227 downloaded branch records and a released 57-bus final DC model with 94 branches, 271 generators and four controllable-link records. The paper’s 233-branch description differs from the pinned download. The reconstruction records that discrepancy rather than inventing missing branches.

Five of seven plotting expressions referenced wrong branch indices. The measurement repair corrects interface extraction while preserving the solved network. The subsequent full 140-bus reconstruction, annual load verification, western diagnostics and compact comparison are included with their own receipts. The authors’ 2019 prepared local-hour labels are not interchangeable with the later 2025 physical UTC/DST clock.

Evidence: [51 bus testbed](COMPACT_NPCC_NY_TESTBED.md) · [66 bus calibration](COMPACT_NY_2025_DLR_METHODOLOGY.md) · [Independent generation study](COMPACT_NY_GENERATION_RECONSTRUCTION.md) · [71 bus partial SPC](COMPACT_NY_PARTIAL_SPC_BASELINE.md) · [2019 measurement repair](NYGRID_2019_INTERFACE_VERIFICATION.md) · [2019 comparator](NYGRID_COMPACT_2019_COMPARISON.md)

## File map and extension contract

| Location | What the colleague should use it for |
| --- | --- |
| System Matpower Format | Public dated DC, detailed AC, compact AC and loss-consistent PF constructors/wrappers. |
| scripts/nygrid_2025_dlr_handoff/runtime | Portable setup, smoke test and filtered one-way thermal screening. |
| scripts/nygrid_2025_ac_loss_revision | Current loss equations, allocation policy, guards, annual replay and scorer. |
| scripts/nygrid_2025_compact_ac/core | Complex reduction, voltage/current recovery, nonlinear kernel and stale-operator fingerprints. |
| scripts/nygrid_2025_ac_system | Engineering branch construction, sections, generator assumptions, thermal kernels and legacy current constraints. |
| output/nygrid_2025_ac_loss_revision | Final current annual results, source-equivalent review, policy evidence, masks and comparisons. |
| output/nygrid_2025_ac_system | Engineering overlays, catalogs, branch metadata and archived bounded DLR results. |
| output/nygrid_2025_dlr_handoff | Package inventory, portable execution proof, eligibility/exclusion ledger and final handoff validation. |
| Earlier nygrid output namespaces | Frozen source-data, topology, dispatch, controls and comparison stages, identified by their own receipts. |

Preserve frozen files when extending the study. Put revised inputs, policies, derived operators and results in a new namespace or scenario label. Carry the original parent/section keys and generation identities into every export. If a profile, parameter, device status or bus role changes, rebuild the dependent operators and update the experiment contract before comparing scores.

For an implementation handoff, retain the package hash, source model commit, MATLAB/MATPOWER version, exact invocation, weather source and units, eligibility mask, failed attempts, and the independent checks supporting the claim. These records are necessary to distinguish a reproducible synthetic DLR result from an unverified operating-system assertion.

### Research questions still open

The package supports transparent investigation of rating sensitivity and numerical model behavior. It does not establish historical thermal trajectories, actual NYISO line currents, asset-certified emergency limits, N−1 security, ramp/reserve adequacy, storage energy feasibility, or economic benefits. Those claims require their corresponding inputs and validation. The present limitations are preserved so that subsequent improvements can be attributed and audited.

Evidence: [Engineering AC and DLR](NYGRID_2025_AC_SYSTEM.md) · [Compact AC](NYGRID_2025_COMPACT_AC.md) · [Loss revision](NYGRID_2025_AC_LOSS_REVISION.md)

## Source and evidence index

All paths below are relative to the extracted package root. The original reports contain the detailed primary-source citations and receipt chains. This index identifies the relevant research stage; the machine-readable package inventory enumerates individual files and hashes.

| Evidence | Relative path |
| --- | --- |
| 2019 parent | [NYGRID_2019_DLR_REBUILD.md](NYGRID_2019_DLR_REBUILD.md) |
| 2025 inputs | [NYGRID_2025_OPERATING_INPUTS.md](NYGRID_2025_OPERATING_INPUTS.md) |
| Fleet and dispatch | [NYGRID_2025_BOUNDED_DISPATCH.md](NYGRID_2025_BOUNDED_DISPATCH.md) |
| Downstate construction | [NYGRID_2025_DOWNSTATE_REFINEMENT.md](NYGRID_2025_DOWNSTATE_REFINEMENT.md) |
| Small bus DC model | [NYGRID_2025_SLIM_DOWNSTATE.md](NYGRID_2025_SLIM_DOWNSTATE.md) |
| Moses diagnosis | [NYGRID_2025_MOSES_SOUTH_DIAGNOSIS.md](NYGRID_2025_MOSES_SOUTH_DIAGNOSIS.md) |
| Ontario controls | [NYGRID_2025_VERIFIED_PAR_CONTROLS.md](NYGRID_2025_VERIFIED_PAR_CONTROLS.md) |
| Western source audit | [NYGRID_2025_WESTERN_SOURCE_AUDIT.md](NYGRID_2025_WESTERN_SOURCE_AUDIT.md) |
| Physical flowgates | [NYGRID_2025_PHYSICAL_FLOWGATE_DEFINITIONS.md](NYGRID_2025_PHYSICAL_FLOWGATE_DEFINITIONS.md) |
| Line estimates | [NYGRID_2025_LINE_PARAMETER_ESTIMATION.md](NYGRID_2025_LINE_PARAMETER_ESTIMATION.md) |
| Dover parameters | [NYGRID_2025_DOVER_PARAMETERS_APPLIED.md](NYGRID_2025_DOVER_PARAMETERS_APPLIED.md) |
| P34 qualifications | [NYGRID_2025_P34_QUALIFICATION_AND_DLR_READINESS.md](NYGRID_2025_P34_QUALIFICATION_AND_DLR_READINESS.md) |
| Engineering AC and DLR | [NYGRID_2025_AC_SYSTEM.md](NYGRID_2025_AC_SYSTEM.md) |
| Profile AC audit | [NYGRID_2025_ACPF_PROFILE_AUDIT.md](NYGRID_2025_ACPF_PROFILE_AUDIT.md) |
| Compact AC | [NYGRID_2025_COMPACT_AC.md](NYGRID_2025_COMPACT_AC.md) |
| Central East diagnosis | [NYGRID_2025_CENTRAL_EAST_DIAGNOSIS.md](NYGRID_2025_CENTRAL_EAST_DIAGNOSIS.md) |
| Loss revision | [NYGRID_2025_AC_LOSS_REVISION.md](NYGRID_2025_AC_LOSS_REVISION.md) |
| Branch classification | [output/nygrid_2025_ac_system/branches/branch_assignments.csv](output/nygrid_2025_ac_system/branches/branch_assignments.csv) |
| Thermal segments | [output/nygrid_2025_ac_system/branches/thermal_segments.csv](output/nygrid_2025_ac_system/branches/thermal_segments.csv) |
| Conductor catalog | [output/nygrid_2025_ac_system/engineering/thermal_conductors.csv](output/nygrid_2025_ac_system/engineering/thermal_conductors.csv) |
| Current physical exceptions | [output/nygrid_2025_acpf_profile_audit/structure/structure_audit.json](output/nygrid_2025_acpf_profile_audit/structure/structure_audit.json) |
| Retained bus ledger | [output/nygrid_2025_compact_ac/independent/bus_retention_ledger.json](output/nygrid_2025_compact_ac/independent/bus_retention_ledger.json) |
| Final annual loss receipt | [output/nygrid_2025_ac_loss_revision/validation/annual/released_equivalent_boundary_consistent/annual_loss_policy_receipt.json](output/nygrid_2025_ac_loss_revision/validation/annual/released_equivalent_boundary_consistent/annual_loss_policy_receipt.json) |
| Final annual comparisons | [output/nygrid_2025_ac_loss_revision/comparison/combined/public_interface_metrics.csv](output/nygrid_2025_ac_loss_revision/comparison/combined/public_interface_metrics.csv) |
| Final hour masks | [output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_cohort.csv](output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_cohort.csv) |
| Final independent physics | [output/nygrid_2025_ac_loss_revision/impedance/released_equivalent_boundary_consistent_annual_arrays_independent_review.json](output/nygrid_2025_ac_loss_revision/impedance/released_equivalent_boundary_consistent_annual_arrays_independent_review.json) |
| Earlier project hierarchy | [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) |
| Phase 1C implementation | [ELECTRICAL_MODEL_IMPLEMENTATION.md](ELECTRICAL_MODEL_IMPLEMENTATION.md) |
| Package A foundation | [output/ny_only_package_a/NY_ONLY_FOUNDATION_RESULTS.md](output/ny_only_package_a/NY_ONLY_FOUNDATION_RESULTS.md) |
| Package B candidate | [NY_ONLY_PACKAGE_B_IMPLEMENTATION.md](NY_ONLY_PACKAGE_B_IMPLEMENTATION.md) |
| 51 bus testbed | [COMPACT_NPCC_NY_TESTBED.md](COMPACT_NPCC_NY_TESTBED.md) |
| 66 bus calibration | [COMPACT_NY_2025_DLR_METHODOLOGY.md](COMPACT_NY_2025_DLR_METHODOLOGY.md) |
| Independent generation study | [COMPACT_NY_GENERATION_RECONSTRUCTION.md](COMPACT_NY_GENERATION_RECONSTRUCTION.md) |
| 71 bus partial SPC | [COMPACT_NY_PARTIAL_SPC_BASELINE.md](COMPACT_NY_PARTIAL_SPC_BASELINE.md) |
| 2019 measurement repair | [NYGRID_2019_INTERFACE_VERIFICATION.md](NYGRID_2019_INTERFACE_VERIFICATION.md) |
| 2019 comparator | [NYGRID_COMPACT_2019_COMPARISON.md](NYGRID_COMPACT_2019_COMPARISON.md) |

