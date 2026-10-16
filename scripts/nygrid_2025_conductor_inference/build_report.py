"""Write the versioned R/X-first synthetic-conductor handoff addendum."""
from pathlib import Path
import hashlib
import json
from infer_conductors import infer

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_conductor_inference'
REPORT=ROOT/'NYGRID_2025_CONDUCTOR_INFERENCE.md'


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))


def record(p):return dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def main():
    inference=read(OUT/'inverse_search_receipt.json')
    tests=read(OUT/'matlab_validation/validation_receipt.json')
    api=read(OUT/'independent/inference_api_independent_review.json')
    assert inference['passed'] and tests['passed'] and api['passed']
    assert inference['current_targets_with_candidates']==185 and inference['imported_targets_with_candidates']==141
    example,candidates=infer(.0004,.0043,345.,100.,.1472539799143274)
    chosen=example['selected_by_declared_ranking']
    (OUT/'worked_example.json').write_text(json.dumps(example,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    counts='\n'.join(f"| {p['hour_index']} | {p['v1_parent_count']} | {p['v2_parent_count']} | {p['imported_RX_parent_count']} | {p['prior_engineered_RX_parent_count']} | {p['segment_count']} |" for p in tests['points'])
    text=f'''# R X conditioned synthetic conductors for DLR research

**A physically consistent synthetic conductor realization is sufficient for this research. Identifying the installed circuit is not a prerequisite.** A declared catalog conductor, temperature, bundle, circuit count, geometry and equivalent length must reproduce the modeled R and X, and its conductor currents and heat balance must remain consistent with the electrical model.

This addendum supersedes the **source-keyed conductor eligibility restriction** in the earlier [DLR handoff](NYGRID_2025_DLR_HANDOFF.md). New APIs and evidence sit alongside that frozen handoff. All electrical cases, R/X/B values, dispatch, voltage solutions, previous comparisons and v1 archives remain unchanged. The new screen admits realizable generic synthetic overhead corridors without claiming installed-asset identification.

## What R and X constrain

For identical, transposed, uncoupled parallel circuits, using ohms and metres:

~~~text
R = r_sub(T) L / (n_c n_b)
X = omega 2e-7 ln(D_m / GMR_bundle) L / n_c
X/R = n_b omega 2e-7 ln(D_m / GMR_bundle) / r_sub(T)
L = R n_c n_b / r_sub(T)
Z_base = kV_base^2 / MVA_base
~~~

Here n_c is integer parallel-circuit count, n_b is subconductors per phase, D_m is phase geometric mean distance, and r_sub(T) is catalog AC resistance at the declared reference temperature. Bundle GMR follows the explicit regular-polygon arrangement. The study uses 60 Hz. These relationships use the conductor, temperature, GMR/GMD, length and electrical-base information of a conventional [transmission-line parameter calculation](https://www.powerworld.com/WebHelp/Content/MainDocumentation_HTML/Transmission_Line_Parameter_Calculator.htm).

R/X does **not** uniquely identify a conductor. Circuit count and length cancel from X/R. Several conductors and geometries can match the same pair; extra identical circuits permit proportionally longer lines while changing aggregate ampacity. The deliverable therefore retains a **candidate set** and a declared ranking. [Independent degeneracy examples](output/nygrid_2025_conductor_inference/independent/same_R_X_different_circuits_length_charging.csv) make this ambiguity explicit.

## The inverse search

The [inference API](scripts/nygrid_2025_conductor_inference/infer_conductors.py) holds R and X fixed and:

1. Searches the archived 14-conductor ACSR/ACSS catalog at declared reference temperatures of 75°C for ACSR and 95°C for ACSS.
2. Searches integer circuit counts 1–4 and the existing voltage-class bundle/spacing windows.
3. Solves GMD from X/R, then derives length from R.
4. Rejects candidates outside the declared geometry or equivalent-length bounds.
5. Reconstructs both R and X. Derived B is recorded separately; supplied positive B may rank alternatives, but model B is never overwritten.

The default length range starts at 5 m and retains the earlier broad voltage caps: 250 km below 200 kV, 500 km below 300 kV, 700 km below 400 kV and 1,000 km otherwise. **No geographic chord or identified route is required.** These are synthetic engineering limits, not surveyed routes or confidence intervals. An explicit maximum-length override is labeled as a sensitivity. No PF solution, interface error or favorable weather enters the ranking. Complete corona, mechanical and installed-equipment qualification is outside this inference.

The fresh search covers 186 overhead-class parent targets on both parameter bases:

| Search target | Parents with candidates | Interpretation |
|---|---:|---|
| Current model R/X | 185 of 186 | Compatible homogeneous catalog/geometry realizations exist; asset-class conflicts and runtime status are checked separately. |
| Imported R/X | 141 of 186 | Historical pairs can be retained under the default search; not all were retained in the earlier construction. |

The [372-row target summary](output/nygrid_2025_conductor_inference/inverse_target_summary.csv) and [{inference['feasible_candidate_rows']:,} feasible candidates](output/nygrid_2025_conductor_inference/feasible_candidate_realizations.csv) preserve alternatives and target provenance. Existing heterogeneous Dover material segments remain a separate valid realization; a homogeneous alternative is not silently substituted.

## Inference and prior redesigns

The earlier 186-parent overhead construction comprised 125 exact imported-R/X inverse fits, three source-design realizations and 58 explicit engineering redesigns. The loss revision removes parent 224's former thermal redesign, leaving 57 such redesigned parents overall. They are conductor-derived engineering models, but they must not be described as inference from unchanged imported R/X.

Under the default no-chord search, **13 earlier redesigns have feasible original-R/X alternatives**. Three more—parents 152, 163 and 164—require an explicit extension of the 220-kV cap from 500 km to 1,000 km; their selected equivalent lengths are approximately 646.5, 510.9 and 556.1 km. The [attribution table](output/nygrid_2025_conductor_inference/independent/recovered_imported_RX_attribution.csv) distinguishes these cases. The initial broader tally of 16 includes a length-limit sensitivity, not only removal of geographic constraints.

No alternative changes the validated electrical case here. Applying an original-R/X restoration or selecting another thermal realization belongs in a separately named scenario with an electrical/thermal comparison. The workflow does not change a target R/X simply to make the inverse fit succeed.

## A concrete inferred realization

For R = 0.0004 pu and X = 0.0043 pu on 100 MVA and 345 kV, there are {example['candidate_count']} feasible candidates from {example['distinct_catalog_choices']} catalog choices. With current geometric B = 0.1472539799143274 pu supplied for ranking:

| Quantity | Inferred or declared value |
|---|---|
| Conductor | {chosen['code_word']} ACSS 795 kcmil |
| Parallel circuits | {chosen['circuits']} |
| Subconductors per phase | {chosen['bundle_count']} |
| Bundle spacing | {chosen['bundle_spacing_m']:.4f} m |
| Phase GMD | {chosen['GMD_m']:.6f} m |
| Equivalent length | {chosen['length_m']/1000:.6f} km |
| Reference temperature | {chosen['reference_temperature_C']:.0f}°C |
| Reconstructed R and X | {chosen['forward_R_pu']:.7f} pu and {chosen['forward_X_pu']:.7f} pu |

This is a reproducible synthetic interpretation, not unique identification. The [worked example](output/nygrid_2025_conductor_inference/worked_example.json) retains all uncertainty fields. Its equivalent length need not equal the distance between named aggregate-bus map points.

## Updated MATLAB eligibility

The selector checks catalog properties, temperature, geometry, integer multiplicities, electrical bases and **both R and X in every numerical section**. It reuses the current model's consistent realization without substituting newly ranked alternatives. Imported and previously engineered R/X receive separate labels. B difference is disclosed; all admitted existing realizations at the tested points also match current B.

Installed-circuit identity and geographic-route bounds no longer gate synthetic eligibility. Cables, voltage-changing equipment, transformers/PARs, incompatible records and the four known overhead/cable conflicts remain excluded. An algebraic fit does not turn a cable into an overhead conductor.

| Hour | V1 parents | R/X based parents | Imported R/X | Prior engineered R/X | Segments |
|---:|---:|---:|---:|---:|---:|
{counts}

All v1 branches remain admitted with identical recovered currents. Hour 8508 has 180 admitted parents, 252 runtime branches and 253 segments; hour 4000 has 179 parents and 251 segments. These dated active counts use a different denominator from the 186-parent inverse search.

For synthetic weather of 25°C, 0.6096 m/s perpendicular wind, 1,000 W/m² solar and 101,325 Pa, the expanded set reveals maximum series-current/ampacity ratios of approximately 3.654 at hour 4000 and 1.479 at hour 8508. Both maxima occur on parent 41, in the **prior_engineered_RX** tier: current R/X is approximately 0.0598327463/0.2040452503 pu, versus imported 0.0018/0.0089 pu. Its reused interpretation is a 115-kV, single-circuit, single-bundle ACSR Hawk line. These are synthetic exposure results, not observed overloads or a unique inference from the imported pair. Both points retain their false V/Q gate. No OPF, resistance feedback, dispatch change or annual replay was performed.

## Parent 224

The released Gilboa–Buchanan equivalent has R = 0.02 pu and X = 0.0147 pu, hence X/R = 0.735. The current 345-kV catalog/geometry minimum is 3.47384. Matching this ratio requires GMD at most 0.361 m, while the declared range is 7–14 m. Length and identical circuit count cannot repair that ratio.

Its exclusion is **no feasible realization under the declared catalog and geometry**, not missing installed identity. This is not a universal impossibility claim. The independent audit demonstrates that tiny non-transmission conductors can produce algebraic fits, but those lack applicable voltage/corona/mechanical screening and are not accepted. Parent 224 remains an unresolved equivalent unless a separately justified electrical or device-model revision is adopted.

## Run the corrected workflow

From a checkout or an extracted v1 handoff with this supplement installed:

~~~matlab
addpath('scripts/nygrid_2025_dlr_handoff/runtime');
setup_nygrid_2025_handoff(pwd);
addpath('scripts/nygrid_2025_conductor_inference');
weather = table(25,.6096,90,1000,101325,'VariableNames', ...
    {{'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'}});
screen = screen_nygrid_2025_rx_thermal(8508,weather);
~~~

In the original checkout without bundled vendor code, pass an explicit MATPOWER 8.1 root as the second setup argument. The one-way screen changes neither the electrical solution nor R/X/B. Preserve its branch/segment keys, candidate/exclusion ledger, operating flags and forward R/X audit.

For a new tuple:

~~~text
python scripts/nygrid_2025_conductor_inference/infer_conductors.py --r-pu 0.0004 --x-pu 0.0043 --kv 345 --base-mva 100 --b-pu 0.1472539799143274 --output runs/conductor_example
~~~

Python 3.11+ and NumPy are required. Use a new or empty output directory. Omitting B removes it from ranking. Supplying --maximum-length-m makes the changed cap explicit. Outputs contain the full candidate set, R/X errors, derived B, circuit/bundle assumptions and material properties.

## Validation and preservation

The mathematical audit passed 504 forward/inverse/current checks. The API passed 29 independent checks, including base conversion, all target/candidate reconstructions, multiplicity ambiguity, failure conditions and output preservation. MATLAB validation passes {tests['test_count']} checks at hours 4000 and 8508, including R-only/X-only errors, geometry/material/temperature/axis guards, unchanged input cases and current/Joule identities.

Evidence: [inverse physics](output/nygrid_2025_conductor_inference/independent/inverse_physics_review.json), [API review](output/nygrid_2025_conductor_inference/independent/inference_api_independent_review.json), and [MATLAB validation](output/nygrid_2025_conductor_inference/matlab_validation/validation_receipt.json). These checks establish consistent synthetic realizations and implementation, not installed conductors or observed route weather.
'''
    REPORT.write_text(text,encoding='utf-8')
    receipt=dict(passed=True,scope='R/X-first handoff addendum from independently checked target and screening records',
        inferred_conductors_are_synthetic=True,installed_identity_required=False,electrical_parameters_modified=False,
        default_current_targets_with_candidates=185,default_imported_targets_with_candidates=141,
        default_restorable_prior_redesigns=13,additional_explicit_long_length_cases=[152,163,164],
        worked_example=example,dependencies=[record(p) for p in [Path(__file__),OUT/'inverse_search_receipt.json',
            OUT/'matlab_validation/validation_receipt.json',OUT/'independent/inference_api_independent_review.json']],
        outputs=[record(REPORT),record(OUT/'worked_example.json')])
    (OUT/'report_receipt.json').write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(str(REPORT))


if __name__=='__main__':main()
