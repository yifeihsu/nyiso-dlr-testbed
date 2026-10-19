# Parent 41 / 185 / 195 physical repair

This version replaces the excessive parent-41 series resistance and relocates the existing fixed compensation on parents185/195. Historical numerical bundles and annual results remain preserved. The current model is compiled from the frozen repair into a new portable bundle; the annual driver uses its own authenticated baseline snapshot and applies the repair once.

## Frozen design

- Parent41: imported R/X =0.0018/0.0089pu on100MVA. The existing inverse-conductor search's first-ranked candidate gives ACSS Mallard, four uncoupled circuits, one conductor per phase,10.750872722km effective length, GMD3.948477m, and95°C reference resistance. Derived geometric B is0.021267472267637012pu. All corresponding material/electrical thermal metadata are rebuilt. This is a synthetic realization; approximate map endpoints do not establish route length or installed conductor identity. The existing aggregate2000A terminal apparatus ceiling is retained independently of the parallel-conductor hypothesis.
- Parents185/195: conductor and section R/X/B stay fixed. Each section contributes a reactor of `0.75 × baseMVA × B_section / 2` MVAr at1pu to each of its two endpoints. Interior nodes receive the contributions of adjacent sections. The original endpoint-only allocations are removed first. This preserves the total75% nominal compensation rating, while reducing the unbalanced local charging that raised interior voltages.
- Bus/branch/generator axes, all8760 source profiles, six fixed transfers, native/HQ active generation, voltage limits and generator voltage setpoints are preserved. New interior shunts are passive admittance terms; exact reduction still retains 148 voltage buses.

The candidate receipt binds the final helpers, parameter file and independent targeted checks. Do not edit those inputs in place after the annual run begins. A different physical proposal needs its own version and replay label.

## Code and evidence

| Path relative to this directory | Responsibility |
|---|---|
| `prepare_parent41.py` | Reconstruct and freeze the existing R/X-conditioned conductor choice without using observed flows |
| `core/nyrepair_apply_case.m` | Apply both physical corrections to an authenticated baseline case |
| `physics/nyrepair_apply_185195.m` | Update reactor placement, ledger, and full-axis shunt metadata |
| `validate_candidate.m` | Check17 targeted hours, all four topology states, thermal forward equations, and detailed/compact agreement |
| `physics/review_combined_candidate.py` | Independently reconstruct all four saved cases and conductor physics |
| `freeze_candidate.py` | Seal the validated candidate before annual replay |
| `annual/` | Snapshot the baseline, replay every source-qualified hour, preserve failures, independently validate and score the year |
| `independent/` | Independent readback of annual physical behavior |
| `delivery/` | Compile corrected templates, update structure/map, validate the standalone runtime, and build the handoff |

Outputs are under `output/nygrid_2025_physical_repair`. The frozen numerical baseline commit is6d46babc3af4335638241e3abff525425a0a6d7e. Original numerical files remain authoritative for reproducing earlier reports; the new candidate and its annual results have separate hashes and paths.

## Core reproduction commands

From PowerShell:

```powershell
cd "C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems"
python scripts/nygrid_2025_physical_repair/prepare_parent41.py
& 'C:/Program Files/MATLAB/R2026a/bin/matlab.exe' -batch "addpath('scripts/nygrid_2025_physical_repair'); validate_candidate"
python scripts/nygrid_2025_physical_repair/physics/review_combined_candidate.py
python scripts/nygrid_2025_physical_repair/freeze_candidate.py
python scripts/nygrid_2025_physical_repair/annual/prepare_annual_contract.py
& 'C:/Program Files/MATLAB/R2026a/bin/matlab.exe' -batch "addpath('scripts/nygrid_2025_physical_repair/annual'); run_nyrepair_annual('physical_repair_v1',true)"
```

`resume=true` authenticates completed monthly checkpoints. An incomplete or differently sourced checkpoint is not overwritten. A fresh independently versioned run can use a new label. The MATLAB dependency is MATPOWER8.1 at the explicit path in the setup helper; no persistent MATLAB path is changed.

Annual source eligibility is8651 of8760clockhours. Equation/loss/recovery qualification, voltage/reactive/capability limits, apparatus/current limits, and installed-asset validity are different claims. The final report and package must use the completed annual receipts for counts; passing the targeted17-hour tests alone does not establish annual success.
