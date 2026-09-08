# Matched NYgrid 2019 reference export

The New York-only control contains the original buses **37–82**, **67 internal AC branch records**, and **243 native generator records**. With the exported terminal injections, its independent DC solve reproduces all 8,760 completed reference hours: maximum internal branch error **1.23e-11 MW**, corrected-interface error **1.86e-11 MW**, and native solved-generation error **1.73e-11 MW**. The acceptance tolerance is 1e-7 MW. These are actual 2019 MW; no benchmark scaling is applied.

This proves fixed-input DC equivalence, including the reference-generator adjustment. It does not prove that the frozen boundary injections reproduce external-network responses after changing NY injections, nor does it establish AC feasibility, generator reactive capability, or thermal limits. The source DC calculations can exceed operating limits.

## Transfer contract

`annual_reference.npz` and `annual_reference.mat` contain the same numerical arrays. Annual rows are identified by `hour_index=1..8760`; columns of bus arrays follow `bus_ids=37..82`. January 8 at 15:00 is **hour index 184**, or Python row 183.

The intended accounting is:

```
net_input = native_input_pg_bus_mw - net_pd_mw
          + boundary_ac_bus_mw + boundary_dc_bus_mw + boundary_hq_bus_mw
```

`boundary_total_bus_mw` is the sum of those three boundary components. Alternatively, a solver with only native generators can use `effective_pd_for_native_only_mw = net_pd_mw - boundary_total_bus_mw`.

`native_solved_pg_bus_mw` and `slack_adjustment_bus_mw` expose the post-PF result separately. Bus **74** remains the reference at the source input angle **0.2979 degrees**. Its first online generator absorbs the balance; this change is not independently observed nuclear generation.

The alternative `all_input_pg_with_hq_bus_mw` and `all_solved_pg_with_hq_bus_mw` arrays include HQ already. **Do not add `boundary_hq_bus_mw` to either alternative.** The last source generator, row 271 at bus 48, is the HQ boundary representation, excluded from the 243 native records. The source has 244 generator records located on NY buses when HQ is included.

| Array | Shape / interpretation |
|---|---|
| `net_pd_mw` | 8760 × 46; source reduced demand after renewable negative loads, before the exported boundary injections |
| `native_input_pg_bus_mw`, `native_solved_pg_bus_mw` | 8760 × 46; bus sums of the 243 native records |
| `boundary_ac_bus_mw`, `boundary_dc_bus_mw`, `boundary_hq_bus_mw` | 8760 × 46; positive means injection into NY |
| `boundary_ac_crossing_injection_mw` | 8760 × 8; individual NY-side crossing injections |
| `dc_schedule_mw` | 8760 × 4; source from-to DC schedules |
| `branch`, `source_branch_rows` | 67 × 13 branch parameters and one-based source 57-bus branch rows |
| `branch_pf_mw`, `bus_va_deg` | 8760 × 67 and 8760 × 46; original reference results |
| `operator_coefficients` | 7 × 67; corrected source interface coefficients |
| `corrected_interface_mw`, `observed_interface_mw` | 8760 × 7; source-model and published reference values, separately retained |

## External and auxiliary buses

The eight surviving AC crossings are 29–37, 35–73, 48–100, 54–102, 54–103, 66–134, 67–138 and 75–124. Positive NY-side injection is `+PF` when NY is the to-bus and `-PF` when NY is the from-bus. These are **flows on the AC branch records obtained from the source DC solution**, not measured terminal telemetry.

The four lossless DC records are 21→80 (1385 plus CSC), 124→79 (Neptune), and two 125→81 records (HTP and VFT). Source branch 81–125 was removed by the released construction. The explicit HQ generator at 48 supplies the remaining boundary component.

Bus **21** is a retained external New England auxiliary generator and DC sender, connected to 29/35 through Ward equivalents. Bus **132** is a retained external PJM load/generator aggregate connected to 124/125/134/138. They are kept in the original 57-bus reference and removed from this NY-only control after the crossing ledger is extracted. Their internal external-network exchanges are not added a second time. `source_bus_role_register.csv` records all 57 source buses, including the nine retained external boundary buses and these two auxiliaries.

`source_branch_register.csv` preserves every source branch's endpoints, orientation, parallel ordinal and one-based row identity. Its stable keys identify records in the pinned reduced model; they are not verified utility circuit identifiers. `corrected_interface_coefficients.csv` resolves all seven measurements onto internal NY rows. No coefficient is dropped during extraction.

## Development-hour components

`matched_components.npz` / `.mat`, `matched_bus_components.csv`, and the accompanying generator/boundary tables cover January 8 15:00; January 21 18:00; April 21 04:00; July 17 16:00; July 20 16:00; and July 27 02:00. These are previously examined development examples, not unseen validation hours. January 8 has separate CSV views.

The component export reruns the released cached reconstruction without changing its arithmetic, then checks the resulting demand and branch flows against the completed annual reproduction. It separates gross load, wind and other renewable negative loads, thermal recorded output, thermal residual allocation, input hydro, nuclear output, and solved slack pickup. Missing thermal records remain marked in the unit table; the bus recorded-total follows the released rule that fills them with zero. The NY Ward demand adjustment is retained explicitly and is only numerical roundoff in these six hours.

January 8 gross demand is **19,275.8 MW**. Recorded thermal output totals **5,762 MW**; the literal release adds **936.333 MW** through its J-only residual policy. Hydro input totals **3,569.667 MW** and reconstructed nuclear input **5,358.371 MW**. The July source St. Lawrence factor is **1.076077**, producing **921.122 MW** against the code's 856-MW capacity assumption. This is preserved reproduction evidence, not a repaired or bounded hydro estimate.

The source tables use the release's hourly means and linear missing-value interpolation. This export does not substitute raw five-minute samples or the later study's forward-hold time aggregation. The original time labels remain naive local timestamps; no new DST correction is introduced.

## Reproduction and provenance

1. Run `scripts/nygrid_compact_2019/export_reference_snapshot.m` in MATLAB to generate the six component snapshots.
2. Run `scripts/nygrid_compact_2019/export_reference.py` with the system Python environment containing NumPy/SciPy.

`reference_export_summary.json` records all annual MAT and final companion CSV hashes, exporter hashes, output hashes and the exact-replay results. The existing NYgrid evidence is consumed read-only. The source is [NYgrid commit 47698b6c7823ae7b1bc6935e5601d5b64b8f918e](https://github.com/AndersonEnergyLab-Cornell/NYgrid/tree/47698b6c7823ae7b1bc6935e5601d5b64b8f918e), using the separately pinned historical reduction toolbox and the previously validated read-cache adaptation. Their source and compatibility manifests remain under `output/nygrid_2019/`.
