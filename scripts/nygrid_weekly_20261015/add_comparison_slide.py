"""Bind independently recomputed cross-year evidence to one editable slide."""
from pathlib import Path
from datetime import datetime, timezone
import csv, hashlib, json, re, shutil

ROOT=Path(__file__).resolve().parents[2]
PROJECT=ROOT/'output/pdf/nygrid_weekly_2026-10-15'
EVIDENCE=ROOT/'output/nygrid_weekly_20261015/evidence'
TITLE='2019 Benchmark vs. 2025: Errors and Observed Flows'


def record(path):
    return dict(path=path.relative_to(ROOT).as_posix(),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                bytes=path.stat().st_size)


def label(name):
    key=re.sub('[^a-z]','',name.lower())
    if 'dysinger' in key:return 'Dysinger East'
    if 'westcentral' in key:return 'West Central'
    if 'totaleast' in key:return 'Total East'
    if 'moses' in key:return 'Moses South'
    if 'centraleast' in key:return 'Central East'
    if 'upny' in key:return 'UPNY--ConEd'
    if 'spr' in key or 'dun' in key:return 'SPR/DUN--South'
    raise ValueError(name)


def pair(a,b,precision):
    return f'{a:,.{precision}f}' + r'$\to$' + f'{b:,.{precision}f}'


def delta(value,precision):
    color='bad' if value>0 else 'good'
    return '\\'+color+'{$'+f'{value:+.{precision}f}'+'$}'


