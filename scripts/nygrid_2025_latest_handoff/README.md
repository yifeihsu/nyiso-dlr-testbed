# Latest model package construction

This namespace produces a single current-model handoff. The colleague package
has `runtime`, `model`, `vendor`, `examples`, and `verification` directories,
plus the structure document, data dictionary, instructions and integrity files.
It does not contain earlier model families or archived experiment corpora.

The authoring exporter reads the frozen research checkout once and compiles
current templates, static interpretation data and exact annual profile arrays.
The packaged loader reads only this compiled input. Half-year MAT files keep
individual files within ordinary repository file-size limits without changing
numeric type or precision. The runtime retains the default compact coupled
loss solve and current conductor-screen equations, with renamed functions and
explicit input/path adapters. It provides no historical model selector.

`build_latest_runtime.py` records source-to-kernel adaptations.
`export_nygrid_latest_model.m` constructs the compiled data.
`export_current_structure.m` and `build_current_structure.py` create the
current structural ledgers and independent admittance checks. The runtime
validation compares complete input arrays and selected current model solutions;
it is not a new annual PF or OPF study.

`build_structure_document.py` authors the separate structure-only DOCX and MD.
The DOCX is rendered, visually inspected, and bound by its review receipts.
`build_package.py --label final` copies an explicit current-file allowlist,
retains vendor licenses, writes a manifest/checksum table, and verifies every
archive member. It refuses to overwrite retained archive or staging paths.
Use a new label for a new build. `verify_package.py` is standalone and needs
only Python's standard library.

The final archive is independently extracted outside the repository and run
with only its own runtime and vendor paths. The delivery manifest binds the
current code, compiled data, document and validation receipts while checking
that earlier deliveries remain byte-preserved. Large ZIP/staging duplicates and
internal document-render intermediates are ignored; model inputs and the
inspectable build/validation evidence are versioned.
