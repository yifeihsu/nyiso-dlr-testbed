# Current NYgrid model for DLR research

This package contains the latest 148-bus loss-consistent AC model, its four
effective-date network states, 2025 operating inputs, exact detailed-current
recovery and R/X-conditioned synthetic conductor screen. The four states belong
to this one model version. Earlier model families and archived experiments are
not required or included.

Read `NYGRID_2025_LATEST_MODEL_STRUCTURE.docx` for the model description and
`DATA_DICTIONARY.md` for array axes, units and qualification flags.

## Interactive network map

Open **[map/network_map.html](map/network_map.html)** for the current network,
zone labels and saved hourly interface flows. The HTML contains its data,
basemap and runtime; viewing it does not require MATLAB or a data server.

The map includes the 148 retained AC view, detailed corridor view, all eleven
NY zones, seven signed interface flows and the four dated 2025 network states.
Use its UTC date/time, hour index or slider to choose a point. Select an
interface to highlight its current member corridors, or a zone to inspect its
load, loss and net native generation. Model MW and public-scale MW are separate
display options. Unavailable computed hours remain blank.

The map displays saved results and does not recompute a power flow when its
controls change. See [map/README.md](map/README.md) for conventions and
`verification/MAP_PROVENANCE.json` for source and validation identities.

## Requirements and setup

Use a licensed MATLAB installation with JVM support. The package includes the
MATPOWER 8.1 numerical code subset and its component licenses. It does not
include MATLAB. The portable workflow is checked using MATLAB R2026a Update 3;
other MATLAB releases have not been established by those checks. Python 3.9 or
newer is optional for the standard-library integrity verifier only.

Extract the ZIP. In MATLAB, change to the extracted directory containing this
file, then run:

```matlab
addpath(fullfile(pwd, 'runtime'));
env = setup_nygrid_latest(pwd);
```

The setup changes paths for the current MATLAB session only. Start a clean
MATLAB session when switching between separate copies of the package.

To check the package on your machine in a fresh MATLAB session:

```matlab
check = smoke_nygrid_latest(fullfile(pwd, 'runs', 'smoke'));
assert(check.passed);
```

This checks the four dated loaders, the compact reduction, a current coupled
solve, an independent detailed Newton power flow, current/heat identities and
input rejection guards. It uses only the packaged runtime, selected MATPOWER
code and base MATLAB paths, and writes a receipt with individual check results.
It does not run the full year or establish operating feasibility.

## Load and solve

```matlab
hour = 8508;  % a tested post-Dover hour
m = load_nygrid_latest(hour);
[result, audit, full, allocation] = run_nygrid_latest_acpf(hour);
assert(result.success && audit.loss_allocation_gate);
assert(audit.reduction_and_equation_gate);

% Detailed electrical-section axis; columns are from, to, series amperes.
I_A = result.recovered_line_current_A;
branch_keys = full.userdata.ac_system.branch_keys;
V_full_pu = result.recovered_full_voltage;
operating_limits_pass = audit.VQ_and_generator_assumption_gate;
```

`m` is the detailed input case, and `result.bus` contains the 148 retained buses.
`full` contains the recovered detailed solution. Source-ineligible hours are
rejected; unsuccessful solves must not be used as predictions. Hour 8508 passes
the equation and loss-accounting gates while its operating-limit flag is false.

The 8,760-hour axis uses the local 2025 year, represented by unique UTC
timestamps from 2025-01-01 05:00Z through 2026-01-01 04:00Z. There are 8,651
source-eligible hours. See the data dictionary for the four state boundaries.

## Apply explicit scenario weather

```matlab
weather = struct('ambient_c', 25, 'wind_m_s', 1.5, ...
    'wind_angle_deg', 90, 'solar_w_m2', 1000, 'pressure_pa', 101325);
cached = struct('full', full, 'audit', audit, 'allocation', allocation);
screen = screen_nygrid_latest_dlr(cached, weather);

eligible = screen.candidate_and_exclusion_ledger;
branch_screen = screen.branch_screen;
segment_screen = screen.segment_screen;
thermal_envelopes_pass = screen.all_candidate_current_envelopes_satisfied;
```

This is declared uniform scenario weather, not observed route weather. A
multirow weather table must match the candidate branch-key and segment-ID order
exactly. The current selector yields 179 eligible parents before Dover and 180
afterward. It holds the electrical R/X/B and solved dispatch fixed. It evaluates
ampacity at the declared temperature limit; it does not solve conductor
temperature, thermal-resistance feedback, or DLR-constrained OPF.

Thermal eligibility requires a valid catalog/geometry realization reproducing
current R and X; actual installed conductor identity is not required. The
screen preserves the distinction between imported-R/X realizations and
declared engineered electrical parameters. It does not choose a different
conductor merely to remove a high utilization. Inspect the exclusion and
forward-reconstruction ledgers before changing assumptions.

## Integrity and interpretation

From a command prompt in the extracted directory, optionally run:

```text
python verify_package.py --root .
```

The verifier checks the supplied files, manifest and checksum table without
Git or access to the original research repository. Extra research outputs can
be stored in a new `runs` directory; the sealed input files should be retained.

The current annual model has 8,170 equation/accounting-qualified solutions and
481 rejected source-eligible attempts. None passes the joint voltage/reactive/
generator-capability gate. Packaging does not change those scientific limits
or constitute a new annual power-flow run. Check `verification` for the actual
portable runtime validation scope. The model supports synthetic research;
operational feasibility, installed asset ratings, measured critical-span
weather, N−1 security and DLR economics require separate work.
