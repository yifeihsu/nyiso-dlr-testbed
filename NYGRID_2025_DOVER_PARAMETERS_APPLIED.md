# Dover parameters applied with explicit parallel PARs

The new Dover line-section estimates are now applied in a separate, validated 2025 DC reconstruction. The model has two explicit parallel PAR banks and a regulated station port, with conditional engineering reactances and bounded operating controls. The previously unapplied line estimates now operate alongside separately represented PAR banks.

The new loader is [npcc_nygrid_2025_dover_dc.m](System%20Matpower%20Format/npcc_nygrid_2025_dover_dc.m). Its default is the **bounded nominal-impedance reconstruction**. Previous models, source inputs and comparison artifacts remain unchanged. This stage applies engineering estimates; it does not claim factory-tested impedances, measured taps or full AC/thermal certification.

## Applied network

The [2025 owner petition and agreement](output/nygrid_2025_dover_parameters/sources/Dover_DPS_Transfer_Petition_SA2734_2025.pdf) explicitly establishes two **parallel** 750-MVA PAR banks, circuit breakers, bypass capability and a spare. NYISO's diagram identifies T398-A/PTID625149 and T398-B/PTID625150, with positive reported flow from Long Mountain toward Cricket Valley. The bypass is drawn normally open; actual hourly breaker positions were not obtained.

```mermaid
flowchart LR
  CV[Cricket Valley] -->|Y17: new line estimate| W[Dover west port]
  W -->|T398-A PAR| E[Dover regulated port]
  W -->|T398-B PAR| E
  W -. bypass normally open .-> E
  E -->|398: NY and CT line sections| LM[Long Mountain]
```

The post-cutover detailed reference has **192 buses and 413 branch records**. One added, zero-injection regulated port separates the line from the two banks. Exact DC reduction retains the same **148 buses and 274 branch records**, including every original NPCC bus. It carries two independent phase-input columns through the reduction, preserving parallel-bank circulation as well as the net transfer.

| Detailed record | Treatment | R pu | X pu | Total B pu |
|---|---|---:|---:|---:|
| 393: Cricket Valley-Dover Y17 | Applied 0.30-mile NY line estimate | 0.00001796 | 0.00014969 | 0.00251381 |
| 394: old Dover-Long Mountain proxy | Preserved as inactive provenance | 0.00046000 | 0.00726000 | 0 |
| 411: T398-A | Explicit PAR, nominal conditional case | 0 model placeholder | 0.01873878 | 0 model placeholder |
| 412: T398-B | Explicit parallel PAR, nominal conditional case | 0 model placeholder | 0.01873878 | 0 model placeholder |
| 413: regulated Dover port-Long Mountain | Applied heterogeneous line estimate | 0.00044388 | 0.00497240 | 0.06121743 |

Values use a **100 MVA, 345 kV base**. The full-precision [applied branch register](output/nygrid_2025_dover_parameters/network/Dover_applied_branch_register.csv) is authoritative. The line estimates retain the previous stage's declared 95 C resistance and representative H-frame geometry assumptions. The 398 estimate combines 3.13 miles of NY twin Mallard ACSS and 5.3 miles of CT single Bluebird ACSS; its exact transition stationing and route-average geometry remain qualified.

All 97 historical PERFORM circuits, other project parameters, generator identities and operating-input templates are preserved. Original record211 remains subject to the existing Ontario controlled-transfer substitution at runtime. No new physical HVDC device is introduced and the six existing transfer schedules remain fixed.

## Conditional PAR impedance estimate

The public [SA2510 equipment specification](output/nygrid_2025_line_parameters/sources/projects/NYTransco_SA2510_2023.pdf), PDF page44, states 450/600/750 MVA per bank, a +/-40-degree range, and maximum advance32 degrees at750 MVA. It does **not** explicitly call40 degrees a no-load angle. The detailed station diagram and relevant facilities-study information are redacted in public releases; factory R/X, loss tests and tap-dependent correction tables were not established.

The selected engineering reference point assumes40 degrees is the no-load reference, an8-degree load-angle drop at unity power factor, receiving voltage1 pu and rated load1 pu. With unknown resistance omitted from the DC model:

`X_750 = tan(8 degrees) = 0.1405408347 pu`

`X_100 = X_750 * 100/750 = 0.01873877796 pu per bank`

Two equal parallel banks have `X_pair = 0.00936938898 pu`. The corresponding AC phasor reference requires internal/source magnitude `sec(8 degrees) = 1.00982757 pu`; this calculation does not assume both terminal magnitudes are exactly1 pu. R=0 is a lossless DC placeholder, not a claim of zero physical winding loss. The estimated X is a conditional reference-point value, not a certified neutral-tap reactance.

