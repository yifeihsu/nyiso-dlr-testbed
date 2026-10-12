# Parameters for lines added relative to the frozen 2019 model

The added paths already had numerical parameters in the earlier 2025 construction. Those values were a mixture of exact historical source rows, inherited corridor budgets, cable analogs and derived DC equivalents. The flowgate-definition audit did not set new electrical parameters.

This work traced the six activated project-path records relative to `refined_2019`, matched the public conductor evidence, replaced the F84 aggregate-budget impedance with an engineering estimate, corrected the Staten cable route length, and validated the resulting five network scenarios. The earlier models and results are preserved.

**The implemented parameter changes have passed source, arithmetic, DC network and independent solver validation. This does not establish an as-built AC model or complete thermal qualification.** Dover line-only estimates are saved separately because the PAR series impedances and operating states remain unresolved. RCC conductor dimensions, bonding and charging remain unresolved; an underground cable does not receive an overhead ACSR/ACSS model.

## Which additions already had parameters?

The [existing-assignment inventory](output/nygrid_2025_line_parameters/local_inventory/existing_project_parameter_assignments.csv) and [inventory receipt](output/nygrid_2025_line_parameters/local_inventory/existing_assignment_receipt.json) reconstruct the original choices:

- F84 used 40% of the old Southington-Pleasant Valley aggregate R/X budget.
- Each Dover segment used 20% of that budget. Together they exactly reproduced the earlier Cricket Valley-Long Mountain proxy impedance, so the nominal resection alone changed no retained DC response.
- The three RCC cables used an East Astoria-Corona historical branch normalized by 5.5 miles. The source workbook explicitly labels that length as estimated from X/B; it is not a surveyed cable length. The template has R=0.0008, X=0.00401 and total B=0.03037 pu on a 100 MVA, 138 kV base. Its construction, conductor and resistance temperature are unverified.
- The associated RCC transformer/PAR values were also declared assumptions: R=0.002, X=0.03 pu, nominal tap and zero phase.

The 191-bus construction has 185 added representation records relative to the original 225-branch parent. Its 97 exact historical PERFORM circuit rows add detail that already existed in the historical source; they are not 97 newly built lines. The smaller model contains 30 derived Schur-equivalent edges, which likewise are not physical conductors. The actual `refined_2019` to year-end comparison contains six project activations and two retirements, with no prior R/X/B/rating/tap reassignment.

The official owner notice establishes that F84 was energized on **July 28, 2019**. Thus “added relative to 2019” means missing from this frozen model, not necessarily constructed after calendar 2019. The original 2020 label is retained only as historical model provenance. All modeled 2025 hours already treat F84 as available, so this date correction does not change the 2025 activation schedule.

## Applied parameter update

All values below are per unit on **100 MVA**; F84 is 345 kV and the RCC cables are 138 kV. B is total nominal-pi line charging, split equally between the two terminals. Zero B or rating in an unchanged DC proxy means unqualified/omitted, not a physical zero capacitance or infinite equipment capability.

| Model path | Previous R | Previous X | New R | New X | New B | Decision |
|---|---:|---:|---:|---:|---:|---|
| Pleasant Valley-Cricket Valley F84 | 0.0009200000 | 0.0145200000 | 0.0008742145 | 0.0073369903 | 0.1214494002 | Project conductor and representative-geometry estimate |
| Cricket Valley-Dover Y17 | 0.0004600000 | 0.0072600000 | 0.0004600000 | 0.0072600000 | 0 placeholder | Retain full-path proxy; line-only estimate saved separately |
| Dover-Long Mountain 398 | 0.0004600000 | 0.0072600000 | 0.0004600000 | 0.0072600000 | 0 placeholder | Retain full-path proxy; heterogeneous line-only estimate saved separately |
| Rainey-Corona RCC | 0.0008727273 | 0.0043745455 | 0.0008727273 | 0.0043745455 | 0 placeholder | Retain qualified historical cable analog |
| Gowanus-Greenwood RCC | 0.0001454545 | 0.0007290909 | 0.0001454545 | 0.0007290909 | 0 placeholder | Retain qualified historical cable analog |
| Goethals-Fox Hills RCC | 0.0013381818 | 0.0067076364 | 0.0013672727 | 0.0068534545 | 0 placeholder | Contractor route length 9.4 miles replaces assumed 9.2 miles |

