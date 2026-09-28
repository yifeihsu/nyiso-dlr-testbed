# Delivery checks

Completed September 8, 2026.

- 8-page, 16:9 PDF compiled with TeX Live 2024 / pdfTeX 1.40.26, condensed from the 24-slide deck.
- The final build reports no overfull boxes, underfull boxes, or LaTeX warnings.
- The annual comparison chart retains vector text and geometry; data tables and the connectivity diagram remain editable in LaTeX.
- All eight pages were rasterized and visually inspected for clipping, overlap, and readability.
- Independent content review rechecked annual and selected-hour table values and the essential model, metric, experiment and validation boundaries. No scientific values were changed when shortening the deck.
- All upstream chart-source hashes and chart-output hashes match their supplied manifests.
- The source ZIP was extracted into a separate folder and compiled twice without repository dependencies. Its eight extracted page texts match the delivered PDF exactly. Regenerating charts is optional and requires the frozen repository outputs; compiling the included vector charts does not.
- No scientific studies, model cases, input datasets, or frozen experiment outputs were rerun or edited for this deck.

Scientific evidence is pinned to project commit `c472e250753b441223d8c6e029aa86e6dd56db8e`. These presentation checks verify the deck and its traceability; they add no new electrical-model validation.