The [engineering basis](output/nygrid_2025_dover_parameters/engineering/conditional_impedance_basis.json) records these assumptions. The [parameter families](output/nygrid_2025_dover_parameters/engineering/PAR_estimates.csv) include multipliers2/3,1 and1.5 to test generic leakage/tap uncertainty. They are stress cases, not Dover confidence bounds. No impedance was inferred from P34 or internal interface errors.

The750-MVA bank fields preserve maximum cooling/nameplate information. The runtime necessary numeric active-power screen is `abs(P_model_bank) <= 750 * gamma`, applied per bank. Actual reactive flow, cooling state, tap steps and terminal limitations remain unknown; neither this screen nor the nominal MATPOWER rating certifies facility thermal capability.

## Timing and operating-state treatment

The application starts at the preserved **December19,2025 hour beginning23 EST** full-service boundary, or **2025-12-20T04:00:00Z**. Before that timestamp, the loader returns the previous engineering case unchanged. This is not described as first station energization: the November21 owner petition says the project was completed and partially energized, and P34 has two opposed-sign test-like postings per bank earlier on December19.

The cached P34 archive contains distinct channels for both banks. Independent reparsing checked187,324 records including the endpoint day. Channel presence starts in February, but earlier zero values do not prove the banks carried zero total intertie transfer. The agreement specifies different revenue-meter locations for normal bank operation versus bypass/out-of-service operation.

The source compiler preserves:

- Actual UTC timestamps and local-clock/DST interpretation, without choosing a time shift by interface scores.
- The two source PTIDs, raw values and individual bank signs; positive reported import becomes negative NY-to-CT branch flow, scaled once by the existing `gamma = 0.30012075175285535`.
- Complete-hour coverage and native gap/duplicate checks, without filling absent channels with zeros.
- The literal `Flow (MWH)` header. The numeric-as-MW convention is inherited and explicitly conditional. The current NYISO guide describes hourly RTD quantities, but the actual native files have roughly five-minute postings; the guide alone does not settle their exact raw semantics. No multiplication or division by12 was introduced.
- The current diagram's direction with its publication-vintage qualification. The December3,2024 effective-date note applies to Moses, not Dover; an explicit historical Dover sign-change record was not found.

There are289 calendar hours after the full-service boundary and287 qualified source hours. Those are exactly the287 hours already present in the previous8,651-hour comparison cohort, so no additional comparison hours are removed.

### Preferred bounded controller

For hours with nonzero native bank postings, the model chooses its two phase states to minimize external bank-target tracking error subject to `abs(SHIFT_model) <= gamma * 40 degrees`. The impedance values and operating injections stay fixed. This is an operating-state reconstruction using external controls, not a fit of line parameters or internal interface expressions.

The gamma-scaled angle bound is a declared uniform-power-scaling convention. `SHIFT_model/gamma` is an unscaled coarse-network proxy, not an observed physical tap. It is not appropriate to compare the raw model angle directly with hardware nameplate angles or claim a measured tap trajectory.

For18 hours, both banks' native postings are entirely zero. Their switching mode is ambiguous. The preferred case retains the normal parallel-bank topology with an explicitly flagged **neutral-phase assumption**. It does not infer that the bypass was closed, and it does not force total intertie flow to zero.

| Preferred nominal case, 287 applied hours | Hours |
|---|---:|
| Nonzero-posting target tracking without hitting the declared angle bound | 220 |
| Nonzero-posting tracking at the angle bound | 49 |
| Ambiguous-zero mode with explicit neutral assumption | 18 |

Raw targets are unchanged. In bounded hours, simulated flow can differ from the desired reported value; the largest residual among nonzero-posting hours is **25.91784 model MW**, or **86.35804 public-equivalent MW per bank**. The [bank-state ledger](output/nygrid_2025_dover_parameters/replay/Dover_bank_states.csv) records targets, achieved flows, residuals, model phases, proxy phases and fallback/bound flags. The term `known_mode` in diagnostic field names means nonzero posted values, not independently verified breaker or bypass state.

An exact-tracking scenario is retained as a diagnostic. Its algebra closes the targets, but60 of287 hours require an unscaled angle proxy above40 degrees, reaching57.68 degrees. This does not prove real hardware infeasibility, given the coarse model and source qualifications; it does show why that exact reconstruction is not presented as a validated physical tap trajectory or chosen as the default. Initial exact-tracking outputs are preserved separately as diagnostic history.

## Results and attribution

The comparisons use the same8,651 hours, fixed bounded dispatch, loads and six existing transfer schedules. Eight annual scenarios cover69,208 scenario-hours. All pre-cutover prefixes are identical to the preceding model; the2,009 post-cutover scenario-hours for the seven new cases were independently checked.

The parameter and operating-state effects are separated before making any accuracy claim:

