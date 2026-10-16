# Weekly report: downstate refinement and 2025 operating inputs

This 16-slide Beamer deck follows the supplied Madrid/beaver 16:9 template:
13 main slides, including the cover, followed by three backup slides.
The report date and evidence snapshot are October 15, 2026; final preparation
continued after midnight. The template's previous subject content is excluded.

## Files

- main.pdf: presentation-ready PDF.
- main.tex: editable deck, including native tables and PGFPlots charts.
- figures/downstate_comparison.tex: editable, source-derived TikZ diagram.
- data/ and figures/data/: exact chart values and represented topology.
- presenter_notes.md: speaking notes, qualifications and source pointers.
- source_manifest.json: research snapshot and source/data SHA-256 hashes.
- validation.json: final build, geometry and source consistency checks.
- evidence/: independent content and provenance reviews.

The source ZIP can be uploaded to Overleaf or extracted into a local folder.
Set main.tex as the main document and use pdfLaTeX. No external images,
shell escape, Python or MATLAB are required to compile the deck.

~~~powershell
pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error main.tex
pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error main.tex
~~~

The bundled data make the presentation independently compilable. Source paths
in the manifest are relative to the research repository; complete annual
hourly model outputs are not duplicated in this small presentation package.
The deck source and editable charts do not rerun the research model.

## Interpretation

The latest completed annual replay is moses_repair_v1 at research commit
0e73b46fed7d9e859d7f1683be019b169270d095. The deck was checked against saved
annual and post-repair evidence. No new annual AC run was launched for slides.

The seven interface metrics use one common 8,651-hour cohort, public MW and
the frozen signed-from diagnostic operator. Physical P32 meter equivalence
remains uncertified. All eligible hours pass equation, loss and recovery
checks, but zero pass every declared operating limit.

The topology diagram is a selected connectivity schematic, not surveyed
geography. Station voltage ports and parallel circuits are combined only for
display; data files preserve source IDs. Added model detail includes historical
assets absent from the frozen aggregate network and dated project states.
It does not mean every depicted addition was constructed after 2019.

Absolute and relative errors are separate. Total East has the largest MAE;
West Central has the largest WAPE. Confirmed input inconsistencies,
within-model ablation effects and unresolved physical causes are distinguished.

Slide 9 adds the October 16 comparison of the reproduced released 2019 DC
benchmark with the current 2025 AC model. It reports MAE and WAPE changes and
changes in mean absolute NYISO-reported flow. The 2019 scores use the authors'
supplied interface map, rather than the plotting helper's stale indices.
These are recomputed scores, not values quoted from the paper's Figure 5.
The periods, operating inputs, physics, prepared observations and diagnostic
operators differ; the comparison does not isolate a topology effect.

## Repository regeneration

From the repository root:

~~~powershell
python scripts/nygrid_weekly_20261015/prepare_slide_data.py
python scripts/nygrid_weekly_20261015/build_2019_comparison_evidence.py
python scripts/nygrid_weekly_20261015/add_comparison_slide.py
~~~

Figure generation uses scripts/nygrid_weekly_20261015/build_downstate_figure.py.
Final build and packaging use scripts/nygrid_weekly_20261015/finalize_deck.py.
The preserved report snapshot must be deliberately updated when refreshing to
a later research version; compiling alone changes no source data.
