# NYgrid interface-flow project update

8-slide LaTeX Beamer deck, condensed from the original 24-slide version at the user's request. Updated September 8, 2026.

Open `nygrid_interface_update.pdf` to present. Edit `nygrid_interface_update.tex` for narrative, tables, and the native TikZ connectivity diagram. The annual comparison chart is a vector PDF in `figures/`, with editable data in `data/`. Additional figures from the longer version remain available in the source bundle.

## Scope and main result

The deck covers the released 2019 NYgrid DC reproduction, the measurement correction, and matched-2019 experiments on the historical 51-bus compact network. Annual pooled actual-flow WAPE falls from 17.38% to 12.32%, with Central East improving and UPNY–ConEd worsening. A seven-interface table compares the best NYgrid and compact minimax examples at their respective selected hours.

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

All selected-hour dates are 2019 New York local time. Annual MAE is actual-scale MW. WAPE compares seven overlapping interfaces and is not a statewide energy-balance metric.

## Reading route

- 1: Title.
- 2: Model scope and error metric.
- 3: NYgrid annual performance and measurement correction.
- 4: How the experiment adapts the paper's method.
- 5: Annual compact-model improvement and UPNY tradeoff.
- 6: Selected-hour errors for every interface.
- 7: Remaining gaps and next steps.
- 8: Linked references with the detailed evidence.

The previous 24-slide deck is retained in Git history at commit `e0b079e`.
