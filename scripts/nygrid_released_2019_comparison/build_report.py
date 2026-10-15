"""Correct the comparison reference to the authors' actual released model."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_released_2019_comparison'
def rec(p):
    with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':digest}
def refs(o):
    if isinstance(o,dict):
        if isinstance(o.get('path'),str) and isinstance(o.get('sha256'),str):yield o
        for x in o.values():yield from refs(x)
    elif isinstance(o,list):
        for x in o:yield from refs(x)
def main():
    independent=OUT/'independent/independent_released_2019_review.json';review=json.loads(independent.read_text())
    fresh_path=OUT/'fresh_author_release_receipt.json';fresh=json.loads(fresh_path.read_text());assert review['passed'] and fresh['passed']
    assert fresh['original_author_files_unchanged'] and not fresh['derived_full_NPCC_loaded'] and not fresh['current2025_case_loaded']
    for r in refs(review):
        p=Path(r['path']);p=p if p.is_absolute() else ROOT/p
        assert rec(p)['sha256']==r['sha256'],p
    checks=pd.read_csv(OUT/'fresh_author_release_checks.csv');columns=[c for c in checks if 'difference' in c]
    assert len(checks)==12 and checks[columns].abs().to_numpy().max()==0 and checks.PF_success.eq(1).all()
    comparison_path=OUT/'independent/released2019_vs_othermodel2025.csv';a=pd.read_csv(comparison_path)
    metrics_path=OUT/'independent/released_2019_recomputed_metrics.csv';metrics=pd.read_csv(metrics_path)
    assert len(a)==7 and a.released_2019_hours.eq(8760).all() and a.other_model_2025_hours.eq(8651).all()
    lines=['| Interface | Authors supplied if.map: 2019 WAPE | Current 2025 WAPE | 2019 MAE, MW | Current MAE, MW |','|---|---:|---:|---:|---:|']
    literal=['| Interface | Literal flow4Plot WAPE | Authors if.map WAPE |','|---|---:|---:|']
    for r in a.itertuples():
        lines.append(f'| {r.interface} | {r.authors_ifmap_2019_WAPE_percent:.2f}% | {r.other_model_2025_WAPE_percent:.2f}% | {r.authors_ifmap_2019_MAE_MW:.2f} | {r.other_model_2025_MAE_MW:.2f} |')
        literal.append(f'| {r.interface} | {r.strict_literal_2019_WAPE_percent:.2f}% | {r.authors_ifmap_2019_WAPE_percent:.2f}% |')
    text=f'''# Comparison using the authors' released 2019 model

This corrects the reference used in the preceding comparison. The 2019 benchmark here is the **authors' released final 57-bus NYgrid DC model with their supplied 2019 inputs**, pinned at NYgrid commit `47698b6c7823ae7b1bc6935e5601d5b64b8f918e`. It is not our reconstructed 140-bus counterpart and does not use any of our 2025 model changes or operating inputs.

## Model and input provenance

The authors' pipeline is `modifyMPC` → `updateOpCond` → `rundcpf`. Its final case has57 buses,94 AC branches,271 generator records and four DC-link records. The provided2019 load, generation, interchange and prepared observation inputs are retained at the authors' public-system power scale, with their original8760 local-hour preparation and missing/DST treatment.

All73 pinned upstream files passed SHA-256 and Git-blob identity checks. The archived annual run used a separate performance-only table-reading cache; its allocation, reduction and solver arithmetic remained unchanged. Existing original-versus-cache checks were verified, and **12 new monthly runs of the unmodified author source reproduce the saved inputs and solved flows exactly**. Each fresh case matches bus, generator, branch, DC, cost and interface arrays with maximum difference zero. No reconstructed/full counterpart or current2025 case was loaded during those checks.

All8760 saved author-model hours were independently rescored from their94-branch flow arrays. This is a fresh provenance check,12 fresh source solves, and a fresh full-year rescore of the verified archived release run; it is not represented as8760 new MATLAB solves in this task.

## Two measurements of the same unchanged model

The release contains an internal discrepancy between five hard-coded branch-index formulas in `Utility/flow4Plot.m` and its own signed interface map `m.if.map` in `updateOpCond.m`. Both measurements are retained separately:

1. **Strict literal plotting-helper output:** execute the released formulas exactly. Pooled WAPE is60.663879663%. These stale indices do not reproduce the reported validation figure and must not be used to claim that our current model is dramatically more accurate.
2. **Authors' supplied interface-map output:** aggregate the same unchanged solved branch flows using the authors' own `m.if.map`. Pooled WAPE is11.218076931%. This changes the reported measurement only; no network parameter, load, generation, dispatch, input or power-flow solution changes.

The independent reviewer parsed the original source's member lists and verified that they equal the saved map in all four annual partitions. Both independently reconstructed interface series match their respective saved series exactly. The table below uses the supplied map for meaningful interface comparison and labels it explicitly.

## Corrected comparison reference

Both WAPE columns use `100 × sum(abs(simulated − observed)) / sum(abs(observed))`. These are our calculations from released-model outputs, not an author-published WAPE table. The current2025 column remains a separate comparison model; it is never substituted for the2019 reference.

{chr(10).join(lines)}

The released-model pooled WAPE is **11.21808%**, versus **15.11099%** for the current2025 model. This is a cross-year benchmark:2019 has8760 prepared local-hour cases;2025 has8651 eligible physical-hour AC cases. Generation, demand, controls, topology and solver physics differ. Pooled error combines overlapping interfaces and is not a statewide energy-balance metric. The available comparison supports lower downstate errors and higher overall current errors, but does not identify a causal effect of model changes.

## Literal release diagnostic retained

{chr(10).join(literal)}

These columns use precisely the same57-bus solves and2019 inputs. The large differences expose a measurement-index inconsistency in the release, not an alternative physical model. No observation-driven fitting or branch-index replacement was made inside the authors' files.

The paper's Equation11 and released helper instead normalize signed observed-minus-simulated error by the hourly positive interface limit. That is distinct from WAPE. West Central's9999 positive-limit field is not a verified physical rating. Literal helper errors, author-map errors, empirical limit-normalized quantiles, MAE, RMSE and bias are all retained in the metrics CSV.

## Reproduction and limitations

The source check uses MATLAB R2026a, MATPOWER8.1 legacy core and the pinned June2019 reduction-toolbox mirror. The precise software revision used to create the published figure is unknown. The result is a verified reproduction of the available pinned code/data release, not a claim to recover the authors' undisclosed execution environment or reproduce Figure5 bit-for-bit. DC convergence also does not certify AC/reactive, thermal or operational feasibility.

From the repository root:

```powershell
cd "C:\\Users\\Holiday\\Desktop\\npcc_ny_lite_package_fixed\\WECC and NPCC Systems"
& 'C:/Program Files/MATLAB/R2026a/bin/matlab.exe' -batch "addpath('scripts/nygrid_released_2019_comparison'); check_unmodified_release"
python scripts/nygrid_released_2019_comparison/independent/recompute_released_metrics.py
python scripts/nygrid_released_2019_comparison/build_report.py
```

- [Fresh unmodified-source checks](output/nygrid_released_2019_comparison/fresh_author_release_checks.csv)
- [Fresh source-run receipt](output/nygrid_released_2019_comparison/fresh_author_release_receipt.json)
- [Independent annual rescore and provenance](output/nygrid_released_2019_comparison/independent/independent_released_2019_review.json)
- [Both measurement variants and all metrics](output/nygrid_released_2019_comparison/independent/released_2019_recomputed_metrics.csv)
- [Corrected baseline comparison](output/nygrid_released_2019_comparison/independent/released2019_vs_othermodel2025.csv)
- [Original author-file manifest](output/nygrid_2019/upstream_manifest.json)
- [Original full-year release-run verification](output/nygrid_2019/independent_dc_replay.json)

This additive correction preserves both the authors' files and all earlier model/evidence artifacts. The previously used derived140-bus counterpart remains a separate historical research artifact and is excluded from this benchmark.
'''
    # Keep prose readable while retaining literal code paths and identifiers.
    for before,after in [('has57','has 57'),(',94',', 94'),(',271',', 271'),('provided2019','provided 2019'),('original8760','original 8760'),('All73','All 73'),('All8760','All 8760'),('their94','their 94'),('check,12','check, 12'),('as8760','as 8760'),('is60.','is 60.'),('is11.','is 11.'),('current2025','current 2025'),('the2019','the 2019'),('benchmark:2019','benchmark: 2019'),('has8760','has 8760'),(';2025','; 2025'),('has8651','has 8651'),('same57','same 57'),('and2019','and 2019'),('Equation11','Equation 11'),("Central's9999","Central's 9999"),('MATPOWER8.1','MATPOWER 8.1'),('June2019','June 2019'),('Figure5','Figure 5'),('derived140','derived 140')]:text=text.replace(before,after)
    report=ROOT/'NYGRID_RELEASED_2019_COMPARISON.md';report.write_text(text,encoding='utf-8')
    sources=[independent,fresh_path,OUT/'fresh_author_release_checks.csv',OUT/'fresh_author_release_cases.mat',comparison_path,metrics_path,ROOT/'scripts/nygrid_released_2019_comparison/check_unmodified_release.m',Path(__file__)]
    receipt={'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),
        'baseline':'Authors released57bus case and authors2019 inputs','authors_release_commit':fresh['upstream_commit'],
        'our_derived140bus_case_used':False,'our_current2025_inputs_used_in2019_case':False,
        'fresh_unmodified_author_source_hours':12,'fresh_maximum_saved_input_and_solution_difference':0.,
        'annual_original_release_hours_rescored':8760,'two_measurements_of_same_unchanged_case':True,
        'author_map_pooled_WAPE_percent':11.218076930625285,'literal_helper_pooled_WAPE_percent':60.66387966304786,
        'reported_as_exact_paper_figure_reproduction':False,'sources':[rec(p) for p in sources],'report':rec(report)}
    (OUT/'comparison_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'author_source_cases_exact':12,'released_annual_hours':8760,'baseline_buses':57,'derived140_used':False}))
if __name__=='__main__':main()
