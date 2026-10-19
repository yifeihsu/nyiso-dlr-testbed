# Remaining-error investigation

Read [the diagnosis](../../NYGRID_2025_REMAINING_ERROR_DIAGNOSIS.md) first. This is an additive research diagnostic for the sealed current model at `303b626`, not a replacement operating model. The evidence supplement includes these scripts, tables, figures, plans and receipts. It requires the existing repository/model/source archives to rerun; large frozen inputs are referenced by SHA-256 rather than duplicated.

The annual stage reads saved results only. It uses the unchanged 8,170 current equation/loss/recovery-qualified hours. The controlled stage uses 15 calendar-selected hours across four topology states; it must not be described as an annual replay or annual improvement.

## Reproduce from PowerShell

The verified environment is Python 3.13 with NumPy, pandas, SciPy and Matplotlib, MATLAB R2026a, and MATPOWER 8.1. The MATLAB helpers use the same external MATPOWER folder as the existing handoff workflow. Change that machine-specific dependency argument in the two probe runners when reproducing on another machine; do not change the frozen model or probe design.

```powershell
cd "C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems"
python scripts/nygrid_2025_remaining_errors/prepare_investigation.py
python scripts/nygrid_2025_remaining_errors/baseline/analyze_baseline.py
python scripts/nygrid_2025_remaining_errors/accounting/export_gate_terms.py
python scripts/nygrid_2025_remaining_errors/accounting/analyze_cut_accounting.py
python scripts/nygrid_2025_remaining_errors/baseline/niagara_prior_consistency.py
python scripts/nygrid_2025_remaining_errors/physics/analyze_saved_physics.py
python scripts/nygrid_2025_remaining_errors/prepare_probes.py
& 'C:/Program Files/MATLAB/R2026a/bin/matlab.exe' -batch "addpath('scripts/nygrid_2025_remaining_errors'); run_probes"
python scripts/nygrid_2025_remaining_errors/score_probes.py
& 'C:/Program Files/MATLAB/R2026a/bin/matlab.exe' -batch "addpath('scripts/nygrid_2025_remaining_errors'); run_pjm_partition_probe"
python scripts/nygrid_2025_remaining_errors/score_pjm_partition.py
python scripts/nygrid_2025_remaining_errors/baseline/review_root_probes.py
python scripts/nygrid_2025_remaining_errors/baseline/review_pjm_partition.py
python scripts/nygrid_2025_remaining_errors/accounting/review_baseline.py
python scripts/nygrid_2025_remaining_errors/plot_findings.py
python scripts/nygrid_2025_remaining_errors/build_sources_receipt.py
python scripts/nygrid_2025_remaining_errors/seal_delivery.py
```

Final independent checks are listed in their receipts under `output/nygrid_2025_remaining_errors/accounting/`. Run those before `python scripts/nygrid_2025_remaining_errors/seal_delivery.py`. Source guards intentionally reject changes to the sealed numerical inputs. Diagnostic outputs can be regenerated; protected model/map files cannot be silently rewritten by this pipeline.

## Artifacts and qualification

| Location under `output/nygrid_2025_remaining_errors` | Purpose |
|---|---|
| `baseline/` | Exact annual metric reproduction, temporal patterns, lag/common-cohort tests, source-prior comparison, independent probe reviews |
| `accounting/` | Explicit complete-cut identities, fixed source terms, external landings, bypasses, terminal corrections and closure checks |
| `physics/` | Matched AC/DC results, annual line-loss and voltage concentrations; descriptive associations are not causal |
| `probes/` | Frozen sample/design, finite-bound input changes, actual solve results/status, paired responses and readback receipts |
| `figures/` | Source-backed scientific PNG/PDF exports |
| `source_guard.json` | Hashes of 53 critical numerical sources and the unrelated pre-existing map changes |
| `verification_receipt.json` | Final source/receipt/packaging checks |
| `handoff/` | Additive diagnostic ZIP and archive receipt; existing current-model handoff remains intact |

The initial design has 150 cases: 142 equation/loss/recovery qualified, six rejected for insufficient finite hydro capability, and two line-search failures. The separate genuine PJM redistribution adds 30 qualified cases. The 15 baseline solves reproduce all 105 saved interface values exactly. Do not count the three capacity-proportional PJM variants as independent allocation perturbations: they are no-op controls. Parent-41 variants change electrical admittance only; their retained thermal metadata are not certified for conductor/DLR use.

The numerical investigation does not certify the physical 2025 P32 meters, historical plant dispatch, operating limits, or a replacement model. Never promote the oracle residual adjustments into source data.
