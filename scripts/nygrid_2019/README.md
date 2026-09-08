# Reproduce the released NYgrid model with 2019 NYISO interfaces

This workflow runs the paper's released 57-bus DC model at NYISO load scale.
It does not load the repository's compact 71-bus model. The pinned NYgrid
source remains unchanged. A separate execution copy caches input tables;
all allocation and reduction arithmetic remains the released implementation.

The seven interfaces are scored twice on each identical solved state:

- `released_plot_mw`: literal `Utility/flow4Plot.m` branch indices.
- `corrected_operator_mw`: released `if.map` indices, independently checked
  against the paper's directed zone pairs and actual branch endpoints.

Five plotting formulas have stale indices. Both series remain in the evidence;
the correction changes measurement only, not topology, generation, or dispatch.

## Inputs and dependencies

MATLAB and MATPOWER are required for the model. The verified environment used
MATLAB R2026a Update 3 and MATPOWER 8.1 with its legacy power-flow core, which
avoids modern data-model metadata incompatibilities in the older case. The
reduction toolbox is pinned to its June 2019 revision. The originally linked
toolbox also matches the two smoke cases after a documented interpolation
compatibility substitution. Its exact version used for the paper is unknown.

Python requires NumPy and pandas for input auditing, and SciPy and Matplotlib
for independent replay and plots. These already existed locally; nothing was
installed. Download scripts verify upstream Git blobs and SHA-256 fingerprints.

```text
python scripts/nygrid_2019/fetch_upstream.py
python scripts/nygrid_2019/fetch_reduction_toolbox.py
python scripts/nygrid_2019/prepare_cached_upstream.py
python scripts/nygrid_2019/audit_nyiso_interfaces.py
python scripts/nygrid_2019/test_audit_nyiso_interfaces.py
python scripts/nygrid_2019/test_summarize_reproduction.py
```

The interface audit independently retrieves all twelve official P32 archives,
reproduces the released hourly arithmetic means and interpolation, and records
duplicates, gaps, limits, and daylight-saving ambiguities. Add `--offline` to
repeat it from the pinned local ZIPs. The CSV and actual MAT input were also
compared directly; to regenerate the optional MAT export in MATLAB:

```matlab
d = load('tmp/nygrid_2019_reproduction/upstream/Data/interflowHourly_2019.mat');
writetable(d.interflowHourly, 'output/nygrid_2019/prepared_mat_interfaces.csv');
```

## Model runs

From the repository root in MATLAB:

```matlab
addpath('scripts/nygrid_2019');
run_upstream_smoke('mirror');
run_upstream_smoke('official_compatibility');
validate_cached_reproduction;
audit_interface_operators;
run_annual_reproduction(1,2190,'annual_1');
run_annual_reproduction(2191,4380,'annual_2');
run_annual_reproduction(4381,6570,'annual_3');
run_annual_reproduction(6571,8760,'annual_4');
```

The four annual calls may run in separate MATLAB processes. Every case checks
the fixed bus/generator identities, branch parameters, DC solution status,
finite flows, and nodal balance. Saved MAT files contain the inputs needed for
an independent linear DC replay, full branch-flow matrices, both interface
measurements, and selected complete cases. The final CSVs indicate completion;
an intermediate MAT checkpoint does not establish full coverage.

Normalize generated evidence CSV line endings to LF before final input
fingerprinting, consistent with this repository's `.gitattributes`.

```text
python scripts/nygrid_2019/replay_dc.py --require-annual
python scripts/nygrid_2019/summarize_reproduction.py
```

The primary score retains all 8,760 released local-hour labels. A separate
diagnostic excludes interpolated and ambiguous hours. Pointwise percentage
error is undefined at exactly zero observed flow; no denominator floor is
introduced. Flow-weighted absolute error is the sum of absolute mismatch
divided by the sum of absolute observed flow. The paper-style metric instead
uses the hourly positive interface limit, including West Central's 9999 value.

Neither a DC solution nor agreement with reconstructed generation constitutes
AC/reactive-capability validation or independent generator telemetry.