def main():
    source=EVIDENCE/'2019_comparison_current.csv'
    target=PROJECT/'data/comparison_2019_2025.csv'
    shutil.copyfile(source,target)
    rows=list(csv.DictReader(target.open(newline='',encoding='utf-8-sig')))
    assert len(rows)==7
    for row in rows:
        for key in row:
            if key!='interface':row[key]=float(row[key])
    rows.sort(key=lambda x:x['mae_2025_MW'],reverse=True)
    m=next(r for r in rows if 'moses' in r['interface'].lower())
    tex=r"""\begin{frame}{2019 Benchmark vs. 2025: Errors and Observed Flows}
\scope{Released 2019 DC case (8,760 h) $\to$ current 2025 AC case (8,651 eligible h)}
\footnotesize
\renewcommand{\arraystretch}{1.10}
\setlength{\tabcolsep}{2.5pt}
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrrr@{}}
\toprule
 & \makecell{MAE (MW)\\2019 $\to$ 2025} & $\Delta$ MW
 & \makecell{WAPE (\%)\\2019 $\to$ 2025} & $\Delta$ pp
 & \makecell{NYISO mean $|F|$ (MW)\\2019 $\to$ 2025} & $\Delta$\% \\
\midrule
"""
    for r in rows:
        tex+=' & '.join([
            label(r['interface']),
            pair(r['mae_2019_MW'],r['mae_2025_MW'],1),
            delta(r['delta_mae_MW'],1),
            pair(r['wape_2019_percent'],r['wape_2025_percent'],2),
            delta(r['delta_wape_pp'],2),
            pair(r['mean_abs_flow_2019_MW'],r['mean_abs_flow_2025_MW'],0),
            '$'+f"{r['delta_mean_abs_flow_percent']:+.1f}"+'$'
        ])+r' \\'+ '\n'
    tex+=r"""\bottomrule
\end{tabular*}
\par\vspace{0.2em}
{\scriptsize $\Delta$ = 2025 minus 2019; pp = percentage points. Mean $|F|$ is the absolute reported interface-flow magnitude.}
\par\vspace{0.4em}
\footnotesize
"""
    tex+=r'\textbf{Moses South:} MAE falls '+f"{abs(m['delta_mae_percent']):.1f}"+r'\%, while WAPE rises '+f"{m['delta_wape_pp']:.2f}"+r' pp as mean $|F|$ falls '+f"{abs(m['delta_mean_abs_flow_percent']):.1f}"+r'\%.'+'\n'
    tex+=r'\par\vspace{0.2em}Reported signed mean: $'+f"{m['mean_signed_flow_2019_MW']:+,.0f}"+r'\to '+f"{m['mean_signed_flow_2025_MW']:+,.0f}"+r'$ MW; negative-flow hours: '+f"{m['negative_hours_2019_percent']:.1f}"+r'\%$\to$'+f"{m['negative_hours_2025_percent']:.1f}"+r'\%.'+'\n'
    tex+=r"""
\par\vspace{0.3em}
\textbf{Cross-year scope:} inputs, physics, cohorts and meter definitions differ; changes do not isolate a topology effect.
\reportsource{[1,4] 2019: author-release if.map; 2025: moses\_repair\_v1. Recomputed WAPE; the paper's limit-normalized metric differs. Physical meter continuity remains unverified.}
\end{frame}
"""
    (PROJECT/'figures/comparison_2019_2025.tex').write_text(tex,encoding='utf-8')
    notes=PROJECT/'presenter_notes.md'
    body=notes.read_text(encoding='utf-8')
    if f'## 9. {TITLE}' not in body:
        body=re.sub(r'^## (\d+)\.',lambda match:'## '+str(int(match[1])+1)+'.' if int(match[1])>=9 else match[0],body,flags=re.M)
        note=f'## 9. {TITLE}\n\n'
        note+='This slide was added October 16, 2026. It compares recomputed errors for the authors’ released 57-bus DC model and supplied 2019 inputs with the latest completed 2025 AC model, moses_repair_v1. It is a cross-year descriptive comparison, not a controlled test of topology alone. The authors’ supplied if.map is used for 2019; their plotting helper has stale branch indices for five interfaces. The exact published Figure 5 is not claimed as reproduced. The paper reports a different limit-normalized metric.\n\n'
        note+='All quantities are public MW. The source cohorts are 8,760 prepared 2019 positions and 8,651 source-qualified 2025 hours. WAPE uses the sum of absolute observations; the observed magnitude column is its denominator per hour. It is not signed net flow, energy or statewide throughput. Source preparation, exclusions and physical interface definitions differ.\n\n'
        note+='| Interface | MAE 2019 → 2025, MW | Change, MW | MAE change, % | WAPE 2019 → 2025, % | Change, pp | Observed mean absolute flow 2019 → 2025, MW | Flow change, % |\n|---|---:|---:|---:|---:|---:|---:|---:|\n'
        for r in rows:
            note+=f"| {label(r['interface']).replace('--','–')} | {r['mae_2019_MW']:.3f} → {r['mae_2025_MW']:.3f} | {r['delta_mae_MW']:+.3f} | {r['delta_mae_percent']:+.2f} | {r['wape_2019_percent']:.3f} → {r['wape_2025_percent']:.3f} | {r['delta_wape_pp']:+.3f} | {r['mean_abs_flow_2019_MW']:.3f} → {r['mean_abs_flow_2025_MW']:.3f} | {r['delta_mean_abs_flow_percent']:+.2f} |\n"
        note+='\nMoses South illustrates the denominator effect: lower MW error accompanies higher WAPE because reported flow magnitude is much lower. Its reported signed mean and negative-hour share also change markedly. These describe the public reported series; they do not prove reversal through an unchanged physical meter. Dated physical membership and exact P32 effective switching times remain unresolved. Central East to Central East–VC is a comparison-name crosswalk, not proof of constant circuit membership. Do not pool the seven overlapping interfaces into a statewide improvement score.\n\n'
        note+='Sources: evidence/2019_comparison_current.csv and companion evidence review; data/comparison_2019_2025.csv; 2019 annual MAT readbacks and current comparison_arrays.npz as fingerprinted in source_manifest.json. Full signed-flow, variation and direction statistics are retained in the evidence CSVs.\n\n'
        body=body.replace('## 10. Total East:',note+'## 10. Total East:')
        notes.write_text(body,encoding='utf-8',newline='\n')
    manifest_path=PROJECT/'source_manifest.json'
    manifest=json.loads(manifest_path.read_text())
    for key, path in [('data_files',target),('data_files',PROJECT/'figures/comparison_2019_2025.tex')]:
        manifest[key]=[r for r in manifest[key] if r['path']!=path.relative_to(ROOT).as_posix()]
        manifest[key].append(record(path))
    review=json.loads((EVIDENCE/'2019_comparison_review.json').read_text())
    for entry in review['source_files']:
        manifest['source_files']=[r for r in manifest['source_files'] if r['path']!=entry['path']]
        manifest['source_files'].append(entry)
    manifest['presentation_revision']=dict(date='October 16, 2026',added_slide=9,
        base_deck_commit='1172727343f7ff5411163da59cb2956004b3aa36',
        comparison='Recomputed released 2019 DC versus latest completed 2025 AC; cross-year descriptive only')
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,table_rows=7,new_slide=9,data=str(target))))


if __name__=='__main__':main()