| Post-cutover MAE, public-equivalent MW | Prior line-parameter case | New parameters, neutral phase | Preferred bounded tracking |
|---|---:|---:|---:|
| Total East | 832.538815 | 832.546724 | 812.344836 |
| Central East - VC | 320.146961 | 320.202051 | 212.424480 |

The other five inherited operators are unchanged to numerical precision. Most of the change above comes from the external bank-flow operating reconstruction. The near-neutral result is consistent with the new line-plus-parallel-bank series reactance being close to the previous aggregate budget, but that agreement was not used to choose the estimate.

| Full-year MAE, public-equivalent MW | Prior | Preferred bounded tracking |
|---|---:|---:|
| Dysinger East | 259.171866 | 259.171866 |
| West Central | 256.327837 | 256.327837 |
| Total East | 429.692811 | 429.022868 |
| Moses South | 119.478483 | 119.478483 |
| Central East - VC | 320.122370 | 316.548638 |
| UPNY-ConEd | 235.140744 | 235.140744 |
| Sprain/Dunwoodie South | 178.800596 | 178.800596 |

The [56 annual rows](output/nygrid_2025_dover_parameters/comparison/annual_metrics.csv), [672 monthly rows](output/nygrid_2025_dover_parameters/comparison/monthly_metrics.csv), and [56 post-cutover rows](output/nygrid_2025_dover_parameters/comparison/post_cutover_metrics.csv) include every declared scenario. These remain the inherited aggregate interface operators; this work does not certify their full physical-flowgate/P32 identities. Internal observations were opened only for the separate posthoc scoring step.

## Validation

- Fourteen independent engineering tests cover the reference phasor, base conversion, phase signs, parallel sharing/circulation, passivity and mixed line sections.
- Three independently constructed network families preserve all original source circuits and inputs. The phase reduction retains both bank-control columns even though their net nodal effect has rank one; unequal phases can create circulating bank flow.
- The independent replay audit validates the complete parent, exact pre-cutover preservation, all2,009 changed-period scenario-hours, per-bank flows, phase constraints, active-bound optimality and neutral fallbacks. Maximum192/148-bus nodal residuals are `2.46e-10 / 3.43e-11 model MW`.
- Fresh MATLAB/MATPOWER checks pass **49 detailed192-bus plus49 condensed148-bus solves**, including saturated and ambiguous-zero states, **24 exact pre-cutover comparisons**, eight loader guards and six fixed-voltage complex-tap bank checks. Maximum branch disagreement is `1.20e-10 model MW`; all six existing transfers agree to solver roundoff.
- All784 annual/monthly/post-cutover metric rows are independently reproduced to `1.14e-12` maximum difference.

Receipts: [source/model review](output/nygrid_2025_dover_parameters/validation/source_model_review.json), [independent replay validation](output/nygrid_2025_dover_parameters/local_audit/Dover_final_replay_validation.json), [MATLAB validation](output/nygrid_2025_dover_parameters/validation/matlab_validation.json), and [comparison validation](output/nygrid_2025_dover_parameters/local_audit/Dover_comparison_validation.json).

These checks validate the declared DC construction, controller and reporting. Full-system AC feasibility, actual winding losses, manufacturer tap-dependent impedance, hourly bypass states, measured physical taps and actual thermal limits remain unverified.

## Use the applied case

```matlab
cd('C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems');
addpath('System Matpower Format');
% First hour at the preserved full-service boundary:
mpc = npcc_nygrid_2025_dover_dc(8472, 'bounded', 'x_nominal');
[result, success] = rundcpf(mpc, mpoption('verbose', 0, 'out.all', 0));
interfaces = npcc_nygrid_2025_slim_interfaces(result);
```

`bounded` is the default. `neutral` is the declared zero-phase operating scenario. `exact` with `x_nominal` is diagnostic only. Impedance choices are `x_low`, `x_nominal` and `x_high`. Before the cutoff the original dated case is returned; excluded source/cohort hours are rejected explicitly.

The [Dover source register](output/nygrid_2025_dover_parameters/sources/dover_source_register.csv), [P34 input receipt](output/nygrid_2025_dover_parameters/local_audit/Dover_P34_input_receipt.json), [network receipt](output/nygrid_2025_dover_parameters/network/network_receipt.json), and [replay receipt](output/nygrid_2025_dover_parameters/replay/replay_receipt.json) identify the reproducible dependencies. Builders and independent validators are under `scripts/nygrid_2025_dover_parameters`; rebuilds should use a copied workspace to preserve the sealed delivered artifacts. `run_dover_replay.py --score-only` is the explicit observation-reading stage.

Verify the packaged files, current proof hashes and report links without rebuilding:

```powershell
python scripts/nygrid_2025_dover_parameters/finalize_dover.py --verify
```

The [delivery manifest](output/nygrid_2025_dover_parameters/DELIVERY_MANIFEST.json) records the applied-model scope and remaining physical qualifications alongside every delivered file hash.
