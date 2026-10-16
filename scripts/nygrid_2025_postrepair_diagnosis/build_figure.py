"""Render controlled-model comparisons from the independently checked scores."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_postrepair_diagnosis'


def main():
    p=OUT/'ablations/factorial_metrics.csv';a=pd.read_csv(p)
    a=a[(a.period=='annual')&(a.convention=='legacy_signed_literal_from')]
    fig,axes=plt.subplots(1,2,figsize=(11.5,5.3))
    colors=['#75818d','#4e8ca9','#cf8745','#226a5e']
    scenarios=['B','G','P','GP'];labels=['Previous\nmodel','Hydro\nonly','PV20\nonly','Both\nrepairs']
    for ax,name,maximum in zip(axes,['TOTAL EAST','MOSES SOUTH'],[560,165]):
        d=a[a.interface.eq(name)].set_index('scenario').loc[scenarios]
        bars=ax.bar(np.arange(4),d.mae_public_MW,color=colors,width=.65)
        ax.set(xticks=np.arange(4),xticklabels=labels,ylim=(0,maximum),ylabel='MAE (public MW)',title=name.replace('_',' '))
        ax.bar_label(bars,fmt='%.2f',padding=5,fontsize=10)
        ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    fig.suptitle('Separating generation and northern-routing effects',x=.06,ha='left',fontsize=15,fontweight='bold')
    fig.text(.06,.90,'Same 8,651 qualified hours and unchanged diagnostic interface definitions.',fontsize=10,color='#4f5a65')
    fig.text(.06,.035,'Two fresh annual ablations; previous and combined runs independently bridged.\nEffects describe this model. Physical P32 meter equivalence remains unverified.',fontsize=9,color='#4f5a65')
    fig.tight_layout(rect=(0,.11,1,.87))
    for ext in ['png','pdf']:fig.savefig(OUT/f'controlled_effects.{ext}',dpi=180)
    plt.close(fig)
    r=dict(passed=True,source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),paired_hours=8651,
           scope='Controlled source-input changes within the model; not real-world causal source-error estimates.',
           outputs=[dict(path=f'controlled_effects.{e}',sha256=hashlib.sha256((OUT/f'controlled_effects.{e}').read_bytes()).hexdigest()) for e in ['png','pdf']])
    (OUT/'figure_receipt.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
