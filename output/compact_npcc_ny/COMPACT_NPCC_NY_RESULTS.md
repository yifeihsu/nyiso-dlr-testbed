# Compact NPCC NY benchmark results

The preferred preliminary electrical testbed contains **51 NY buses**, including all **46 original NPCC NY buses**, under a hard **200-bus ceiling**. It has **87 active branches** (92 records), **35 aggregate generator records**, and **10 fixed boundary injections**.

Electrical baseline qualified under declared benchmark assumptions: **true**. Contemporary validation: **not claimed**. DLR ready: **false**.

| Matched benchmark quantity | Value |
| --- | ---: |
| Gross NY load | 10902.219799 MW |
| Net boundary P (positive into NY) | -1424.445909 MW |
| Net boundary Q | -602.494888 MVAr |
| NY aggregate generation | 12863.375828 MW |
| Internal branch losses | 536.710120 MW |
| Shunt losses | 0.000000 MW |

The negative boundary P is a net export in this reconstructed NPCC benchmark. Each boundary uses the negative of the removed tie's solved NY-terminal flow, preserving its delivered-power sign and NY-side charging contribution. Gross demand and boundary injections are separately registered; effective demand subtracts each boundary injection once. This fixed P/Q representation reproduces one matched state, not external voltage or contingency response.

All 91 implementation assertion groups and 12 acceptance gates pass. A fresh NY power flow has maximum nodal residuals 7.16e-12 MW and 2.72e-11 MVAr, matched complex-voltage error 2.48e-16 pu, and active-dispatch adjustment 4.55e-13 MW. Voltage, both-terminal static ratings, angle limits and every declared generator P/Q envelope pass the physical audit.

The primary reconstruction uses MIPS start 0 with a generator-prior objective and unchanged hardware, loads, shunts, ratings and capability bounds. 4 of 4 solver/start attempts pass bounded audit and independent full-network replay. Full-NPCC generation moves 12460.545 MW in total absolute terms from inherited priors: this is a reconstructed benchmark dispatch, not an observed historical operating snapshot. Every attempted result is retained in the operating evidence.

The 35 NY generator records comprise 21 original NPCC identities with inherited S7/S4 aggregate envelopes and 14 S4 P-only equivalents. Broad Q limits (including +/-999 and +/-9999 MVAr) are declared benchmark assumptions, not verified physical plant capability. No new generator or relaxed limit is introduced.

Eleven source AC circuit records refine Pleasant Valley/East Fishkill/Wood Street/Millwood and Ramapo/Ladentown/Buchanan. Five overlapping parent records (88,89,94,235,236) are inactive. The two S7 parallel aggregates 235/236 are exact electrical replacements; the original NPCC corridor retirements are declared functional substitutions with response changes, not exact response-equivalent reductions. Source-device exclusions and omitted incident source connections remain explicit.

`compact_electrical_asset_register.csv` records terminal RMS model currents and electrical provenance. Overhead/cable/conductor realization remains unverified and all thermal eligibility is false. Inherited equivalent currents do not represent individual physical conductors. The 878-bus Package B case remains an optional historical reference.

Rebuild: `run_compact_npcc_ny_testbed`. Independently verify the frozen input without optimization: `replay_compact_npcc_ny_testbed`. Load the frozen NY case: `npcc_ny_compact_dlr_testbed`.
