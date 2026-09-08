# NY-only Package B regional candidate

Electrical baseline qualified: **true**, for one assumed 2019 NPCC/PERFORM regional candidate. Contemporary coverage and DLR readiness remain false.

The connected source region covers D-K: 855 source buses plus 23 retained NPCC A-C buses, 1375 total branches and 595 generator records. Of the generator records,594 are native source records and one is the separately bounded Marcy Q-only research support inherited from Package A.

Row235 is an exact duplicate of the two Pleasant Valley-Wood Street physical parallel records and is retired first. The regional package then retires every inherited D-K incident branch, all old NY injections and all old NY generators before transferring source devices once. Other retired paths are functional replacements with assumed correspondence; the historical parent remains an explicit alternative. No nonpassive residual is fitted.

Common-terminal source/candidate complex power error: 0 MVA; current error: 0 kA. These local device checks do not establish retained A-C aggregation response identity. Aggregated A-C load and controls, including the C-E cut mapping, remain declared research assumptions.

| Quantity | Value |
|---|---:|
Gross demand | 29799.660000 MW |
Fixed net boundary injection | 1292.635022 MW |
Native generation | 29083.765450 MW |
Losses | 576.740472 MW |
Balance error | 3.08773451e-10 MW |
Native P movement from Package A | 0.001429 MW |
Native Q movement from Package A | 2400.724194 MVAr |
Marcy support P | 0 MW |
Marcy support Q | -649.599563 MVAr |
Maximum replay P adjustment | 4.05730228e-05 MW |
Maximum replay V adjustment | 3.21410232e-10 pu |

Default reconstruction uses MATPOWER MIPS with its interior initialization (opf.start=0), quadratic native P-prior deviations and fixed hardware, schedules and capability bounds. PV targets, voltage magnitudes and native reactive outputs may move within the declared envelopes. No load shedding, fictitious P, constraint relaxation, boundary schedule movement or interface target fit is used. Independent PF maximum nodal mismatches: 1.15466747e-09 MW / 2.4563036e-09 MVAr.

Separate source-response tables compare each independently solved operating point at its own voltages. They quantify voltage and both-terminal P/Q/current differences, without an acceptance threshold. A bounded electrical baseline does not establish exact source response; broader response qualification remains Package D work.

Smaller G-K and D+G-K variants are reproducibly attempted and retained in operating_attempts.csv and alternatives/. Their failed numerical solves are not proofs of global infeasibility. D-K removes the collapsed E/F ports and the weak aggregated Plattsburgh pocket without altering source limits. Additional exploratory warm-start and IPOPT runs informed this choice; they do not supply the accepted artifact.

Reproduce with `run_ny_only_regional_candidate`; replay the hash-verified saved input with `replay_ny_only_regional_candidate`. Load the frozen case with `npcc_ny_lite_s14_ny_only_regional_candidate`. The runner records all default attempted variants. Fast run_operating=false implementation checks never qualify an operating point.

The canonical source conversion retains its known RAW control and circuit-identity ambiguities. Physical parameters and voltage bases are copied; overhead/cable classification, contemporary plant status, thermal eligibility and held-out response accuracy are not established. Package A and historical NPCC/S7/S13 artifacts remain preserved.
