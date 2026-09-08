# NYgrid interface-flow project update

24-slide LaTeX Beamer deck: 19 main slides and five appendix slides. Prepared September 8, 2026.

Open `nygrid_interface_update.pdf` to present. Edit `nygrid_interface_update.tex` for narrative, tables, and the native TikZ connectivity diagram. The four scientific charts are vector PDFs in `figures/`, with editable data in `data/`.

## Scope and main result

The deck covers the released 2019 NYgrid DC reproduction, the correction to five interface measurement formulas, and matched-2019 experiments on the historical 51-bus compact network. Adding the paper-derived Marcy branch hypothesis reduces annual pooled actual-flow WAPE from 17.38% to 12.32%, with Central East improving and UPNY–ConEd worsening. Three retrospective minimax snapshots have worst-interface errors of 4.85%, 5.31%, and 5.59%.

The 71-bus year-end 2025 model is unchanged. The new experiment performs no shared-parameter fitting or per-hour interface-target fitting and has no untouched holdout. The compact ancestry retains older S4/S7 calibration history. A separate three-hour bounded AC checkpoint uses the compact network without the Marcy additions; it does not qualify the selected Marcy DC hours for AC or DLR studies.

## Build the presentation

Extract the source ZIP, preserve its directory structure, and run these two commands from the directory containing the main `.tex` file:

```text
pdflatex -interaction=nonstopmode -halt-on-error nygrid_interface_update.tex
pdflatex -interaction=nonstopmode -halt-on-error nygrid_interface_update.tex
```

Or use `latexmk -pdf nygrid_interface_update.tex`. Tested with TeX Live 2024 / pdfTeX 1.40.26. The included style uses standard Beamer, Latin Modern, TikZ, pgfplots, booktabs, tabularx, amsmath, and hyperref packages. No shell escape or Python is needed to compile the slides. The source bundle includes the vector chart PDFs required by LaTeX.

## Data and figure provenance

Scientific evidence is frozen at repository commit `c472e250753b441223d8c6e029aa86e6dd56db8e`. No studies were rerun or modified to create the deck.

- `NYGRID_2019_INTERFACE_VERIFICATION.md` and `output/nygrid_2019/` provide the NYgrid reproduction.
- `NYGRID_COMPACT_2019_COMPARISON.md` and `output/nygrid_compact_2019/` provide the compact experiments and separate AC checkpoint.
- `data/source_hash_manifest.csv` pins the chart's upstream evidence and generation script; `data/figure_output_manifest.csv` pins its chart/data outputs.
- `data/README.md` explains denominators, scaling, role operators, and retrospective selection.
- `CONTENT_AUDIT.md` is the independent evidence/narrative review; `VALIDATION.md` records the delivered slide checks.

To regenerate figures from the original frozen study outputs, place this directory at its repository path `output/pdf/nygrid_interface_update_2026-09-08/` and run `python figures/build_figures.py`. This optional step requires the full repository outputs and NumPy, pandas, matplotlib, and Pillow. It is unnecessary for standalone LaTeX compilation. Editable CSVs also support independent chart recreation.

All selected-hour dates are 2019 New York local time. Chart 4 displays actual-scale GW by dividing compact values by the single study power scale; AC loss values on slide 18 are benchmark MW. Annual WAPE compares seven overlapping interfaces and is not a statewide energy-balance metric.

## Reading route

- Slides 1–8: model identity, NYgrid methodology, measurement correction, annual and selected-hour results.
- Slides 9–17: matched experimental design, role crosswalks, Marcy hypothesis, annual/monthly/ablation results and compact snapshots.
- Slides 18–19: separate AC checkpoint and next calibration priorities.
- Slides 20–24: source/time quality, development matrix, selection criteria, physical limitations and linked references.
