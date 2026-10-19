# Direction-verified St. Lawrence PAR controlled-transfer replay

Read [the source, implementation and results report](../../NYGRID_2025_VERIFIED_PAR_CONTROLS.md).
This is a separate revision. It preserves the full 148-bus model and the prior
hydro correction, while representing two observed external PAR transfers with
explicit source direction and necessary per-device nominal-capacity checks.
It does not reconstruct physical tap settings or establish complete hardware
P/Q/thermal operating limits.

From the repository root, verify an existing delivery without regenerating it:

```powershell
cd 'C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems'
$taskPython = '.\tmp\nygrid_2025_inputs_runtime_20261010\Scripts\python.exe'
& $taskPython scripts/nygrid_2025_par_controls/finalize_controls.py --verify
```

To deliberately rebuild this revision from its preserved sources:

```powershell
& $taskPython scripts/nygrid_2025_par_controls/build_control_inputs.py
& $taskPython scripts/nygrid_2025_par_controls/run_checks.py
& $taskPython scripts/nygrid_2025_par_controls/replay_controls.py
& $taskPython scripts/nygrid_2025_par_controls/validate_controls.py
matlab -batch "addpath('scripts/nygrid_2025_par_controls'); validate_matlab_par;"
& $taskPython scripts/nygrid_2025_par_controls/build_figures.py
& $taskPython scripts/nygrid_2025_par_controls/finalize_controls.py
```

Rebuilding changes creation-time receipts; numerical results should reproduce.
The input compiler uses the old frozen P34 archives and the new frozen direction,
equipment and P53A evidence. It does not require reacquiring the website or
choosing a sign. All original 2019/2025 source and model folders remain intact.
The existing research Python requires NumPy, pandas and SciPy; figures use
Matplotlib. MATLAB/MATPOWER is needed for the independent loader checks.

## Contracts

- `controls/inputs.npz` and `.mat`: exact 8,760-hour UTC axis, ordered PTIDs
  `[25118,25119]`, separate observed and raw schedule arrays, quality masks,
  gamma, nominal-P screen and embedded provenance metadata. P34 positive flow
  is Ontario-to-New-York. P53A sign remains diagnostic and is not selected as
  an operating input.
- `controlled_equivalent.py`: deactivates original passive branch 211 as a
  representation substitution and appends two ideal lossless transfer records
  from model bus 100 to 48. Its `dcline` records are PAR equivalents, not new
  physical HVDC facilities. All old branch parameters and four DC rows remain.
- `replay/*_verified_PAR_flows.mat`: fresh dated/year-end solutions, separate
  per-device transfers, and logical branch-211 transfer. The inactive passive
  AC record's zero PF is not the physical external transfer.
- `comparison/`: all seven internal interfaces, evaluated post hoc, on the same
  source-qualified hours as both baselines. `replay_controls.py --score-only`
  recalculates metrics after verifying saved replay hashes.
- `npcc_nygrid_2025_par_controlled_dc(hour_index, topology)`: loader for this
  revision; `topology` is `dated` by default or `year_end`. Use the existing
  `npcc_nygrid_2025_slim_interfaces` accessor after a successful `rundcpf`.

The source direction is verified. The 300 MVA nominal capacity supplies only
the necessary `|P|<=300 MW` screen. Unknown Q and equipment conditions prevent
complete thermal qualification. The ±60-degree physical range is a no-load
design property, not a limit on the previous aggregate equivalent phase.
Missing/out-of-envelope measurements fail closed and are never clipped.
