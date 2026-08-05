# Fixes applied in this rebuild

- Corrected Perform codes: H/MILLWD = 73 and I/DUNWOD = 72.
- Corrected physical mapping: CE UG = I, GOETHALS = J, NORTHPORT = K.
- Added `physical_zone`, `load_allocation_group`, and `perform_zone_code` metadata.
- Removed mixed MW/share targets from the S0 zonal-load scenario.
- Added exact baseline-Q invariance and signed Q/P preservation.
- Added explicit, idempotent equivalent E/G/H generator scaffolding with PQ/PV control modes.
- Added generator-redispatch and balanced-injection interchange modes; no implicit default method.
- Added external reference-bus selection and explicit balancing-pool dispatch.
- Added generator-limit repair helper.
- Added structural and operating-point fingerprints.
- Reduced the default topology to only the direct Perform Gilboa-Leeds analog.
- Preserved Gilboa-Leeds RATE_A/RATE_B/RATE_C = 1216/2454/1804 MVA.
- Added PF/PT source-end interface metering and aggregate ConEd-LIPA schema.
- Guarded `npcc_ny_lite_v3_calibrated.m` until real calibration is completed.
