# Small-bus 2025 Downstate alternative

The preferred small-bus DC research case is **148 buses: all 140 original NPCC
buses plus eight critical 345-kV stations**. New York has 54 buses (46+8);
the 94 original external buses are preserved. The 191-bus model remains a
frozen detailed reference.

Read [the report](../../NYGRID_2025_SLIM_DOWNSTATE.md) for the station choices,
branch classes, validation and remaining limitations.

[Geographic figures](../../output/nygrid_2025_slim/geography/README.md) now
match the148-bus model. The [interactive map](../../output/nygrid_2025_slim/interactive/network_map.html)
is a self-contained offline HTML file with pan/zoom, bus/branch details, and
connection-category toggles. [Map instructions and validation scope](../../output/nygrid_2025_slim/interactive/README.md).

## Load and solve

```matlab
cd('C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems');
addpath('System Matpower Format');
mpc = npcc_nygrid_2025_slim_dc(1); % default: topology_dated
[result, success] = rundcpf(mpc, mpoption('verbose', 0, 'out.all', 0));
assert(success);
interfaces = npcc_nygrid_2025_slim_interfaces(result);
```

Use `npcc_nygrid_2025_slim_dc(hour_index, 'topology_year_end')` for a fixed
year-end counterfactual. The same 97 source-gap hours are rejected. Generator
outputs, bounds, original P/Q loads, four DC schedules, and the scale factor
remain frozen. The eight additions have zero injection in this baseline.

**Use the interface accessor after solving.** A simple sum of new zone-crossing
branches does not preserve the old Dunwoodie measurement after internal buses
are eliminated. The accessor applies the saved exact response operator to
solved angles. It returns model MW and public-equivalent MW (`model MW/gamma`).
The loader removes native `if.map` so an incomplete or stale map cannot be
mistaken for the complete seven-interface definition.

## Rebuild in a new directory

The frozen baseline and detailed-reference artifacts must be present. These
commands avoid overwriting the delivered slim case.

```powershell
cd 'C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems'
$taskPython = '.\tmp\nygrid_2025_inputs_runtime_20261010\Scripts\python.exe'
$taskOutput = '.\tmp\nygrid_2025_slim_rebuild_user'
if (Test-Path -LiteralPath $taskOutput) { throw 'Choose a fresh directory' }
& $taskPython scripts/nygrid_2025_slim/build_slim_network.py --output "$taskOutput\network"
& $taskPython scripts/nygrid_2025_slim/replay_slim.py --folder $taskOutput
& $taskPython scripts/nygrid_2025_slim/validate_slim.py --folder $taskOutput
matlab -batch "addpath('scripts/nygrid_2025_slim'); validate_matlab_slim(fullfile(pwd,'tmp','nygrid_2025_slim_rebuild_user'));"
```

To check the canonical delivery without regenerating its saved artifacts:

```powershell
& $taskPython -m unittest discover -s scripts/nygrid_2025_slim -p 'test_*.py' -v
& $taskPython scripts/nygrid_2025_slim/finalize_slim.py --verify
```

The numerical workflow uses NumPy, SciPy, pandas and MATLAB/MATPOWER. The
diagram uses Graphviz and its Python package. The tested task runtime already
contains the Python dependencies.

`run_checks.py` regenerates the saved test receipt; `draw_slim_network.py`
regenerates the diagram. After deliberately rebuilding canonical artifacts,
run `finalize_slim.py` without `--verify` to refresh their delivery fingerprints.

## Data contract

`network/network_cases.mat` has five common-axis 148-bus cases, the kept and
eliminated IDs, and recovery structures keyed by state name without `_case`.
Recovery maps consume retained **angles in radians** and include affine phase
offsets. They recover 191-bus angles, 410 detailed branch records and the seven
original interface functionals. Matrix units are model MW/radian where
appropriate. The fixed gamma is 0.30012075175285535.

`branch_register.csv` separates 225 original records, 14 exact direct historical
source circuits, five retained declared assumptions, and 30 equivalent pairs.
Each equivalent's source component and original circuit contributions are
registered separately. No coefficient-size threshold prunes required couplings.

Only added zero-injection buses are removed. The old asset-remapping diagnostic
places generators and load on eliminated nodes and is not an accepted input to
this zero-injection alternative. Equivalents are passive DC representations;
R/B/rating zeros are explicit placeholders. They do not define conductors,
thermal limits, AC equivalents or physically verified line routes.
