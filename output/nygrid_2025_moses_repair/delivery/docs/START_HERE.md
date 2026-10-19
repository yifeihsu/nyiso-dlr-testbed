# Corrected NYgrid 2025 model for DLR research

This package contains the corrected 148-bus AC model, four effective-date
states, corrected hydro and PV20 operating inputs, exact detailed-current recovery and
an R/X-conditioned synthetic conductor screen. Open `map/network_map.html` in
a browser for the offline network, zonal data and annual interface flows.
Read `NYGRID_2025_MOSES_REPAIR_MODEL_STRUCTURE.docx` for the current model
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

St Lawrence monthly EIA net generation is conserved over the entire year,
including explicit latent energy on the 109 excluded hours. Dated unit
admission keeps 15 active 57 MW units each month. Conventional hydro is
redistributed within original bounds while hourly reconciled hydro totals,
pumped storage and other fuel profiles remain fixed.

A new fixed-PQ PV20 input uses Sand Bar P34 PTID 325270 at bus 49, with the
same P removed from existing ISONE injections to preserve aggregate exchange.
Q is assumed zero. Sand Bar is a proxy for the physical Plattsburgh gate;
South Hero load, intervening losses and the 2025 sign convention are not
independently measured. The physical seven-term Moses boundary is documented
but not certified against the synthetic comparison operator.

The parent 41 and 185/195 network corrections are inherited unchanged. Gross
load, other fuel profiles, HQ and Ontario PAR inputs, clock, scale, source
mask and original comparison operators are preserved. Both hourly profile
files change. Source baseline commit: `f6c124a97b16f45a98a538c121c6006556255005`.
Current static model SHA-256: `c2142719b6c754769a5796e7f0f866e0eedf25f2a07b45dc0b4910294e23ecc8`.
Candidate hashes are recorded under `verification/`; source-policy receipts
and ledgers are under `analysis/generation/` and `analysis/boundary/`.

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
interface comparison tables plus the generation and boundary source policies.
`sources/` contains primary evidence and extraction receipts. The
`SOURCE_PATH_INDEX.json` maps original paths retained in frozen receipts to
their portable counterparts. Historical authoring inputs not included in the
package remain provenance references. Full monthly solve artifacts are retained
in the research checkout and are not required by this portable runtime.
