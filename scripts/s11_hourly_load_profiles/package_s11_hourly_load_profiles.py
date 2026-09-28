"""Package the S11 dataset and its local reproduction inputs for handoff."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[2]
DATA = Path("output/s11_hourly_load_profiles")
DEST = ROOT / "output/s11_hourly_load_profiles_handoff"
PACKAGE = "S11_49bus_hourly_load_profiles"

GUIDE = """# S11 49-bus hourly load profiles - handoff

This package contains hourly active-load profiles and modeled reactive-load
profiles for every bus in the retained S11 reduced diagnostic model.

## Start here

Extract the ZIP and open its `S11_49bus_hourly_load_profiles` folder. The ready-to-use
data are in `output/s11_hourly_load_profiles/`:

| File | Contents |
|---|---|
| `pd_mw.csv` | 4,416 hourly rows; UTC/local timestamps, source timezone, then 49 `bus_ID` columns of MW |
| `qd_mvar.csv` | Same layout; modeled signed constant-power reactive component in MVAr |
| `s11_hourly_load_profiles.mat` | MATLAB `profile` struct; `pd_mw` and `qd_mvar` are **49 buses x 4,416 hours** |
| `bus_allocation.csv` | Bus names, zones, allocation weights, baseline P/Q, and fixed GS/BS |
| `coverage.csv` | Coverage and statewide demand range for each month |
| `zonal_pd_mw.csv` | The 11 original zonal hourly input series |
| `README.md` | Detailed allocation methodology and usage |
| `validation.json`, `independent_validation.json` | Allocation and source reconciliation results |
| `peak_pf_validation.json` | Single retained-peak AC power-flow integration result |
| `source_manifest.csv` | Paths and record counts for all 184 included source files |

CSV files can be read without MATLAB or this repository. Use the actual bus IDs;
they are **37-82, 9001, 9002, and 9003**, not consecutive IDs 1-49. MATLAB arrays
use the order in `profile.bus_id`. Both UTC and local timestamps are included.

## Coverage and assumptions

- January, April, and July of **2019 and 2025**: 4,416 hours and 216,384 bus-hour pairs.
  Each of the six monthly segments is complete. This is not two complete years;
  missing months and the intervening years have not been interpolated.
- Source data: 184 cached NYISO `palIntegrated` daily files, included under
  `System Matpower Format/NY_Lite/nyiso_public_cache/`.
- Each zonal hourly MW total is distributed using fixed saved-S11 load shares.
  These are synthetic bus allocations of observed zonal demand. All 49 buses
  are present; 28 carry active demand and 21 remain zero.
- Qd follows the saved case's signed constant-power Q/P ratios. Only bus 80 has
  nonzero Qd, with a negative ratio. It is not measured hourly reactive demand.
  Network GS/BS shunts remain unchanged and are excluded from the load arrays.
- Source EST/EDT labels are retained, with explicit local UTC offsets. The
  provider's labels have not been reinterpreted as interval beginning or ending.
- All source and allocation checks passed. The retained **2025-07-29 18:00 EDT**
  peak reproduces the saved case and passes standard and Q-limit-enforced AC PF.
  AC feasibility for the other hours has not been established. Set consistent
  generation dispatch, external schedules, and controls before running them.

## MATLAB quick start

From the extracted package root:

```matlab
addpath('System Matpower Format', 'System Matpower Format/NY_Lite');
data = load('output/s11_hourly_load_profiles/s11_hourly_load_profiles.mat');
k = 1;  % column index; select using data.profile.timestamp_utc
mpc = npcc_ny_lite_s11_dlr_pf_base;
[mpc, hour] = apply_s11_hourly_load_profile(mpc, data.profile, k);
disp(hour);
```

Loading and applying the data do not require MATPOWER. The helper changes only
Pd/Qd and matches buses by ID, so reordered case rows are supported. Reading,
applying, and rebuilding were tested with MATLAB R2026a. Other versions were
not tested. AC PF validation additionally requires MATPOWER on the MATLAB path;
MATLAB and MATPOWER themselves are not bundled.

## Verify or reproduce

The original relative folder layout is retained so these commands work from
the extracted package root, independently of the original checkout.

Independent source-to-output check (Python with NumPy and SciPy):

```text
python scripts/s11_hourly_load_profiles/verify_s11_hourly_load_profiles.py
```

Rebuild and check bus-ID application in MATLAB:

```matlab
addpath('scripts/s11_hourly_load_profiles');
build_s11_hourly_load_profiles;
test_apply_s11_hourly_load_profile;
```

Optional retained-peak AC replay with MATPOWER installed:

```matlab
validate_s11_hourly_load_profile_integration;
```

