"""Standalone scientific comparison of frozen source-only predictions."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
FOLDER=ROOT/'output/compact_ny_2025/generation_reconstruction'


def main():
    z=pd.read_csv(FOLDER/'zone_generation_deviations.csv')
    z=z[z.scenario_id=='S1_2025_SUMMER_PEAK_PUBLIC'].sort_values('zone')
    d=pd.read_csv(FOLDER/'scored_interface_comparison.csv')
    d=d[d.scenario_id.str.startswith('V')]
    names=['Dysinger_East','West_Central','Moses_South','Central_East','Total_East_proxy','UPNY_ConEd','Dunwoodie_South']
    ids=['V1_2025_JAN15_EVENING','V2_2025_APR15_MIDDAY','V3_2025_JUL15_EVENING','V4_2025_JUL25_NIGHT']
    matrix=d.pivot(index='scenario_id',columns='interface_name',values='residual_mw').loc[ids,names].to_numpy()
    fig,(a,b)=plt.subplots(2,1,figsize=(11,8),gridspec_kw={'height_ratios':[1.15,1]},layout='constrained')
    fig.suptitle('Compact New York testbed: load allocation and independent flow prediction',fontsize=15,weight='bold')
    x=np.arange(11);w=.25
    for off,col,label,color in [(-w,'gross_load_benchmark_mw','NYISO gross load, scaled','#99a8b5'),
                               (0,'source_prior_benchmark_mw','Independent generation estimate','#2b718e'),
                               (w,'solved_generation_mw','AC-solved generation','#d19a42')]:
        a.bar(x+off,z[col],w,label=label,color=color)
    a.set(xticks=x,xticklabels=list('ABCDEFGHIJK'),ylabel='Benchmark MW',xlabel='NYISO zone',
          title='Summer example: July 29, 2025, 18:00–19:00 EDT')
    a.legend(loc='upper left',frameon=False,fontsize=9)
    a.spines[['top','right']].set_visible(False);a.set_axisbelow(True);a.grid(axis='y',alpha=.2)
    limit=np.ceil(np.max(np.abs(matrix))/50)*50
    im=b.imshow(matrix,cmap='RdBu_r',vmin=-limit,vmax=limit,aspect='auto')
    for i in range(4):
        for j in range(7):
            b.text(j,i,f'{matrix[i,j]:+.0f}',ha='center',va='center',fontsize=10,
                   color='white' if abs(matrix[i,j])>limit*.6 else '#17242e')
    b.set(xticks=np.arange(7),xticklabels=['Dysinger\nEast','West\nCentral','Moses\nSouth','Central\nEast','Total\nEast*','UPNY/\nConEd','Dunwoodie\nSouth'],
          yticks=np.arange(4),yticklabels=['Jan 15, 18:00','Apr 15, 13:00','Jul 15, 18:00','Jul 25, 04:00'],
          title='Four reserved 2025 hours: predicted minus NYISO hourly interface flow')
    b.tick_params(length=0)
    cb=fig.colorbar(im,ax=b,shrink=.87);cb.set_label('Error, benchmark MW')
    fig.supxlabel('66 NY buses · fixed scale γ = 0.35576 · source estimates are not observed zonal dispatch\n'
                  '* All interface operators remain approximate; no internal flow targets entered the prediction fit.',fontsize=9)
    fig.savefig(FOLDER/'independent_generation_validation.png',dpi=180)
    fig.savefig(FOLDER/'independent_generation_validation.pdf')
    plt.close(fig)


if __name__=='__main__':main()