Only full191 rows **391 and 410** change. The other four project paths, all 97 historical source circuits, original bus/generator records and source transfers are preserved exactly. Updated Schur equivalents and recovery operators are recomputed from the 191-bus case, keeping the same **148 buses and 274 branch records**. No new bus, interface member, control schedule or injection location was selected by observed-flow errors.

The [exact before/after table](output/nygrid_2025_line_parameters/estimates/before_after_parameters.csv), [applied scenario parameters](output/nygrid_2025_line_parameters/estimates/parameter_estimates.csv), and [engineering basis](output/nygrid_2025_line_parameters/estimates/engineering_basis.json) contain the complete precision and qualifications.

## Conductor and circuit matching

The [circuit-conductor match register](output/nygrid_2025_line_parameters/estimates/circuit_conductor_matches.csv) separates a documented design match from a verified installed manufacturer or a merely compatible family. The [normalized conductor catalog](output/nygrid_2025_line_parameters/conductors/conductor_catalog.csv) includes 13 source rows, with original temperature points and SI conversions.

**F84.** The [project EM&CP](output/nygrid_2025_line_parameters/sources/projects/CV_EMCP_Rev2_VolI_2017.pdf), PDF page 12 / printed page 9, specifies twin-bundled 795-kcmil Mallard ACSS. The project EMF input gives 1.14-inch diameter and 18-inch bundle spacing. The [Prysmian catalog](output/nygrid_2025_line_parameters/conductors/sources/prysmian_acss_us.pdf) matches the family, codeword, size, 30/19 stranding and diameter; it gives GMR=0.0389 ft and AC resistance at 25/75/200 C. This establishes a catalog/design match; it does not identify the installed supplier, steel coating or a measured line impedance.

At the project's normal-rating conductor temperature of 95 C, interpolation of the manufacturer AC resistance gives 0.026996 ohm/kft per subconductor. With 14.6 miles and two parallel subconductors per phase, the phase resistance is 1.040533824 ohm. The base impedance is 1190.25 ohm, giving R=0.0008742145129 pu.

The [2017 engineering drawing](output/nygrid_2025_line_parameters/sources/projects/CV_EMCP_AppS_EngineeringDrawings_20170825.pdf), PDF page 2, supports representative relative phase centers `(15.5,0)`, `(15.5,31)`, `(-15.5,14)` ft. The left offset is inferred by symmetry and equal insulator drops are assumed. These give GMD=10.182226556 m. The model uses transposed positive-sequence R/X/B, with an effective twin-bundle GMR for inductance and physical conductor radius for capacitance. The nominal capacitance calculation omits earth-image and ground-wire effects. This is a representative-structure estimate, not a route-average survey.

The source's 2214 A summer-normal circuit rating at 95 C converts to approximately 1323 MVA at 345 kV. RATE_A=1323 records that **conductor design** value. It is not a verified terminal-limited facility rating. RATE_B/C remain unqualified zeros rather than assigning the separately published 15-minute emergency rating to an unspecified duration. The phase-bundle current is not multiplied by two a second time.

Three predeclared sensitivity cases use phase spacing at 80% and 120% of the representative geometry, and the drawing's 30-ft minimum conductor clearance for an earth-image capacitance calculation. These are engineering scenarios, not confidence intervals or exhaustive uncertainty bounds. They were fixed before the score comparisons. Temperature-dependent resistance is supported by the catalog, but actual 2025 hourly conductor temperatures are not observed.

**Dover.** The [project-source register](output/nygrid_2025_line_parameters/project_source_register.csv) identifies approximately 0.30 miles of Y17 and 3.13 miles of the New York 398 section with twin Mallard ACSS. Connecticut filings identify a further 5.3 miles to Long Mountain with one 2156-kcmil ACSS conductor per phase; the adjacent NY filing calls this Bluebird. The 8.43-mile combined length is a cross-source approximation. The conductor transition is near the state line, not an independently surveyed exact segment boundary.