The saved validation JSON files describe the delivered dataset. If you rebuild,
rerun the independent Python check and any required AC replay. The Python check
prints its new results to the terminal; it does not overwrite the saved JSON.

`PACKAGE_MANIFEST.json` identifies the source dataset commit and inventory.
`PACKAGE_CONTENTS.csv` lists the included payload files. All data needed to read,
apply, regenerate, and independently reconcile these profiles are included.
No repository clone or source download is required for those operations.
"""


def payload_paths() -> list[Path]:
    files = sorted((ROOT / DATA).iterdir())
    if not all(path.is_file() for path in files):
        raise ValueError("Unexpected subdirectory in profile output")
    relative = [path.relative_to(ROOT) for path in files]
    relative.append(Path("System Matpower Format/npcc_ny_lite_s11_dlr_pf_base.m"))
    helper = Path("System Matpower Format/NY_Lite")
    relative.extend(helper / name for name in (
        "apply_s11_hourly_load_profile.m", "attach_nyiso_zone_metadata.m",
        "nyiso_bus_zone_map.m", "nyiso_zone_metadata.m", "nyiso_zone_index.m",
        "s11_bus_geography.csv",
    ))
    relative.extend(Path("scripts/s11_hourly_load_profiles") / name for name in (
        "build_s11_hourly_load_profiles.m", "test_apply_s11_hourly_load_profile.m",
        "validate_s11_hourly_load_profile_integration.m",
        "verify_s11_hourly_load_profiles.py", "package_s11_hourly_load_profiles.py",
    ))
    with (ROOT / DATA / "source_manifest.csv").open(encoding="utf-8-sig", newline="") as handle:
        sources = [Path(row["source_file"]) for row in csv.DictReader(handle)]
    if len(sources) != 184:
        raise ValueError("Expected exactly 184 raw daily inputs")
    relative.extend(sources)
    if len(set(relative)) != len(relative):
        raise ValueError("Duplicate package member")
    for path in relative:
        resolved = (ROOT / path).resolve()
        if path.is_absolute() or not resolved.is_relative_to(ROOT) or not resolved.is_file():
            raise ValueError(f"Invalid payload path: {path}")
    return sorted(relative)


def main() -> None:
    files = payload_paths()
    dataset_commit = subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", str(DATA)], cwd=ROOT, text=True
    ).strip()
    manifest = {
        "package": PACKAGE,
        "source_dataset_commit": dataset_commit,
        "bus_count": 49,
        "hour_count": 4416,
        "months": ["201901", "201904", "201907", "202501", "202504", "202507"],
        "raw_daily_source_files": 184,
        "payload_file_count": len(files),
        "payload_bytes": sum((ROOT / path).stat().st_size for path in files),
        "full_year_coverage": False,
        "all_hours_power_flow_validated": False,
        "profile_paths": {
            "active_csv": (DATA / "pd_mw.csv").as_posix(),
            "reactive_csv": (DATA / "qd_mvar.csv").as_posix(),
            "matlab": (DATA / "s11_hourly_load_profiles.mat").as_posix(),
        },
    }
    inventory = io.StringIO(newline="")
    writer = csv.writer(inventory, lineterminator="\n")
    writer.writerow(["relative_path", "bytes"])
    writer.writerows((path.as_posix(), (ROOT / path).stat().st_size) for path in files)
    DEST.mkdir(parents=True, exist_ok=True)
    archive = DEST / f"{PACKAGE}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in files:
            z.write(ROOT / path, f"{PACKAGE}/{path.as_posix()}")
        z.writestr(f"{PACKAGE}/README.md", GUIDE)
        z.writestr(f"{PACKAGE}/PACKAGE_MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
        z.writestr(f"{PACKAGE}/PACKAGE_CONTENTS.csv", inventory.getvalue())
    with zipfile.ZipFile(archive) as z:
        bad = z.testzip()
        if bad:
            raise ValueError(f"Archive CRC check failed: {bad}")
        if len(z.namelist()) != len(files) + 3:
            raise ValueError("Archive member count mismatch")
        for path in files:
            if z.read(f"{PACKAGE}/{path.as_posix()}") != (ROOT / path).read_bytes():
                raise ValueError(f"Archive payload mismatch: {path}")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    receipt = {
        **manifest, "zip_file": archive.name, "zip_bytes": archive.stat().st_size,
        "zip_sha256": digest, "archive_file_count": len(files) + 3,
        "zip_crc_and_payload_equality_passed": True,
    }
    (DEST / "README.md").write_text(GUIDE, encoding="utf-8", newline="\n")
    (DEST / "package_receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
