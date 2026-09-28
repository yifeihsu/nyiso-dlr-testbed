# NY-only Package A reference

Electrical qualification: **true**, scoped to one assumed 2019 PERFORM source reference. Final S14 candidate, contemporary coverage and DLR readiness remain unqualified.

The immutable source contains 1576 buses, 2371 branches and 615 generator records (not physical-unit count). Its reproduced PF converges, with 1 generator limit violation(s); maximum active violation 47.787356 MW.

Twenty boundary proxies are represented by fixed PQ injections at original NY bus IDs. Inactive records remain zero. The separate Marcy RF placeholder is removed without any P/Q injection. A distinct assumed Marcy Q-only PV device has P=0 and Q bounds [-900,900] MVAr. Roseton bus847 supplies the native angle reference.

| Quantity | Value |
|---|---:|
Gross demand | 29799.660000 MW |
Fixed net boundary injection | 1292.635022 MW |
Native generation | 29083.764074 MW |
Branch and shunt losses | 576.739096 MW |
Power-accounting error | 1.6048034e-09 MW |
Native dispatch L1 movement from source priors | 0.879980 MW |
Boundary schedule movement | 0.000000 MW |
Assumed support active injection | 0 MW |
Assumed support Q | -395.658308 MVAr |
| Native reactive dispatch L1 movement | 4067.377425 MVAr |
| Maximum voltage movement from source | 0.066076 pu |

The bounded solve minimizes squared native P-prior deviations with MATPOWER MIPS; it does not fit internal interfaces. Native voltage/reactive controls vary within original source envelopes. Gross loads, source shunts, branches, boundary PQ and native capability limits remain fixed. The Marcy support envelope is a declared research assumption, not a verified physical device.

Independent fixed-input PF passes: true. Maximum nodal mismatch 2.00793146e-09 MW / 4.4455879e-09 MVAr. Maximum reference P adjustment 3.97911628e-05 MW. No relaxation or fictitious active injection is used in the accepted reference.

Every original snapshot, fixed-control repair, bounded solve and replay attempt has a row in operating_attempts.csv. Each has full bus/generator/branch ledgers in physical units. Original source violations are preserved in original_source_*.csv; they are not silently repaired in source files.

Reproduce from repository root with `run_ny_only_foundation`; independently replay the saved input with `replay_ny_only_foundation`. Fast `run_operating=false` checks never establish electrical qualification.

Limitations: source-era inferred/assumed controls and boundary Q, ambiguous identical parallel circuit IDs, no contemporary observations, no NPCC internal replacement, no thermal eligibility. The voltage envelope remains the explicit source 0.9-1.1 pu envelope; this reference is not evidence for a tighter study envelope or NYISO certification.

Source preservation refers to the canonical MATPOWER conversion. The RAW remote regulator at generator 138/1 targets bus1296, while the canonical conversion controls local bus138; this conversion limitation is retained and disclosed in the control inventory. It is not a claim of reproducing every RAW control.
