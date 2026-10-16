# Corrected model delivery pipeline

This directory owns the versioned portable model, current structure manual and
offline map for the frozen physical repair. It preserves the original latest
runtime/model and all 21 pre-existing dirty map files. The recovery receipts are
under `output/nygrid_2025_physical_repair/delivery/preservation`.

`export_repaired_model.m` requires the passed frozen candidate receipt. It
constructs each dated baseline case, applies the frozen repair exactly once,
removes transient loader/vendor handles, retains complete physical-repair and
full-axis shunt metadata, updates parent 41 registry provenance, and copies both
profile shards byte-for-byte. Existing static exports are not overwritten.

`runtime/` is the prior sealed public runtime with the authoring path resolver
changed to this versioned model. Numerical kernels are unchanged. The public
names remain `setup_nygrid_latest`, `load_nygrid_latest`,
`run_nygrid_latest_acpf`, `screen_nygrid_latest_dlr` and `smoke_nygrid_latest`.
The four-state authoring comparison and fresh cold smoke provide separate
receipts in the versioned delivery validation directory.

The map builders read the completed replay selected by
`NYGRID_REPAIR_RUN_LABEL` (default `physical_repair_v1`). They require the
matching annual, scoring, candidate and compiled model receipts. Their order is:

1. `export_current_structure.m`, then `build_current_structure.py`.
2. `map/build_geography_data.py` and `map/build_interface_definitions.py`.
3. `map/export_annual_data.py`, then the separate annual/geography readbacks.
4. `map/build_network_map.py`, JS helper and actual-DOM checks, embedded-payload
   readback, and a separate native-browser review.
5. `build_delivery_docs.py` and `build_structure_document.py`; render the Word
   document, inspect every page, and bind the visual/content receipts.
6. Independent compiled-model/map/manual review, `finalize_delivery.py seal-map`,
   and `build_package.py --label final`.
7. `check_portable_package.py prepare`, fresh MATLAB execution of its recorded
   batch command from the OS-temp extraction, then `check_portable_package.py finish`.
8. `finalize_delivery.py promote` updates the explicit current-package pointer
   and map HTML alias only after all gates pass.

The data builders require NumPy, SciPy and pandas; geographic projection also
uses pyproj. Document authoring uses the Codex bundled Python with python-docx.
The package verifier needs only standard-library Python. Native MATLAB R2026a,
MATPOWER 8.1, Microsoft Word PDF export and Poppler were used for the recorded
runtime and document checks. Word was used because the canonical packaged
renderer could not find LibreOffice.

The two `prepare_*_sources.py` scripts and `prepare_document_builder.py` are
one-time guarded source preparation records. They are not normal rebuild
commands and refuse to overwrite subsequent reviewed work. Existing historical
source files and sealed numerical bundles must remain available for reproducing
their earlier receipts.
