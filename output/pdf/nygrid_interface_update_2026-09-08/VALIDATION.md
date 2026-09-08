# Delivery checks

Completed September 8, 2026.

- 24-page, 16:9 PDF compiled with TeX Live 2024 / pdfTeX 1.40.26.
- The final build reports no overfull boxes, underfull boxes, or LaTeX warnings.
- All fonts are embedded; four scientific chart PDFs retain vector text and geometry.
- All 24 pages were rasterized and visually inspected. Dense pages received individual full-size checks. The Marcy labels and allocation-table spacing were corrected and independently rechecked.
- Independent content review checked model identities, annual metrics, all 30 development-matrix entries, ablation counts, selected-hour rankings, role/operator scope and AC values against saved study evidence. Generation-residual wording, hydro time scales, matrix rounding and benchmark-MW labels were corrected.
- All upstream chart-source hashes and chart-output hashes match their supplied manifests.
- The source ZIP was extracted into a separate folder and compiled twice without repository dependencies. Its 24 extracted page texts match the delivered PDF exactly. Regenerating charts is optional and requires the frozen repository outputs; compiling the included vector charts does not.
- No scientific studies, model cases, input datasets, or frozen experiment outputs were rerun or edited for this deck.

Scientific evidence is pinned to project commit `c472e250753b441223d8c6e029aa86e6dd56db8e`. These presentation checks verify the deck and its traceability; they add no new electrical-model validation.
