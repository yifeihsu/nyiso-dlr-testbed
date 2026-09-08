# Compact interface operator reconstruction audit

The separate `compact_nyiso_interface_operator_variant` helper corrects three demonstrable coverage errors without changing the frozen 66-bus baseline or consulting validation-hour observations. It adds the Stolle–Meyer A-to-C bypass to Dysinger East and West-Central, and replaces the F-to-G Total East proxy with the complete modeled western A–E to eastern F–K cut. The resulting operators remain approximate research measurements. Missing network paths and unresolved public metering prevent exact NYISO interface validation.

The variant is named `nygrid_informed_partition_v1`. It accepts an NY-only MATPOWER case and its row-aligned stable branch keys. Its seven names and coefficient matrices match the existing scoring API. The returned registry, bus partitions, member table, definition sources, and coverage gaps make the change reviewable. No interface targets, generation dispatch, or solved branch powers affect construction. It does not add external-flow offsets.

## Evidence and interpretation

NYgrid’s Table I identifies Total East with E-to-F plus E-to-G transfers. Its pinned `flow4Plot.m` implements Total East as its Central East expression plus another branch contribution. It does not identify Total East with F-to-G. Those numeric row references belong to NYgrid’s own reduced network and are not reusable on this case. NYgrid’s `PFtestcase.m` performs **DC** power flow; its interface preprocessing averages samples by hour and fills missing observations. These choices differ from AC terminal metering and from an individual P32 point sample. [NYgrid paper, Table I and Sections IV–V](https://sustainable-power-energy-research.media.uconn.edu/wp-content/uploads/sites/3441/2023/11/An-Open-Source-Representation-for-the-NYS-Electric-Grid-to-Support-Power-Grid-and-Market-Transition-Studies.pdf), [pinned flow4Plot](https://github.com/AndersonEnergyLab-Cornell/NYgrid/blob/47698b6c7823ae7b1bc6935e5601d5b64b8f918e/Utility/flow4Plot.m), [pinned PFtestcase](https://github.com/AndersonEnergyLab-Cornell/NYgrid/blob/47698b6c7823ae7b1bc6935e5601d5b64b8f918e/PFtestcase.m).

The public NYISO definition places the Stolle path in both western interfaces. In the compact model its stable identity is `NPCC_S7:BRANCH_ROW:73`, with endpoints 62–63. Although those endpoint zones are A and C, it must not disappear from a West-Central aggregation merely because that proxy previously selected B-to-C branches. [NYISO Dysinger East and West Central study, interface definitions](https://www.nyiso.com/documents/20142/1394656/DE_WC_Stability_Limit_Report_final-3.pdf/b461b192-f51d-7bf7-340e-d424b60c84fa), [NYISO Appendix 5.1, page 2](https://www.nyiso.com/documents/20142/1410707/CRPP_Appendix_5.1_Interface_Definitions.pdf/6bd50d60-bfd2-4572-31bf-634fbb6c8ddf).

## Local realization and remaining gaps

Counts below are active branch memberships on the current 66-bus construction. A branch can legitimately belong to two different interfaces. Within each operator it appears once, at one terminal.

| Interface | New / previous count | Local realization | Remaining limitation |
|---|---:|---|---|
| Dysinger East | 3 / 2 | All NY branches leaving zone A; adds Stolle–Meyer. | Aggregated western network does not identify each public low-voltage circuit or later Dysinger device. |
| West-Central | 4 / 3 | All NY branches leaving A+B; adds the same A-to-C bypass. | Public low-voltage circuits remain aggregated. |
| Moses South | 3 / 3 | Complete modeled zone-D export cut: two Moses–Adirondack legs and the remaining Colton/Porter aggregation. | Explicit Massena–Marcy 765-kV path and individual 115-kV members are absent. |
| Central East | 5 / 5 | Existing E-to-F proxy retained, including the three new Edic circuit keys. | Some public members are absent; two inherited 230-kV paths are proxies rather than the published modern member list. |
| Total East | 6 / 2 | Complete A–E to F–K model cut: five E-to-F branches plus Binghamton–Gilboa, keyed by inherited record 37. | Binghamton–Gilboa is a coarse cross-boundary substitute. Coopers/Middletown paths and selected external contributions are unresolved. |
| UPNY-ConEd | 6 / 6 | Existing six source circuits. East Fishkill and Wood Street belong to the receiving side of this local partition. | RFK305 and lower-voltage East Fishkill members are absent. |
| Dunwoodie South | 6 / 6 | Existing I-to-J receiving paths; each replacement path counted at its first crossing. | I-to-J is not a complete public or closed Dunwoodie definition; other zone and external contributions are not added by assumption. |

The 2024 Central East study explicitly includes Edic–Princetown 351/352 and Edic–Gordon Road 14, along with Marcy–New Scotland, three 115-kV members, and Plattsburgh–Sand Bar. Therefore a corrected regional cut still cannot establish public monitored-element identity on this coarse network. [NYISO CEVC-24, Figure 8](https://www.nyiso.com/documents/20142/3692791/Central-East-Voltage-Limit-Study-2024-FINAL.pdf).

The 2023 Total East study describes a closed interface with internal Central East and Marcy South members plus selected PJM paths and Plattsburgh–Sand Bar. A regional P32 scheduled interchange total does not identify these individual terminal flows. The helper consequently returns zero applied offsets **and an explicit unresolved-coverage flag**, rather than treating unknown contributions as measured zero. Public transfer limits are not added as branch ratings. [NYISO TE-23, Table 2](https://www.nyiso.com/documents/20142/3692388/TE-23-StabReport-OC-09-15-2023-Approved.pdf/b03ef116-aa5a-616d-9a5a-86f091e8e53d).

The missing 765-kV Moses path is a network-representation gap, not an operator-sign error. The public 2024 definition lists that path separately from both 230-kV Moses–Adirondack circuits. [NYISO MS-24](https://www.nyiso.com/documents/20142/1411640/MS-24-StabReport-OC-07-18-2024-Approved.pdf/1c512118-6ef0-2092-5653-2f2807d3e380).

## AC convention and verification

Each contribution is real power entering the branch at the declared upstream endpoint: `PF` when upstream is the from bus, or `PT` when upstream is the to bus. This uniform convention is physically meaningful and invariant to branch orientation. It is not a claim to reproduce the public definition’s mixed metered ends; replacing `PT` by `-PF` would silently neglect line loss.

Fourteen focused tests pass. They verify the new membership counts, restored bypasses, Total East’s exclusion of the downstream F-to-G gate, unchanged other proxy scopes, retirement and series-path exclusion, branch permutation and orientation invariance, independence from loads/dispatch/solved flows, and rejection of stale critical identities. For every complete modeled partition, an independent arbitrary-phasor calculation verifies that cut flow equals regional nodal injection minus internal branch losses and bus-shunt consumption. Tests perform no optimization and read no observed interface targets.

These definitions were fixed without reading the newly reserved validation hours. Previously inspected study hours are revisited diagnostics; any new unseen-hour evaluation must keep the operator, generation-prior method, and metering/averaging rules frozen before reading those outcomes. No accuracy claim follows from this construction audit alone.

The previous `compact_nyiso_interface_operators` helper, saved electrical campaign, thermal campaign, and their manifests remain unchanged. Both GitHub preferred-2025 jobs in runs `34188988373` and `34188987233` passed; this audit required no CI repair.