The [Dover line-only estimates](output/nygrid_2025_line_parameters/estimates/Dover_line_only_estimates_not_applied.csv) contain 36 temperature/geometry/section scenarios. For illustration, at 95 C and an explicitly assumed 25.6-ft adjacent H-frame phase spacing:

| Line-only section | Length, miles | R pu | X pu | Total B pu |
|---|---:|---:|---:|---:|
| Y17, New York twin Mallard | 0.30 | 0.00001796 | 0.00014969 | 0.00251381 |
| 398, New York twin Mallard | 3.13 | 0.00018742 | 0.00156173 | 0.02622738 |
| 398, Connecticut single Bluebird | 5.30 | 0.00025646 | 0.00341067 | 0.03499005 |
| Dover-Long Mountain composite line | 8.43 | 0.00044388 | 0.00497240 | 0.06121743 |

The CSV is authoritative at full precision. These illustrative line parameters exclude the two Dover PAR banks. The public agreement gives bank ratings and phase capability but not their series R/X; zero phase shift does not imply zero series impedance. Therefore these estimates are not substituted into the full operating path. The existing model's nominal zero-angle representation remains an unresolved assumption, and this audit does not resolve its detailed internal bank arrangement.

**RCC cables.** The contractor describes completed Goethals-Fox Hills as a **9.4-mile, single-circuit, 138-kV XLPE feeder**. [Contractor source](https://hauglandgroup.us/projects/goethals-to-fox-hills-substation/). This supports the route-length and insulation-family correction. It does not identify conductor material/area, sheath bonding, temperature, capacitance or installation-dependent rating. Queens and Brooklyn retain their historical electrical analogs and existing public route approximations.

The [cable charging scenarios](output/nygrid_2025_line_parameters/estimates/RCC_charging_catalog_scenarios_not_applied.csv) use 12 published 138-kV XLPE catalog sizes for each route, solely as conditional estimates. They are not applied or represented as installed cable matches. The manufacturer's capacitance-to-charging-current identity is independently checked. Underground ampacity requires cable-specific installation/thermal data; the overhead IEEE738 conductor treatment is inapplicable to these feeders.

## Fresh validation and comparison

The parameter checks passed 13 independent physics tests, eight source/estimate checks, and an independent matrix calculation of all 40 F84/Dover estimate rows with maximum discrepancy about `1.04e-16 pu`. The matrix calculation checks asymmetrical earth-image potential coefficients, phase permutation, single versus twin conductors, temperature interpolation, base/frequency/length scaling, total-pi B and real-power loss closure.

All five scenarios, including the identity control, passed the five-state reduction checks and 11 invalid-input probes. The identity overlay reproduces the saved branch parameters and recovery operators exactly. Only the two intended physical-path parameter rows change; the four retained project assumptions and historical source circuits remain bit-identical. Relevant proof is in the [independent overlay validation](output/nygrid_2025_line_parameters/validation/independent_parameter_overlay_validation.json).

The annual replay uses the same **8,651 qualified hours**, bounded generator outputs, loads, all four regional exchanges, original four DC schedules and two externally observed PAR transfers. It solves **43,255 scenario-hours**. Internal interface observations are loaded only in a separate posthoc scoring command after the parameter choices and replays are sealed.

| Existing interface proxy | Baseline MAE, public-equivalent MW | Engineering nominal MAE | Baseline WAPE | Engineering nominal WAPE |
|---|---:|---:|---:|---:|
| Dysinger East | 259.171866 | 259.171866 | 30.903030% | 30.903030% |
| West Central | 256.327837 | 256.327837 | 46.027619% | 46.027619% |
| Total East | 429.471338 | 429.692811 | 13.718628% | 13.725703% |
| Moses South | 119.478483 | 119.478483 | 22.129408% | 22.129408% |
| Central East - VC | 318.781798 | 320.122370 | 19.159781% | 19.240353% |
| UPNY-ConEd | 235.140744 | 235.140744 | 7.841942% | 7.841942% |
| Sprain/Dunwoodie South | 178.807288 | 178.800596 | 9.676215% | 9.675853% |

The engineering update slightly worsens Total East/Central East and slightly improves Sprain/Dunwoodie. It was not chosen to improve these scores. The unchanged western/northern complete cuts reflect the preserved injections and boundaries. These remain inherited aggregate interface proxies, not newly certified physical flowgates. [All 35 annual rows](output/nygrid_2025_line_parameters/comparison/annual_metrics.csv) and [420 monthly rows](output/nygrid_2025_line_parameters/comparison/monthly_metrics.csv) retain every scenario and result.

The full-year nodal residual is below `4e-11 model MW`. Numerical DC closure does not establish the complete physical flowgate expression, AC voltages/reactive feasibility, equipment thermal feasibility, hourly conductor temperature or actual PAR taps. The two-terminal AC nominal-pi component test verifies the implemented line equations; it is not a full-network AC certification.

Fresh MATLAB/MATPOWER validation passed **35 snapshots** covering seven distinct state/season hours in all five scenarios, seven loader guards, and two fixed-voltage two-bus AC component checks. Maximum branch-flow disagreement was `3.02e-11 model MW`, maximum interface disagreement `3.34e-11 model MW`, and all six transfer values agreed exactly. The AC component checks independently confirmed positive resistive loss and the total-B half split at the two terminals. [MATLAB validation receipt](output/nygrid_2025_line_parameters/validation/matlab_validation.json).

The [independent annual audit](output/nygrid_2025_line_parameters/validation/annual_replay_validation.json) checked all 43,255 scenario-hours using separately constructed branch equations and KCL. Maximum residuals were `4.46e-11 model MW` in the 148-bus network and `2.53e-10 model MW` after lifting to 191 buses. The [independent score audit](output/nygrid_2025_line_parameters/validation/comparison_validation.json) reproduced all 455 annual/monthly rows to `6.82e-13` maximum numeric difference. The capacitance-only sensitivity produced identical DC angles/flows, as it should.

## Load and reproduce

The previous preferred loader is preserved. The new engineering scenario is available explicitly:

```matlab
cd('C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems');
addpath('System Matpower Format');
mpc = npcc_nygrid_2025_line_estimated_dc(1, 'dated', 'engineering_nominal');
[result, success] = rundcpf(mpc, mpoption('verbose', 0, 'out.all', 0));
interfaces = npcc_nygrid_2025_slim_interfaces(result);
```

The loader also accepts `identity_reference`, `geometry_spacing_80pct`, `geometry_spacing_120pct` and `ground_image_30ft`, with `dated` or `year_end` topology. It verifies the saved case hash and preserves the six transfer records, dispatch bounds and bus identity axes.

From the same repository directory, use a Python runtime with NumPy, pandas and SciPy:

```powershell
python scripts/nygrid_2025_line_parameters/build_estimates.py
python scripts/nygrid_2025_line_parameters/build_parameter_overlay.py --parameters output/nygrid_2025_line_parameters/estimates/parameter_estimates.csv --output tmp/line_parameter_overlay_rebuild
python scripts/nygrid_2025_line_parameters/test_line_physics.py
python scripts/nygrid_2025_line_parameters/test_estimates.py
```

Choose a fresh overlay output directory. `run_parameter_replay.py` and its explicit `--score-only` mode target this stage's saved overlay folder; reproduce those into a copied workspace or update the documented output root before rebuilding delivery artifacts. Source acquisition, circuit matching, engineering estimates, network reduction, annual replay and scoring are separate stages with their own receipts.

Verify the packaged deliverable without rebuilding it:

```powershell
python scripts/nygrid_2025_line_parameters/finalize_line_parameters.py --verify
```

The [delivery manifest](output/nygrid_2025_line_parameters/DELIVERY_MANIFEST.json) binds the report, loader, scripts, source files, cases, replays and validation receipts. Verification also checks the current hashes recorded by the source and numerical proofs.

The remaining physical data gaps are concrete: Dover bank R/X and actual tap states; RCC installed cable dimensions, bonding and temperature-dependent electrical data; F84 route-average geometry and terminal limits; and the physical-flowgate/P32 bindings documented in the [preceding audit](NYGRID_2025_PHYSICAL_FLOWGATE_DEFINITIONS.md). No unknown conductor or control setting has been silently certified.
