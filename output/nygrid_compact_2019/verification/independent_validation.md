# Independent 2019 comparison verification

PASS: 188 numerical/provenance checks cover all 8,760 annual hours, all 30 matched network/input rows, all 25 source-derived allocation ablations, and all six selected candidates.

The independent Python replay builds its own DC nodal matrix, tap and phase-shift injections; it does not call the comparison DC solver. A second replay uses MATPOWER rundcpf on all six selected candidates with signed nodal demand and one numerical reference generator. No AC or thermal qualification follows.

July 3, 2019 04:00 is the best minimax hour for compact51 + the two Marcy reactances under paper roles: pooled error 3.27872892%, worst-interface error 4.85182860%, and no opposite-direction interfaces.

| timestamp           | interface     |   observed_actual_mw |   predicted_actual_scale_mw |   absolute_error_pct | wrong_direction   |
|:--------------------|:--------------|---------------------:|----------------------------:|---------------------:|:------------------|
| 2019-07-03 04:00:00 | Dysinger East |           857.380000 |                  844.825260 |             1.464315 | False             |
| 2019-07-03 04:00:00 | West Central  |           497.037500 |                  504.407091 |             1.482703 | False             |
| 2019-07-03 04:00:00 | Total East    |          4110.180000 |                 4234.160513 |             3.016425 | False             |
| 2019-07-03 04:00:00 | Moses South   |          1935.280000 |                 2029.176469 |             4.851829 | False             |
| 2019-07-03 04:00:00 | Central East  |          2132.804167 |                 2042.696116 |             4.224863 | False             |
| 2019-07-03 04:00:00 | UpNY-Coned    |          2833.574167 |                 2939.876021 |             3.751511 | False             |
| 2019-07-03 04:00:00 | Dun/SPR-South |          3468.361667 |                 3553.324632 |             2.449657 | False             |

Top-three pooled hours: September 6 02:00 (1.77323734%), September 8 05:00 (1.95163634%), September 6 03:00 (2.17022055%). The minimax criterion instead selects July 3 04:00, July 22 04:00, and September 8 05:00.

Annual pooled error with paper roles falls from 17.38250825% to 12.31721500%, with improvement in all 12 monthly pooled scores. The paper reference remains 11.21807693%. With current physical-zone roles the same network change instead increases annual pooled error from 19.07209610% to 19.67048524%; operator roles therefore must stay explicit.

MATPOWER maximum selected branch discrepancy: 2.12e-12 MW; maximum selected interface discrepancy: 2.96e-12 MW. All 94 branch records retain exact hardware and ordering.

Source-array equality is checked against the separately exported annual reference NPZ, including pre-solve generation, solved generation/slack, net demand, and separate AC/DC/HQ boundary accounts. Source and construction hashes match their pinned manifests. All selected best-hour quality flags are independently joined to the primary-source reconstruction quality table. The detailed CSV retains irregular-sample cases rather than silently excluding them.

## Interpretation boundaries

- The seven scored interfaces overlap; pooled WAPE is a pooled comparison error, not independent statewide energy error.
- All rankings are retrospective selections from 8760 already examined hours; there is no untouched holdout.
- Paper allocation roles and compact physical-zone roles define different measurement operators; matching names do not prove identical physical membership.
- Kron bus9003 maps one-half to78 and one-half to80 as exact DC injection equivalence conditioned on compact topology, not measured generation or a physical site crosswalk.
- The load-placement ablation changes the zonal role crosswalk and within-zone weights jointly; hydro combines current zonal priors with generic capacity weighting.
- NYgrid native solved generation includes source slack; fixed NY boundary injections are model-derived, not measured individual tie telemetry.
- The Marcy variant adds two source reactances for DC diagnosis; its AC resistance/charging/ratings and upgrade disposition are not established.
- Source-hour quality pertains to interface sampling, not independently observed nodal generation.
- Paper-style signed errors use placeholder limit values for some channels and are not physical thermal-rating error measures.

## Evidence

- `independent_validation.json`: machine-readable findings and all selected quality/replay records.
- `independent_validation_gates.csv` and `independent_validation_source_hashes.csv`: tolerances and source pins.
- `selected_hour_source_quality.csv` and `selected_interface_source_quality.csv`: direct primary-source quality joins.
- `independent_selected_interface_metrics.csv` and `independent_monthly_improvements.csv`: independently calculated metrics.
- `matpower_selected_dc_replay.csv`: separate solver replay without a physical-generation claim.
