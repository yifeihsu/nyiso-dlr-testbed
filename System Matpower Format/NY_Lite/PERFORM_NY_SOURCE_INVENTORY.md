# Original PERFORM NY source inventory

Package A uses `normalize_perform_ny_source` to inventory the original NY electrical case without modifying it. `perform_ny_source_manifest.csv` pins four source files by SHA-256 after CRLF/CR-to-LF normalization. The canonical electrical source is `PERFORM/On Peak 2019 v23_Perform_NY/On Peak 2019 v23/nyiso_On_Peak_v23_shunts_as_z_load.m`. Its complete MATPOWER structure, including extra columns, is returned as `n.source`.

This is the **2019 PERFORM model at its original actual-MW scale**. The associated RAW export date is September 19, 2022. Neither date makes its bus loads, generator dispatch, boundary exchange, or control targets contemporary observations. Inventory validation establishes coverage and accounting; it does not qualify an operating point.

| Inventory | Source treatment |
| --- | --- |
| 1,576 buses | Original numeric IDs, names, voltage levels, NY zones A–K, gross PD/QD, GS/BS, voltage limits, and combined electrical roles |
| 2,371 branches | 2,227 AC elements of unresolved line/cable/equivalent type and 144 two-winding transformers; original parameters, ratings, tap, shift, and status retained |
| 615 generator records | 576 native generation, 16 pumped storage, 2 other storage, 20 external exchange proxies, and 1 reference placeholder |
| 34 shunt records | Switched-shunt BINIT frozen in canonical bus BS; 20 have nonzero BS, totaling 1,035.9 MVAr at 1 pu |
| 793 control records | 615 generator controls, 144 fixed transformer taps, and 34 shunt controls disabled in the static canonical representation |

Generator classification uses the canonical fuel/type metadata, checked against the 615-row generator metadata CSV, and matched to RAW by bus plus unit ID. The RAW contains 649 generator records: its other 34 `QS` records are the alternative shunt representation. `shunt_alias_inventory` joins each `QS` identity to its canonical bus shunt. These devices must never be copied into both generator and bus-shunt representations.

## Identity and unresolved records

Bus keys use original source IDs. Generator keys use `PERFORM2019:GEN:<bus>:<RAW unit ID>`. Branch keys use family, endpoint IDs, and RAW circuit ID. Source row numbers remain lookup pointers alongside these keys. `source_to_model_mapping` covers buses, branches, and canonical generators; the shunt-alias and control inventories supply the corresponding representation/device links.

The canonical branch table lacks circuit IDs. Matching it to RAW by endpoints and electrical values leaves **287 canonical branch rows with electrically identical parallel candidates**. All parallel elements are preserved; deterministic one-to-one assignments provide normalized keys for the pinned source. The candidate set and `individual_circuit_identity_resolved=false` explicitly limit those assignments: they do not establish which physical circuit is which. No branch is classified as overhead or eligible for thermal modeling solely from its voltage or electrical parameters.

The unique transformer identity between source buses 1137 and 1169, circuit `EQ` (canonical branch row 2013), has a 0.00107 pu charging-B difference between RAW conversion and canonical MATPOWER. The inventory preserves the canonical value and records the discrepancy; RAW supplies identity metadata, not a parameter overwrite.

One RAW generator, `PERFORM2019:GEN:138:1`, requests remote voltage regulation at bus 1296. Canonical MATPOWER regulates its local terminal, bus 138. The generator inventory retains the RAW target in `regulated_bus`, records `canonical_regulated_bus=138`, and flags `raw_remote_control_omitted=true`. The control inventory's `regulated_bus` is the canonical target; its separate `raw_regulated_bus` is the original intended target. This limitation is in the unresolved-record report. Automatic transformer tap/phase regulation and switched-shunt logic are not inferred from fixed canonical values.

## Why 21 source records became 19 historical schedule rows

The source has **20 external exchange proxies and one Marcy reference placeholder**. Fourteen exchange proxies are online in the canonical case; six are offline despite being online in RAW. Stored nonzero PG/QG on those six offline records has zero effective injection. Canonical status governs; normalization never reactivates them.

The old `s12_external_boundary_groups.csv` contains 19 exchange rows. Its missing exchange identity is **bus 69, unit X**, canonical generator row 74. The S12 construction's fixed-P heuristic omitted this variable-P proxy when it shared a bus with another generator. Its canonical status is offline. The new reconciliation retains it explicitly in the PJM AC schedule group with zero canonical effective injection.

The other source record absent from the old schedule map is **bus 1263, unit RF**, canonical generator row 537. It is a reference placeholder, not an external schedule. Its stored P is -0.070196 MW, stored Q is -721.10734 MVAr, active limits are -1 to 1 MW, and reactive limits are ±9,900 MVAr. It cannot become native generation or unlimited reactive support. Package A removes its generator record with no fixed external injection; any replacement bounded reactive support is a separately declared assumption owned by the operating-reference builder.

`boundary_reconciliation` stores source P/Q and status-adjusted effective values for all 21 original records. Its `boundary_member=false` for RF is essential: that row's source-state effective Q is **not** an instruction to inject it into the new operating case. `build_ny_boundary_register` implements the separate removal policy. Schedule groups are reused as source mapping labels; they are not new measured exchange observations.

All 15 source generator records with ±9,900 MVAr bounds are the 14 active external proxies plus RF. No native generator has such placeholder bounds. Their role and treatment remain explicit in the unresolved-record report.

## Reproduction and gates

```matlab
addpath('System Matpower Format/NY_Lite');
n = normalize_perform_ny_source(struct('write_outputs', true));
test_result = test_normalize_perform_ny_source;
```

The default inventory output directory is `output/ny_only_package_a/source_inventory`. The normalizer exports source manifest, bus, branch, generator, shunt, control, shunt-alias, boundary reconciliation, unresolved-record and mapping tables, plus normalization gates. The 32 inventory gates check coverage, source values/limits/status, role accounting, shunt duplication, identity, remote-control disclosure, and claim boundaries. The focused test exercises 23 assertion groups, including adversarial capacity changes, false native/reference membership, offline injections, duplicate keys, shunt double counting, hidden identity ambiguity, and false vintage/qualification labels.

Source inputs are immutable. No power flow is run by normalization, and its `electrical_baseline_qualified` and `dlr_ready` remain false. The separate bounded electrical solve and independent replay determine the initial source-reference qualification.
