# Figure data and claim boundaries

All graphics use frozen CSVs from the completed studies. No model or operating input is changed or fitted here.

WAPE = 100 sum(abs(modeled - observed)) / sum(abs(observed)). The annual result has 8,760 timezone-naive local-hour labels; each individual interface has 8,760 comparisons. Pooled results contain 61,320 comparisons of seven overlapping interfaces. Primary annual figures retain source interpolation and DST treatment; no quality-filtered selection is substituted.

The NYgrid reference uses corrected released if.map operators, not the erroneous literal plotting-row selection. Comparison figures use the same paper allocation roles for all networks and the same scaled NYgrid native solved generation, net demand, and fixed model-derived AC/DC/HQ NY boundary injections. The Marcy diagnostic adds the paper's two reactances to the compact DC network. It does not establish physical upgrade disposition, AC feasibility, line ratings, or DLR validity.

The compact network uses fixed gamma 0.358662225381536 for every load, generation, boundary injection and observed comparison. WAPE is scale invariant. The selected-flow figure divides scaled compact values by gamma so both panels use actual-scale GW. That display conversion does not turn the compact network into an actual-MW model.

January 8 15:00 is the NYgrid best pooled hour; July 3 04:00 is the compact + Marcy best minimax hour. Both were selected retrospectively from already examined annual data. They are not held-out validation. All seven interfaces at those hours have 12 unique raw samples, no imputation and no ambiguous DST flag.

The current physical-zone operator sensitivity is intentionally not mixed into these three paper-role series. Its annual pooled WAPE worsens from 19.07209610% to 19.67048524% with the same Marcy change; a differently defined interface cut can produce a different comparison.

The two annual figures are deliberately both bar charts: the first reports one model across seven interfaces; the second compares three models within each interface. The monthly series uses all 12 months. The paired-point panels label all seven discrete interfaces and use equal 0–5.2 GW scales, instead of treating seven points as an unlabeled statistical scatter sample.

CSV tables retain precision from source files and contextual fields. Figure and LaTeX table display values are rounded only for legibility. Numeric interface_index/month/panel fields support native pgfplots without parsing labels. All TeX tables are input-ready tabular fragments requiring booktabs. No image-based table is used.
