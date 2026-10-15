# Corrected NYgrid 2025 model for DLR research

This package contains the corrected 148-bus AC model, four effective-date
states, unchanged 2025 operating inputs, exact detailed-current recovery and
an R/X-conditioned synthetic conductor screen. Open `map/network_map.html` in
a browser for the offline network, zonal data and annual interface flows.
Read `NYGRID_2025_PHYSICAL_REPAIR_MODEL_STRUCTURE.docx` for the current model
and `DATA_DICTIONARY.md` for axes, units and qualification flags.

The completed fresh annual replay retained all 8,760 timestamps and attempted
all 8,651 source-eligible hours. 8,651 hours
passed the AC equation and loss-accounting gates;
0 passed the joint voltage
and generator assumptions; 0 passed the
full declared operating gate. These gates are separate. The package does not
claim installed facility ratings or a feasible historical dispatch.

## Setup and run

Use MATLAB with JVM support. The included numerical vendor subset is MATPOWER
8.1; validation used MATLAB R2026a. Extract this ZIP and change MATLAB's current
directory to the folder containing this file. Use a fresh MATLAB session when
switching between package versions.

```matlab
addpath(fullfile(pwd, 'runtime'));
env = setup_nygrid_latest(pwd);
mpc = load_nygrid_latest(8508);
[result, audit, detailed, allocation] = run_nygrid_latest_acpf(8508);
assert(result.success && audit.loss_allocation_gate);
```

`result` contains the retained network and recovered currents. `detailed`
contains the recovered detailed solution. Always inspect the separate audit
flags before interpreting an operating point. The callable runtime uses the
compiled corrected templates and does not invoke the original model builders.

```matlab
weather = table(25, 0.6096, 90, 1000, 101325, ...
    'VariableNames', {'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'});
cached = struct('full', detailed, 'audit', audit, 'allocation', allocation);
screen = screen_nygrid_latest_dlr(cached, weather);
check = smoke_nygrid_latest(fullfile(pwd, 'runs', 'smoke'));
assert(check.passed);
```

The thermal screen needs explicit weather and preserves the electrical
solution. It is a one-way synthetic conductor calculation with no OPF or
temperature-feedback solve. MATLAB is not included. Optional Python verifies
package integrity using only its standard library:

```text
python verify_package.py --root .
```

## What changed

Parent 41 restores the imported R/X pair with one coherent declared conductor
and derived charging B. Parents 185 and 195 keep their conductor R/X/B and
total 75 percent fixed reactor rating, with section-local placement along the
existing passive numerical buses. The detailed and retained axes, native and
HQ active profiles, demand, transfer schedules, phase controls, voltage limits
and generator capability assumptions are preserved.

The prior static model and earlier manual remain in the preserved baseline
delivery. This package contains the corrected current version. The two hourly
profile files are byte-identical to that baseline. Baseline source commit:
`2e0fcd5c3f0ae39d04f27a733ce30eb148b0b243`. Repair candidate SHA-256:
`3ea77c854ffff4e8eb30fa72fc92296e024cb23eb3744010e276bff49e3fc08f`. Current static model
SHA-256: `5f0d7f3745dcc8f298e6f6d3c6d5734d930737d6a087d5e176aeea2380de7385`.

## Map and evidence

The map contains all 8,760 hours and switches dated topology automatically.
It displays model MW by default; the public-scale option divides aggregate
power by the fixed gamma. Failed or source-excluded solved flows remain null.
Gross load, prescribed native generation and fixed transfers use the source
mask. Coordinates are qualified source anchors and schematic connections,
not a reconstruction of transmission routes or physical interface meters.

`verification/` includes the frozen candidate, annual, scoring, runtime and
map receipts. `model/structure/` contains exact bus, branch, generator and
transfer ledgers. `analysis/` contains the annual hour-quality and public
interface comparison tables. Full monthly solve artifacts are retained in
the research checkout and are not required by this portable runtime.
